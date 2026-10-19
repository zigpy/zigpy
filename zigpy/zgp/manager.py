"""Green Power Manager: commissioning of Green Power devices.

Opens and closes the GP commissioning window, handles the GPD commissioning commands
(0xE0-0xE3), and sends the GP cluster commands that configure proxies.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from cryptography.exceptions import InvalidTag

from zigpy.datastructures import Debouncer
from zigpy.device import GP_DUPLICATE_TIMEOUT, GreenPowerDevice
from zigpy.listeners import gp_command
from zigpy.profiles import zgp as zgp_profile
import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zcl.clusters.greenpower import (
    GreenPowerProxy,
    PairingOptions,
    ProxyCommissioningModeOptions,
    ResponseOptions,
    TempMasterTxChannel,
)
from zigpy.zgp.commands import (
    GPChannelConfigurationPayload,
    GPChannelRequestPayload,
    GPCommissioningPayload,
    GPCommissioningReplyOptions,
    GPCommissioningReplyPayload,
)
from zigpy.zgp.crypto import decrypt_security_key
from zigpy.zgp.types import (
    GP_ENDPOINT,
    ApplicationID,
    CommunicationMode,
    GPDCommandID,
    ProxyCommissioningModeExitMode,
    SecurityKeyType,
    SecurityLevel,
)
from zigpy.zgp.util import synthetic_ieee

if TYPE_CHECKING:
    from zigpy.application import ControllerApplication

LOGGER = logging.getLogger(__name__)


def derived_group(device: GreenPowerDevice) -> t.Group:
    """The DGroupID proxies forward a GPD's GPDFs to in derived groupcast mode."""
    # Derived from the GPD ID exactly like the alias (A.3.6.1.4), and the device's NWK
    # address is that alias
    return t.Group(device.nwk)


