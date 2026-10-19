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
from zigpy.profiles import zgp as zgp_profile
import zigpy.types as t
from zigpy.util import CreateTaskMixin
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
    SrcID,
)

if TYPE_CHECKING:
    from zigpy.application import ControllerApplication

LOGGER = logging.getLogger(__name__)


def derived_group(device: GreenPowerDevice) -> t.Group:
    """The DGroupID proxies forward a GPD's GPDFs to in derived groupcast mode."""
    # Derived from the GPD ID exactly like the alias (A.3.6.1.4), and the device's NWK
    # address is that alias
    return t.Group(device.nwk)


def commissioning_security(
    source_id: SrcID, comm: GPCommissioningPayload
) -> tuple[SecurityLevel, SecurityKeyType, t.KeyData | None] | None:
    """Return the security level, key type and key of a GPD, or None to reject it."""
    if comm.extended_options is None:
        return SecurityLevel.NoSecurity, SecurityKeyType.NoKey, None

    security_level = comm.extended_options.security_level

    if security_level == SecurityLevel.Reserved:
        # A.1.4.1.3: no processing is defined for the reserved level,
        # and pairing a GPD with it would push it to every proxy.
        LOGGER.warning(
            "GP Commissioning from 0x%08X uses the reserved security level",
            source_id,
        )
        return None

    if security_level == SecurityLevel.NoSecurity:
        # The key type, key and outgoing counter of an unprotected GPD are ignored on
        # reception (A.4.2.1.1.3). Proxies report NoKey for its unprotected GPDFs, so
        # a stored key type would fail the security parameter check of every one.
        return SecurityLevel.NoSecurity, SecurityKeyType.NoKey, None

    if comm.outgoing_counter is None:
        # A protected GPD must announce its security frame counter, without it
        # the commissioning check fails (A.3.9.2.1.2)
        LOGGER.warning(
            "GP Commissioning from 0x%08X has no outgoing frame counter",
            source_id,
        )
        return None

    security_key = comm.security_key

    # Without a key, every later GPDF of a protected GPD fails verification. This sink
    # neither provisions keys nor derives them from the network key, so a GPD that does
    # not supply its own key is dropped, even if it requests one (A.3.9.1 step 13.g).
    if security_key is None:
        LOGGER.warning(
            "GP Commissioning from 0x%08X has no security key",
            source_id,
        )
        return None

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
            LOGGER.warning("Failed to decrypt security key from 0x%08X", source_id)
            return None

    return security_level, comm.extended_options.key_type, security_key


