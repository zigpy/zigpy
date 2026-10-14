"""Green Power Manager: commissioning of Green Power devices.

Opens and closes the GP commissioning window, handles the GPD commissioning commands
(0xE0-0xE3), and sends the GP cluster commands that configure proxies.
"""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from typing import TYPE_CHECKING, Any

from cryptography.exceptions import InvalidTag

from zigpy.datastructures import Debouncer
from zigpy.device import GreenPowerDevice
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
    GP_CLUSTER_ID,
    GP_ENDPOINT,
    GP_GROUP_ID,
    ApplicationID,
    CommunicationMode,
    GPDCommandID,
    SecurityKeyType,
    SecurityLevel,
    SrcID,
)

if TYPE_CHECKING:
    from zigpy.application import ControllerApplication

LOGGER = logging.getLogger(__name__)

# GPDFs the manager handles. Decommissioning is not one of them: it comes from a
# registered GPD, which checks its freshness and security first (spec A.3.5.2.4)
COMMISSIONING_COMMANDS: frozenset[GPDCommandID] = frozenset(
    {
        GPDCommandID.CommissioningRequest,
        GPDCommandID.SuccessReport,
        GPDCommandID.ChannelRequest,
    }
)


class GreenPowerManager:
    """Commissions Green Power devices, attached to the app.

    Limitation: only ApplicationID.SrcID (0b000) is supported. GPDs using
    ApplicationID.IEEE (0b010) are not handled.
    """

    # Duplicate filtering window per ZGP spec A.3.6.1.2
    DEDUP_TIMEOUT_S: float = 2.0

    def __init__(self, application: ControllerApplication) -> None:
        self._application = application
        self._commissioning_window_end: float = 0
        self._commissioning_task: asyncio.Task[None] | None = None
        # Background tasks spawned from incoming frames; tracked so shutdown
        # can cancel everything instead of leaving work attached to the app.
        self._tasks: set[asyncio.Task[Any]] = set()
        # Commissioning GPDFs come from GPDs that are not registered yet, so
        # `GreenPowerDevice` cannot filter their duplicates (spec A.3.6.1.2)
        self._dedup_debouncer: Debouncer = Debouncer()

    def _create_task(self, coro: Any, name: str | None = None) -> asyncio.Task[Any]:
        """Create a task owned by the manager, tracked until completion."""
        task = asyncio.get_running_loop().create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def shutdown(self) -> None:
        """Cancel pending work and reset state."""
        if self._commissioning_task is not None:
            self._commissioning_task.cancel()
            self._commissioning_task = None
        self._commissioning_window_end = 0

        pending = list(self._tasks)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._tasks.clear()

    @property
    def is_commissioning(self) -> bool:
        """Return True if the GP commissioning window is currently open."""
        return time.monotonic() < self._commissioning_window_end

    def _is_duplicate(self, source_id: SrcID, frame_counter: int | None) -> bool:
        """Drop a (sourceID, frame_counter) pair reforwarded by a proxy (A.3.6.1.2)."""
        filtered = self._dedup_debouncer.filter(
            (source_id, frame_counter), self.DEDUP_TIMEOUT_S
        )
        if filtered:
            LOGGER.debug(
                "GP dedup: dropping duplicate from 0x%08X (fc=%d)",
                source_id,
                frame_counter,
            )
        return filtered

    # --- Frame processing ---

    def packet_received(self, packet: t.ZigbeeGpPacket) -> None:
        """Process a commissioning GPDF, dispatching async work as a background task."""
        if packet.application_id is not ApplicationID.SrcID:
            LOGGER.debug("Ignoring GP packet with unsupported addressing: %r", packet)
            return

        assert packet.src_id is not None

        if self._is_duplicate(packet.src_id, packet.frame_counter):
            return

        self._create_task(
            self._process_commissioning_command(packet),
            f"gp_process_command-0x{packet.command_id:02x}",
        )

    async def _process_commissioning_command(self, packet: t.ZigbeeGpPacket) -> None:
        """Dispatch a commissioning GPDF by its command ID."""
        assert packet.src_id is not None

        proxy_nwk = packet.gpp_short_addr

        if packet.command_id == GPDCommandID.CommissioningRequest:
            await self._process_commissioning(packet, proxy_nwk)
        elif packet.command_id == GPDCommandID.ChannelRequest:
            await self._process_channel_request(packet, proxy_nwk)
        elif packet.command_id == GPDCommandID.SuccessReport:
            LOGGER.debug("GP Success from 0x%08X", packet.src_id)

    # --- Commissioning ---

    async def _process_commissioning(
        self, packet: t.ZigbeeGpPacket, proxy_nwk: int | None = None
    ) -> None:
        """Process a GP Commissioning command (0xE0): create device, pair, reply."""
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

        LOGGER.info(
            "GP device commissioning: source_id=0x%08X, device_id=0x%02X",
            source_id,
            comm.device_id,
        )

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
            security_key_type = comm.extended_options.key_type

            if comm.extended_options.key_present and comm.security_key is not None:
                if comm.extended_options.key_encrypted and comm.key_mic is not None:
                    mic_bytes = struct.pack("<I", comm.key_mic)

                    # AES-CCM over 16 bytes takes ~20 us on a CM4. Offloading it to an
                    # executor would cost ~200 us for the thread handoff alone, mostly
                    # on the event loop itself.
                    try:
                        key_data = decrypt_security_key(
                            source_id, bytes(comm.security_key), mic_bytes
                        )
                    except InvalidTag:
                        LOGGER.warning(
                            "Failed to decrypt security key from 0x%08X",
                            source_id,
                            exc_info=True,
                        )
                        return
                    security_key = t.KeyData(key_data)
                else:
                    security_key = t.KeyData(comm.security_key)

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
        device.frame_counter = (
            comm.outgoing_counter
            if comm.outgoing_counter is not None
            else packet.frame_counter
        )

        if device.ieee in self._application.devices:
            self._application.gp_device_recommissioned(device)
        else:
            self._application.listener_event("device_joined", device)
            self._application.device_initialized(device)

        if device.rx_on_capability:
            await self._send_commissioning_reply(source_id, proxy_nwk)

        await self.send_pairing(device, add_sink=True, proxy_nwk=proxy_nwk)

        LOGGER.info("GP device commissioned: %r", device)

    def decommission(self, device: GreenPowerDevice) -> None:
        """Remove a GPD whose Decommissioning command (0xE1) passed its checks."""
        self._create_task(
            self._decommission(device),
            f"gp_process_command-0x{GPDCommandID.DecommissioningRequest:02x}",
        )

    async def _decommission(self, device: GreenPowerDevice) -> None:
        await self.send_pairing(device, add_sink=False)
        await self._application.remove(device.ieee)

        LOGGER.info("GP device decommissioned: %r", device)

    async def _process_channel_request(
        self,
        packet: t.ZigbeeGpPacket,
        proxy_nwk: int | None = None,
    ) -> None:
        """Process a GP Channel Request (0xE3) by replying with Channel Configuration."""
        source_id = packet.src_id
        assert source_id is not None

        try:
            channel_req, _ = GPChannelRequestPayload.deserialize(
                packet.payload.serialize()
            )
        except (ValueError, IndexError):
            LOGGER.warning("Failed to parse Channel Request from 0x%08X", source_id)
            return

        channel = self._application.state.network_info.channel

        LOGGER.debug(
            "GP Channel Request from 0x%08X: next=%d, second=%d, "
            "responding with channel %d",
            source_id,
            channel_req.next_channel + 11,
            channel_req.second_next_channel + 11,
            channel,
        )

        channel_config = GPChannelConfigurationPayload(
            operational_channel=channel - 11,
            basic=1,
            _reserved=0,
        )

        await self._send_gp_response(
            source_id=source_id,
            gpd_command_id=GPDCommandID.ChannelConfiguration,
            gpd_command_payload=channel_config.serialize(),
            proxy_nwk=proxy_nwk,
        )

    # --- Commissioning window control ---

    async def permit_join(self, time_s: int) -> None:
        """Open the GP commissioning window; time_s=0 closes it immediately."""
        if time_s == 0:
            await self._close_commissioning_window()
            return

        LOGGER.info("Opening GP commissioning window for %d seconds", time_s)

        await self._send_proxy_commissioning_mode(enter=True, window=time_s)
        self._commissioning_window_end = time.monotonic() + time_s

        if self._commissioning_task is not None:
            self._commissioning_task.cancel()

        self._commissioning_task = self._create_task(
            self._commissioning_window_timer(time_s),
            name="gp_commissioning_window_timer",
        )

    async def _commissioning_window_timer(self, time_s: int) -> None:
        """Timer task that closes the commissioning window after expiry."""
        try:
            await asyncio.sleep(time_s)
            await self._close_commissioning_window()
        except asyncio.CancelledError:
            pass

    async def _close_commissioning_window(self) -> None:
        """Close the GP commissioning window."""
        self._commissioning_window_end = 0

        LOGGER.info("Closing GP commissioning window")

        await self._send_proxy_commissioning_mode(enter=False)

    # --- Outgoing GP commands ---

    async def _send_proxy_commissioning_mode(
        self, enter: bool, window: int | None = None
    ) -> None:
        """Broadcast a GP Proxy Commissioning Mode command to enter or exit."""
        has_window = enter and window is not None
        options = ProxyCommissioningModeOptions(
            enter=int(enter),
            commissioning_window_present=int(has_window),
            exit_mode=0,  # exit on window expiry only
            channel_present=0,
            unicast=0,
            _reserved=0,
        )

        schema_kwargs: dict[str, Any] = {"options": options}
        if has_window:
            schema_kwargs["window"] = window

        await self._broadcast_command(
            GreenPowerProxy.ClientCommandDefs.proxy_commissioning_mode,
            **schema_kwargs,
        )

    async def send_pairing(
        self,
        device: GreenPowerDevice,
        add_sink: bool = True,
        proxy_nwk: int | None = None,
    ) -> None:
        """Broadcast a GP Pairing command telling proxies to add or remove a GPD.

        Uses UnicastLightweight when a proxy forwarded the commissioning
        notification, since that proxy is a known unicast target; otherwise
        falls back to GroupcastForwardToDGroup. Table 27 lists the possible
        gpsCommunicationMode values; choosing between them per pairing is
        this sink's own policy, not spec-mandated.
        """
        assert device.src_id is not None

        coordinator_ieee = self._application.state.node_info.ieee
        coordinator_nwk = self._application.state.node_info.nwk

        if proxy_nwk is not None:
            comm_mode = CommunicationMode.UnicastLightweight
        else:
            comm_mode = CommunicationMode.GroupcastForwardToDGroup

        options = PairingOptions(
            application_id=ApplicationID.SrcID,
            add_sink=int(add_sink),
            remove_gpd=int(not add_sink),
            communication_mode=comm_mode,
            gpd_fixed=int(device.fixed_location),
            gpd_mac_seq_num_cap=int(device.mac_seq_num_capability),
            security_level=device.security_level,
            security_key_type=device.security_key_type,
            security_frame_counter_present=int(add_sink),
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
            if comm_mode in (
                CommunicationMode.Unicast,
                CommunicationMode.UnicastLightweight,
            ):
                schema_kwargs["sink_ieee"] = coordinator_ieee
                schema_kwargs["sink_nwk_addr"] = coordinator_nwk
            else:
                schema_kwargs["sink_group"] = t.Group(GP_GROUP_ID)
            schema_kwargs["device_id"] = t.uint8_t(device.device_id)

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
        source_id: int,
        gpd_command_id: int,
        gpd_command_payload: bytes,
        proxy_nwk: int | None = None,
    ) -> None:
        """Send a GP Response (0x06) instructing a proxy to transmit a GPDF."""
        channel = self._application.state.network_info.channel
        temp_master = proxy_nwk or self._application.state.node_info.nwk

        await self._broadcast_command(
            GreenPowerProxy.ClientCommandDefs.response,
            options=ResponseOptions(
                application_id=ApplicationID.SrcID,
                transmit_on_endpoint_match=0,
                _reserved=0,
            ),
            temp_master_short_addr=t.uint16_t(temp_master),
            temp_master_tx_channel=TempMasterTxChannel(
                transmit_channel=t.uint4_t(channel - 11), _reserved=0
            ),
            gpd_id=SrcID(source_id),
            gpd_command_id=GPDCommandID(gpd_command_id),
            gpd_command_payload=t.LVBytes(gpd_command_payload),
        )
        LOGGER.debug(
            "Sent GP Response (cmd=0x%02X) for GPD 0x%08X via proxy 0x%04X",
            gpd_command_id,
            source_id,
            temp_master,
        )

    async def _send_commissioning_reply(
        self, source_id: int, proxy_nwk: int | None = None
    ) -> None:
        """Send a GP Commissioning Reply (0xF0) to an RX-capable GPD.

        This sink does not provision a security key in the Commissioning
        Reply; the GPD must already hold a pre-shared key or use no security.
        """
        LOGGER.info(
            "Sending GP Commissioning Reply to RX-capable GPD 0x%08X",
            source_id,
        )

        commissioning_reply = GPCommissioningReplyPayload(
            options=GPCommissioningReplyOptions(
                pan_id_present=0,
                security_key_present=0,
                key_encrypted=0,
                security_level=SecurityLevel.NoSecurity,
                key_type=SecurityKeyType.NoKey,
            )
        )

        await self._send_gp_response(
            source_id=source_id,
            gpd_command_id=GPDCommandID.CommissioningReply,
            gpd_command_payload=commissioning_reply.serialize(),
            proxy_nwk=proxy_nwk,
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
                cluster_id=t.uint16_t(GP_CLUSTER_ID),
                data=t.SerializableBytes(hdr.serialize() + request.serialize()),
            )
        )