class GreenPowerManager:
    """Commissions Green Power devices, attached to the app.

    Limitation: only ApplicationID.SrcID (0b000) is supported. GPDs using
    ApplicationID.IEEE (0b010) are not handled.
    """

    def __init__(self, application: ControllerApplication) -> None:
        self._application = application
        self._commissioning_window_end: float = 0
        self._window_closed: asyncio.Event = asyncio.Event()
        self._window_closed.set()
        self._window_timer: asyncio.TimerHandle | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        # Commissioning GPDFs come from GPDs that are not registered yet, so
        # `GreenPowerDevice` cannot filter their duplicates (spec A.3.6.1.2)
        self._dedup_debouncer: Debouncer = Debouncer()
        # One commissioning task per GPD, restarted by each Commissioning GPDF
        self._commissioning_tasks: dict[t.EUI64, asyncio.Task[None]] = {}
        # GPDs in bidirectional commissioning, until their Success GPDF arrives
        self._pending_devices: dict[t.EUI64, GreenPowerDevice] = {}

    def _create_task(self, coro: Any, name: str) -> asyncio.Task[Any]:
        task = asyncio.get_running_loop().create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def startup(self) -> None:
        """Join the derived groups of all commissioned GPDs, to receive their GPDFs."""
        groups = {
            derived_group(device)
            for device in self._application.devices.values()
            if isinstance(device, GreenPowerDevice)
        }

        for group in sorted(groups):
            await self._application.subscribe_to_multicast_group(
                group, endpoint_id=GP_ENDPOINT
            )

    async def shutdown(self) -> None:
        """Cancel commissioning in progress and close the window."""
        self._close_window()

        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)

    @property
    def is_commissioning(self) -> bool:
        """Return True if the GP commissioning window is currently open."""
        return time.monotonic() < self._commissioning_window_end

    async def permit_join(self, time_s: int) -> None:
        """Open the GP commissioning window; time_s=0 closes it immediately."""
        if time_s == 0:
            self._close_window()
            await self._send_proxy_commissioning_mode(window=None)
            return

        # Proxies leave commissioning mode on their own once the window expires
        # (A.3.6.3.2), so only an explicit close needs telling them
        await self._send_proxy_commissioning_mode(window=time_s)

        # A new window does not resume commissioning from an expired one
        if not self.is_commissioning:
            self._close_window()

        if self._window_timer is not None:
            self._window_timer.cancel()

        self._commissioning_window_end = time.monotonic() + time_s
        self._window_closed.clear()
        self._window_timer = asyncio.get_running_loop().call_later(
            time_s, self._close_window
        )

    def _close_window(self) -> None:
        """Close the window, failing commissioning still waiting for a Success GPDF."""
        if self._window_timer is not None:
            self._window_timer.cancel()
            self._window_timer = None

        self._commissioning_window_end = 0
        self._window_closed.set()

    def get_pending_device(self, ieee: t.EUI64) -> GreenPowerDevice | None:
        """Return the GPD in bidirectional commissioning, if any."""
        if ieee not in self._pending_devices:
            return None

        return self._pending_devices[ieee]

    def packet_received(self, packet: t.ZigbeeGpPacket) -> None:
        """Process a commissioning GPDF."""
        if packet.application_id is not ApplicationID.SrcID:
            LOGGER.debug("Ignoring GP packet with unsupported addressing: %r", packet)
            return

        if self._dedup_debouncer.filter(
            (packet.src_id, packet.frame_counter),
            GP_DUPLICATE_TIMEOUT.total_seconds(),
        ):
            LOGGER.debug("Dropping duplicate GP packet: %r", packet)
            return

        if packet.command_id == GPDCommandID.ChannelRequest:
            self._create_task(
                self._process_channel_request(packet),
                f"gp_process_command-0x{packet.command_id:02x}",
            )
            return

        assert packet.command_id == GPDCommandID.CommissioningRequest
        assert packet.src_id is not None

        if not self.is_commissioning:
            LOGGER.debug(
                "GP Commissioning from 0x%08X ignored: window not open", packet.src_id
            )
            return

        if packet.src_id == 0x00000000:
            LOGGER.warning(
                "GP Commissioning with unspecified sourceID 0x00000000, ignoring"
            )
            return

        ieee = synthetic_ieee(packet.src_id)

        # A new Commissioning GPDF restarts the GPD's commissioning, which also covers
        # a GPD falling back from bidirectional to unidirectional commissioning
        if ieee in self._commissioning_tasks:
            self._commissioning_tasks[ieee].cancel()

        task = self._create_task(
            self._process_commissioning(packet),
            f"gp_commissioning-0x{packet.src_id:08X}",
        )
        self._commissioning_tasks[ieee] = task
        task.add_done_callback(lambda task: self._commissioning_done(ieee, task))

    def _commissioning_done(self, ieee: t.EUI64, task: asyncio.Task[None]) -> None:
        # A restarted commissioning may already have replaced the task
        if (
            ieee in self._commissioning_tasks
            and self._commissioning_tasks[ieee] is task
        ):
            del self._commissioning_tasks[ieee]

    async def _process_commissioning(self, packet: t.ZigbeeGpPacket) -> None:
        """Process a GP Commissioning command (0xE0): create device, reply, pair."""
        source_id = packet.src_id
        assert source_id is not None

        try:
            comm, _ = GPCommissioningPayload.deserialize(packet.payload.serialize())
        except (ValueError, IndexError):
            LOGGER.warning(
                "Failed to parse GP Commissioning payload from 0x%08X",
                source_id,
            )
            return

        security_level = SecurityLevel.NoSecurity
        security_key_type = SecurityKeyType.NoKey
        security_key = None

        if comm.extended_options is not None:
            security_level = comm.extended_options.security_level
            if security_level == SecurityLevel.Reserved:
                # A.1.4.1.3: no processing is defined for the reserved level,
                # and pairing a GPD with it would push it to every proxy.
                LOGGER.warning(
                    "GP Commissioning from 0x%08X uses the reserved security level",
                    source_id,
                )
                return

            if (
                security_level != SecurityLevel.NoSecurity
                and comm.outgoing_counter is None
            ):
                # A protected GPD must announce its security frame counter, without it
                # the commissioning check fails (A.3.9.2.1.2)
                LOGGER.warning(
                    "GP Commissioning from 0x%08X has no outgoing frame counter",
                    source_id,
                )
                return

            security_key_type = comm.extended_options.key_type
            security_key = comm.security_key

            # The key MIC is only present if the key is protected with the TC-LK
            if comm.key_mic is not None:
                # AES-CCM over 16 bytes takes ~20 us on a CM4. Offloading it to an
                # executor would cost ~200 us for the thread handoff alone, mostly on
                # the event loop itself.
                try:
                    security_key = t.KeyData(
                        decrypt_security_key(
                            source_id,
                            comm.security_key.serialize(),
                            comm.key_mic.serialize(),
                        )
                    )
                except InvalidTag:
                    LOGGER.warning(
                        "Failed to decrypt security key from 0x%08X", source_id
                    )
                    return

        device = GreenPowerDevice(
            self._application, application_id=ApplicationID.SrcID, src_id=source_id
        )
        device.device_id = comm.device_id
        device.gpd_manufacturer_id = comm.manufacturer_id
        device.gpd_model_id = comm.model_id
        device.commands = [GPDCommandID(cmd) for cmd in comm.gpd_commands or []]
        device.server_cluster_ids = list(comm.server_clusters or [])
        device.client_cluster_ids = list(comm.client_clusters or [])

        if comm.switch_information is not None:
            device.switch_configuration = comm.switch_information.configuration

        device.mac_seq_num_capability = bool(comm.options.mac_seq_num_capability)
        device.rx_on_capability = bool(comm.options.rx_on_capability)
        device.fixed_location = bool(comm.options.fixed_location)
        device.security_key = security_key
        device.security_key_type = security_key_type
        device.security_level = security_level
        # An unprotected GPD has no security frame counter, the GPDF carries its MAC
        # sequence number instead
        device.frame_counter = (
            comm.outgoing_counter
            if comm.outgoing_counter is not None
            else packet.frame_counter
        )

        # The commissioning GPDF is the latest reception from the GPD
        device.last_seen = packet.timestamp
        device.lqi = packet.lqi
        device.rssi = packet.rssi

        # The triggering GPDF's RxAfterTx, not RxOnCapability, says whether the GPD
        # listens for a Commissioning Reply (A.3.9.1 13.j). Bidirectional commissioning
        # then finishes with the GPD's Success GPDF (A.3.9.1 18-19).
        if packet.rx_after_tx:
            await self._send_commissioning_reply(
                packet, security_level, security_key_type
            )

            if not await self._wait_for_success(device):
                LOGGER.info("GP commissioning failed, no Success from %r", device)
                return

        await self._finalize_commissioning(device)

    async def _wait_for_success(self, device: GreenPowerDevice) -> bool:
        """Wait for the GPD's Success GPDF (0xE2), while the window is open."""
        # The pending device receives the GPD's GPDFs, checked with its new security
        # parameters (A.3.9.1 18.b). Nothing is awaited between sending the reply and
        # listening, so the Success GPDF cannot be missed.
        self._pending_devices[device.ieee] = device

        try:
            with self._application.frame_listeners.wait_for(
                gp_command(GPDCommandID.SuccessReport), ieee=device.ieee
            ) as success:
                window_closed = asyncio.ensure_future(self._window_closed.wait())
                waiting: list[asyncio.Future[Any]] = [success, window_closed]

                try:
                    await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    window_closed.cancel()

                return success.done()
        finally:
            # A restarted commissioning may already have replaced the device
            if (
                device.ieee in self._pending_devices
                and self._pending_devices[device.ieee] is device
            ):
                del self._pending_devices[device.ieee]

    async def _finalize_commissioning(self, device: GreenPowerDevice) -> None:
        """Register a commissioned GPD and pair it with the proxies (A.3.9.1 19)."""
        if device.ieee in self._application.devices:
            self._application.gp_device_recommissioned(device)
        else:
            self._application.listener_event("device_joined", device)
            self._application.device_initialized(device)

        await self._application.subscribe_to_multicast_group(
            derived_group(device), endpoint_id=GP_ENDPOINT
        )
        await self.send_pairing(device, add_sink=True)

        LOGGER.info("GP device commissioned: %r", device)

    def decommission(self, device: GreenPowerDevice) -> None:
        """Remove a GPD whose Decommissioning command (0xE1) passed its checks."""
        self._create_task(
            self._application.remove(device.ieee),
            f"gp_process_command-0x{GPDCommandID.DecommissioningRequest:02x}",
        )

    async def unpair(self, device: GreenPowerDevice) -> None:
        """Remove a GPD from all proxies and leave its derived group, once removed."""
        await self.send_pairing(device, add_sink=False)

        group = derived_group(device)

        # Distinct GPD IDs can derive the same group
        if group not in {
            derived_group(other)
            for other in self._application.devices.values()
            if isinstance(other, GreenPowerDevice)
        }:
            await self._application.unsubscribe_from_multicast_group(
                group, endpoint_id=GP_ENDPOINT
            )

        LOGGER.info("GP device unpaired: %r", device)

    async def _process_channel_request(self, packet: t.ZigbeeGpPacket) -> None:
        """Process a GP Channel Request (0xE3) by replying with Channel Configuration."""
        source_id = packet.src_id
        assert source_id is not None

        # Outside of commissioning mode, the command is silently dropped (A.3.9.1 7.a)
        if not self.is_commissioning:
            LOGGER.debug(
                "GP Channel Request from 0x%08X ignored: window not open", source_id
            )
            return

        try:
            request, _ = GPChannelRequestPayload.deserialize(packet.payload.serialize())
        except (ValueError, IndexError):
            LOGGER.warning("Failed to parse Channel Request from 0x%08X", source_id)
            return

        channel = self._application.state.network_info.channel

        channel_config = GPChannelConfigurationPayload(
            operational_channel=channel - 11,
            basic=1,
            _reserved=0,
        )

        # The GPD listens on the channel of its next attempt, not the operational one
        # (A.3.9.1 7.d.iv)
        await self._send_gp_response(
            packet,
            GPDCommandID.ChannelConfiguration,
            channel_config.serialize(),
            tx_channel=request.next_channel + 11,
        )

    # --- Outgoing GP commands ---

    async def _send_proxy_commissioning_mode(self, window: int | None) -> None:
        """Broadcast a GP Proxy Commissioning Mode command, to exit if no window."""
        await self._broadcast_command(
            GreenPowerProxy.ClientCommandDefs.proxy_commissioning_mode,
            options=ProxyCommissioningModeOptions(
                enter=int(window is not None),
                commissioning_window_present=int(window is not None),
                # Without it, proxies may ignore the exit command and stay in
                # commissioning mode until the window expires (Figure 57)
                exit_mode=ProxyCommissioningModeExitMode.OnExplicitExit,
                channel_present=0,
                unicast=0,
                _reserved=0,
            ),
            window=window,
        )

    async def send_pairing(self, device: GreenPowerDevice, add_sink: bool) -> None:
        """Broadcast a GP Pairing command telling proxies to add or remove a GPD."""
        assert device.src_id is not None

        # The frame counter is the security frame counter of a protected GPD, or the MAC
        # sequence number of an unprotected one if it increments it (A.3.3.5.2)
        frame_counter_present = add_sink and (
            device.security_level
            in (SecurityLevel.FullFrameCounterAndMIC, SecurityLevel.Encrypted)
            or device.mac_seq_num_capability
        )

        # TODO: proxies forward with derived groupcast, a single NWK broadcast per GPDF.
        # Unicast forwarding through a chosen set of proxies needs zigpy to maintain
        # those proxies as the network changes, from its topology scans.
        options = PairingOptions(
            application_id=ApplicationID.SrcID,
            add_sink=int(add_sink),
            remove_gpd=int(not add_sink),
            communication_mode=CommunicationMode.GroupcastForwardToDGroup,
            gpd_fixed=int(device.fixed_location),
            gpd_mac_seq_num_cap=int(device.mac_seq_num_capability),
            security_level=device.security_level,
            security_key_type=device.security_key_type,
            security_frame_counter_present=int(frame_counter_present),
            security_key_present=int(add_sink and device.security_key is not None),
            assigned_alias_present=0,
            groupcast_radius_present=0,
            _reserved=0,
        )

        schema_kwargs: dict[str, Any] = {
            "options": options,
            "gpd_id": device.src_id,
        }

        if add_sink:
            schema_kwargs["sink_group"] = derived_group(device)
            schema_kwargs["device_id"] = t.uint8_t(device.device_id)

            if frame_counter_present:
                schema_kwargs["frame_counter"] = t.uint32_t(device.frame_counter)

            if device.security_key is not None:
                # The GP Pairing carries the key from the Sink Table in the clear and
                # proxies store it as-is (A.3.3.5.2). Only GPDFs protect the key with
                # the TC-LK (A.3.7.1.2.3), the GP Pairing is protected by NWK security.
                schema_kwargs["key"] = device.security_key

        await self._broadcast_command(
            GreenPowerProxy.ClientCommandDefs.pairing, **schema_kwargs
        )
        LOGGER.debug(
            "Sent GP Pairing for 0x%08X (add_sink=%s)",
            device.src_id,
            add_sink,
        )

    # --- GP Response (sink-to-GPD via proxy) ---

    async def _send_gp_response(
        self,
        packet: t.ZigbeeGpPacket,
        gpd_command_id: GPDCommandID,
        gpd_command_payload: bytes,
        tx_channel: int,
    ) -> None:
        """Send a GP Response (0x06) instructing a proxy to transmit a GPDF to a GPD."""
        # The proxy that heard the GPD transmits in its receive window. A GPDF the
        # coordinator received directly has no forwarding proxy.
        if packet.gpp_short_addr is not None:
            temp_master = packet.gpp_short_addr
        else:
            temp_master = self._application.state.node_info.nwk

        await self._broadcast_command(
            GreenPowerProxy.ClientCommandDefs.response,
            options=ResponseOptions(
                application_id=ApplicationID.SrcID,
                transmit_on_endpoint_match=0,
                _reserved=0,
            ),
            temp_master_short_addr=t.uint16_t(temp_master),
            temp_master_tx_channel=TempMasterTxChannel(
                transmit_channel=t.uint4_t(tx_channel - 11), _reserved=0
            ),
            gpd_id=packet.src_id,
            gpd_command_id=gpd_command_id,
            gpd_command_payload=t.LVBytes(gpd_command_payload),
        )

    async def _send_commissioning_reply(
        self,
        packet: t.ZigbeeGpPacket,
        security_level: SecurityLevel,
        security_key_type: SecurityKeyType,
    ) -> None:
        """Send a GP Commissioning Reply (0xF0) to a GPD listening after its GPDF.

        This sink does not provision a security key in the Commissioning Reply; the
        GPD must already hold a pre-shared key or use no security.
        """
        # Without provisioned parameters, the reply echoes the security level and key
        # type of the triggering Commissioning GPDF (A.3.9.1 13.j.i)
        reply = GPCommissioningReplyPayload(
            options=GPCommissioningReplyOptions(
                pan_id_present=0,
                security_key_present=0,
                key_encrypted=0,
                security_level=security_level,
                key_type=security_key_type,
            )
        )

        await self._send_gp_response(
            packet,
            GPDCommandID.CommissioningReply,
            reply.serialize(),
            tx_channel=self._application.state.network_info.channel,
        )

    # --- Helpers ---

    async def _broadcast_command(
        self, command: foundation.ZCLCommandDef, **kwargs: Any
    ) -> None:
        """Broadcast a GP cluster command from the sink to all proxies."""
        tsn = self._application.get_sequence()

        # The sink implements the server side of the GP cluster and the proxies the
        # client side, so commands to proxies go server-to-client (Table 37)
        hdr = foundation.ZCLHeader.cluster(
            tsn=tsn,
            command_id=command.id,
            direction=foundation.Direction.Server_to_Client,
        )
        request = command.schema(**kwargs)

        await self._application.send_packet(
            t.ZigbeePacket(
                dst=t.AddrModeAddress(
                    addr_mode=t.AddrMode.Broadcast,
                    address=t.BroadcastAddress.ALL_ROUTERS_AND_COORDINATOR,
                ),
                dst_ep=t.uint8_t(GP_ENDPOINT),
                src_ep=t.uint8_t(GP_ENDPOINT),
                tsn=t.uint8_t(tsn),
                profile_id=t.uint16_t(zgp_profile.PROFILE_ID),
                cluster_id=GreenPowerProxy.cluster_id,
                data=t.SerializableBytes(hdr.serialize() + request.serialize()),
            )
        )