class GreenPowerManager(CreateTaskMixin):
    """Commissions Green Power devices, attached to the app.

    Limitation: only ApplicationID.SrcID (0b000) is supported. GPDs using
    ApplicationID.IEEE (0b010) are not handled.
    """

    def __init__(self, application: ControllerApplication) -> None:
        self._application = application
        # A `time.monotonic()` deadline, unaffected by wall clock adjustments
        self._commissioning_window_end: float = 0
        self._tasks: set[asyncio.Task[Any]] = set()
        # Commissioning GPDFs come from GPDs that are not registered yet, so
        # `GreenPowerDevice` cannot filter their duplicates (spec A.3.6.1.2)
        self._dedup_debouncer: Debouncer = Debouncer()
        # GPDs in bidirectional commissioning, until their Success GPDF arrives. They
        # outlive a lapse of the window, which a client may keep re-requesting.
        self._pending_devices: dict[t.EUI64, GreenPowerDevice] = {}

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
        self._commissioning_window_end = 0
        self._pending_devices.clear()

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
            self._commissioning_window_end = 0
            self._pending_devices.clear()
            await self._send_proxy_commissioning_mode(window=None)
            return

        # Proxies leave commissioning mode on their own once the window expires
        # (A.3.6.3.2), so only an explicit close needs telling them
        await self._send_proxy_commissioning_mode(window=time_s)
        self._commissioning_window_end = time.monotonic() + time_s

    def get_pending_device(self, ieee: t.EUI64) -> GreenPowerDevice | None:
        """Return the GPD in bidirectional commissioning, while the window is open."""
        # Its Success GPDF is only accepted in commissioning mode (A.3.9.1 step 18.a),
        # and outside of it the GPD's GPDFs go to its registered device, if any
        if not self.is_commissioning or ieee not in self._pending_devices:
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

        if packet.command_id == GPDCommandID.CommissioningRequest:
            coro = self._process_commissioning(packet)
        else:
            assert packet.command_id == GPDCommandID.ChannelRequest
            coro = self._process_channel_request(packet)

        self.create_task(coro, f"gp_process_command-0x{packet.command_id:02x}")

    async def _process_commissioning(self, packet: t.ZigbeeGpPacket) -> None:
        """Process a GP Commissioning command (0xE0): create device, reply, pair."""
        source_id = packet.src_id
        assert source_id is not None

        if not self.is_commissioning:
            LOGGER.debug(
                "GP Commissioning from 0x%08X ignored: window not open",
                source_id,
            )
            return

        if source_id == 0x00000000:
            LOGGER.warning(
                "GP Commissioning with unspecified sourceID 0x00000000, ignoring"
            )
            return

        try:
            comm, _ = GPCommissioningPayload.deserialize(packet.payload.serialize())
        except (ValueError, IndexError):
            LOGGER.warning(
                "Failed to parse GP Commissioning payload from 0x%08X",
                source_id,
            )
            return

        security = commissioning_security(source_id, comm)

        if security is None:
            return

        security_level, security_key_type, security_key = security
        device = GreenPowerDevice.from_commissioning(
            self._application,
            packet,
            comm,
            security_level=security_level,
            security_key_type=security_key_type,
            security_key=security_key,
        )

        # Commissioning GPDFs are unprotected, so one can be replayed with an older
        # outgoing counter. A GPD keeping its key never resets its security frame
        # counter (A.3.9.1 step 15.c), so a re-commissioned GPD keeps the higher one.
        if device.ieee in self._application.devices and device.security_level in (
            SecurityLevel.FullFrameCounterAndMIC,
            SecurityLevel.Encrypted,
        ):
            registered = self._application.devices[device.ieee]
            assert isinstance(registered, GreenPowerDevice)

            if registered.security_key == device.security_key:
                assert registered.frame_counter is not None
                assert device.frame_counter is not None
                device.frame_counter = max(
                    registered.frame_counter, device.frame_counter
                )

        # The triggering GPDF's RxAfterTx, not RxOnCapability, says whether the GPD
        # listens for a Commissioning Reply (A.3.9.1 13.j). Bidirectional commissioning
        # then finishes with the GPD's Success GPDF (A.3.9.1 18-19).
        if packet.rx_after_tx:
            self._pending_devices[device.ieee] = device
            await self._send_commissioning_reply(
                packet, security_level, security_key_type
            )
            return

        # A GPD can fall back to unidirectional commissioning
        if device.ieee in self._pending_devices:
            del self._pending_devices[device.ieee]

        await self._finalize_commissioning(device)

    def commissioning_succeeded(self, device: GreenPowerDevice) -> None:
        """Finish commissioning a GPD whose Success command (0xE2) passed its checks."""
        # The GPD may repeat its Success GPDF (A.3.9.2), only the first one finishes
        if self.get_pending_device(device.ieee) is not device:
            LOGGER.debug("Ignoring Success from %r: not commissioning", device)
            return

        del self._pending_devices[device.ieee]
        self.create_task(
            self._finalize_commissioning(device),
            f"gp_process_command-0x{GPDCommandID.SuccessReport:02x}",
        )

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
        self.create_task(
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
            packet=packet,
            gpd_id=SrcID(0x000000),
            gpd_command_id=GPDCommandID.ChannelConfiguration,
            gpd_command_payload=channel_config.serialize(),
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
        *,
        packet: t.ZigbeeGpPacket,
        gpd_id: SrcID,
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
            gpd_id=gpd_id,
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

        assert packet.src_id is not None

        await self._send_gp_response(
            packet=packet,
            gpd_id=packet.src_id,
            gpd_command_id=GPDCommandID.CommissioningReply,
            gpd_command_payload=reply.serialize(),
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
                    address=t.BroadcastAddress.RX_ON_WHEN_IDLE,
                ),
                dst_ep=t.uint8_t(GP_ENDPOINT),
                src_ep=t.uint8_t(GP_ENDPOINT),
                tsn=t.uint8_t(tsn),
                profile_id=t.uint16_t(zgp_profile.PROFILE_ID),
                cluster_id=GreenPowerProxy.cluster_id,
                data=t.SerializableBytes(hdr.serialize() + request.serialize()),
            )
        )
