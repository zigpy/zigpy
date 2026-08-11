"""Green Power Manager: processes GP frames on cluster 0x0021, endpoint 242.

Manages GP device lifecycle (commissioning, decommissioning) and dispatches
GP commands to listeners.
"""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from typing import TYPE_CHECKING, Any

from zigpy.datastructures import Debouncer
from zigpy.event import EventBase
from zigpy.profiles import zgp as zgp_profile
import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zcl.clusters.greenpower import (
    GreenPowerProxy,
    NotificationOptions,
    PairingOptions,
    PairingSchema,
    ProxyCommissioningModeOptions,
    ProxyCommissioningModeSchema,
    ResponseOptions,
    ResponseSchema,
    TempMasterTxChannel,
)
from zigpy.zgp.commands import (
    GPChannelConfigurationPayload,
    GPChannelRequestPayload,
    GPCommissioningPayload,
    GPCommissioningReplyOptions,
    GPCommissioningReplyPayload,
)
from zigpy.zgp.crypto import decrypt_security_key, encrypt_security_key
from zigpy.zgp.device import GPDevice
from zigpy.zgp.events import CommandReceived, DeviceJoined, DeviceLeft
from zigpy.zgp.proxy import GPProxyTable
import zigpy.zgp.types as zgptypes
from zigpy.zgp.types import (
    GP_CLUSTER_ID,
    GP_ENDPOINT,
    GP_GROUP_ID,
    CommunicationMode,
    GPDCommandID,
    SecurityKeyType,
    SecurityLevel,
)

if TYPE_CHECKING:
    from zigpy.application import ControllerApplication

LOGGER = logging.getLogger(__name__)

DEFAULT_COMMISSIONING_WINDOW_S: int = 180


class GreenPowerManager(EventBase):
    """Central manager for Green Power protocol handling, attached to the app.

    Limitation: only ApplicationID.SrcID (0b000) is supported. GPDs using
    ApplicationID.IEEE (0b010) are not handled.
    """

    # Duplicate filtering window per ZGP spec A.3.6.1.2
    DEDUP_TIMEOUT_S: float = 2.0

    def __init__(self, application: ControllerApplication) -> None:
        super().__init__()
        self._application = application
        self._devices: dict[int, GPDevice] = {}  # sourceID -> GPDevice
        self._commissioning_window_end: float = 0
        self._commissioning_task: asyncio.Task[None] | None = None
        # Background tasks spawned from incoming frames; tracked so shutdown
        # can cancel everything instead of leaving work attached to the app.
        self._tasks: set[asyncio.Task[Any]] = set()
        self.proxy_table: GPProxyTable = GPProxyTable()
        # Duplicate filtering via zigpy's shared Debouncer implementation
        # (spec A.3.6.1.2): same (sourceID, frame_counter) key seen again
        # inside DEDUP_TIMEOUT_S is a retransmission from a different proxy.
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
    def devices(self) -> dict[int, GPDevice]:
        """Return the dictionary of commissioned GP devices."""
        return self._devices

    @property
    def is_commissioning(self) -> bool:
        """Return True if the GP commissioning window is currently open."""
        return time.monotonic() < self._commissioning_window_end

    def get_device(self, source_id: int) -> GPDevice | None:
        """Get a commissioned GP device by sourceID."""
        return self._devices.get(source_id)

    def _is_duplicate(self, source_id: int, frame_counter: int) -> bool:
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

    def add_device(self, device: GPDevice) -> None:
        """Add or update a GP device in the registry."""
        self._devices[device.source_id] = device

    def remove_device(self, source_id: int) -> GPDevice | None:
        """Remove a GP device from the registry."""
        return self._devices.pop(source_id, None)

    # --- Frame processing ---

    def handle_packet(self, packet: t.ZigbeePacket) -> bool:
        """Process a GP frame packet, dispatching async work as background tasks."""
        if packet.dst_ep != GP_ENDPOINT or packet.cluster_id != GP_CLUSTER_ID:
            return False

        try:
            data = packet.data.serialize()
            hdr, zcl_payload = foundation.ZCLHeader.deserialize(data)
        except ValueError:
            LOGGER.debug("Error processing GP packet", exc_info=True)
            return False

        if hdr.frame_control.frame_type != foundation.FrameType.CLUSTER_COMMAND:
            LOGGER.debug("GP frame is not cluster-specific, ignoring")
            return False

        is_server_to_client = (
            hdr.frame_control.direction == foundation.Direction.Server_to_Client
        )

        proxy_nwk: int | None = None
        if packet.src and packet.src.addr_mode == t.AddrMode.NWK:
            assert isinstance(packet.src.address, t.NWK)
            proxy_nwk = int(packet.src.address)

        self._create_task(
            self._process_zcl_command(
                hdr.command_id, zcl_payload, is_server_to_client, proxy_nwk
            ),
            f"gp_process_command-0x{hdr.command_id:02x}",
        )
        return True

    async def _process_zcl_command(
        self,
        command_id: int,
        payload: bytes,
        is_server_to_client: bool,
        proxy_nwk: int | None,
    ) -> None:
        """Dispatch a parsed ZCL command on the GP cluster.

        Only server-to-sink commands are consumed; client commands are only sent.
        """
        if is_server_to_client:
            LOGGER.debug(
                "Received GP client command 0x%02X (unexpected direction)",
                command_id,
            )
            return

        server_cmds = GreenPowerProxy.ServerCommandDefs
        if command_id == server_cmds.notification.id:
            await self._handle_gp_notification(payload, proxy_nwk)
        elif command_id == server_cmds.commissioning_notification.id:
            await self._handle_commissioning_notification(payload, proxy_nwk)
        else:
            LOGGER.debug("Unhandled GP server command: 0x%02X", command_id)

    async def _handle_gp_notification(
        self, payload: bytes, proxy_nwk: int | None
    ) -> None:
        """Handle a GP Notification command (server command 0x00), the main data path."""
        try:
            notification = GreenPowerProxy.NotificationSchema.deserialize(payload)[0]
        except (ValueError, IndexError):
            LOGGER.warning("Failed to parse GP Notification payload")
            return

        source_id = int(notification.gpd_id)
        gpd_command_id = int(notification.command_id)
        gpd_payload = bytes(notification.payload) if notification.payload else b""
        frame_counter = int(notification.frame_counter)

        LOGGER.debug(
            "GP Notification: source_id=0x%08X, cmd=0x%02X, counter=%d",
            source_id,
            gpd_command_id,
            frame_counter,
        )

        if proxy_nwk is not None:
            self.proxy_table.add_or_update(
                source_id=source_id,
                proxy_nwk=proxy_nwk,
                frame_counter=frame_counter,
            )

        # Duplicate filtering: when multiple proxies forward the same GPD
        # frame, only process the first one (spec A.3.6.1.2)
        if self._is_duplicate(source_id, frame_counter):
            return

        if gpd_command_id == GPDCommandID.CommissioningRequest:
            await self._process_commissioning(
                source_id, frame_counter, gpd_payload, proxy_nwk
            )
            return

        if gpd_command_id == GPDCommandID.DecommissioningRequest:
            await self._process_decommissioning(source_id)
            return

        if gpd_command_id == GPDCommandID.ChannelRequest:
            await self._process_channel_request(source_id, gpd_payload, proxy_nwk)
            return

        if gpd_command_id == GPDCommandID.SuccessReport:
            LOGGER.debug("GP Success from 0x%08X", source_id)
            return

        if not self._security_matches(source_id, notification.options):
            return

        await self._dispatch_gp_command(
            source_id, frame_counter, gpd_command_id, gpd_payload
        )

    async def _handle_commissioning_notification(  # pragma: no cover
        self, payload: bytes, proxy_nwk: int | None
    ) -> None:
        """Handle a GP Commissioning Notification command (server command 0x04)."""
        try:
            notification = GreenPowerProxy.CommissioningNotificationSchema.deserialize(
                payload
            )[0]
        except (ValueError, IndexError):
            LOGGER.warning("Failed to parse GP Commissioning Notification")
            return

        source_id = int(notification.gpd_id)
        gpd_command_id = int(notification.command_id)
        gpd_payload = bytes(notification.payload) if notification.payload else b""
        frame_counter = int(notification.frame_counter)

        LOGGER.debug(
            "GP Commissioning Notification: source_id=0x%08X, cmd=0x%02X",
            source_id,
            gpd_command_id,
        )

        if gpd_command_id == GPDCommandID.CommissioningRequest:
            await self._process_commissioning(
                source_id, frame_counter, gpd_payload, proxy_nwk
            )
        elif gpd_command_id == GPDCommandID.DecommissioningRequest:
            await self._process_decommissioning(source_id)
        elif gpd_command_id == GPDCommandID.ChannelRequest:
            await self._process_channel_request(source_id, gpd_payload, proxy_nwk)

    # --- Commissioning ---

    async def _process_commissioning(
        self,
        source_id: int,
        frame_counter: int,
        payload: bytes,
        proxy_nwk: int | None = None,
    ) -> None:
        """Process a GP Commissioning command (0xE0): create device, pair, reply."""
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
            comm, _ = GPCommissioningPayload.deserialize(payload)
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
                    try:
                        key_data = decrypt_security_key(
                            source_id, bytes(comm.security_key), mic_bytes
                        )
                    except Exception:  # noqa: BLE001
                        LOGGER.warning(
                            "Failed to decrypt security key from 0x%08X",
                            source_id,
                            exc_info=True,
                        )
                        return
                    security_key = t.KeyData(key_data)
                else:
                    security_key = t.KeyData(comm.security_key)

        device = GPDevice(
            source_id=source_id,
            device_id=comm.device_id,
            security_key=security_key,
            security_level=security_level,
            security_key_type=security_key_type,
            frame_counter=(
                comm.outgoing_counter
                if comm.outgoing_counter is not None
                else frame_counter
            ),
            manufacturer_id=comm.manufacturer_id,
            model_id=comm.model_id,
            gpd_commands=list(comm.gpd_commands or []),
            server_clusters=list(comm.server_clusters or []),
            client_clusters=list(comm.client_clusters or []),
            mac_seq_num_capability=bool(comm.options.mac_seq_num_capability),
            rx_on_capability=bool(comm.options.rx_on_capability),
            fixed_location=bool(comm.options.fixed_location),
        )

        self.add_device(device)

        if device.rx_on_capability:
            await self._send_commissioning_reply(source_id, proxy_nwk)

        await self.send_pairing(device, add_sink=True, proxy_nwk=proxy_nwk)

        self.emit(DeviceJoined.event_type, DeviceJoined(device=device))

        LOGGER.info(
            "GP device commissioned: %r",
            device,
        )

    async def _process_decommissioning(self, source_id: int) -> None:
        """Process a GP Decommissioning command (0xE1)."""
        device = self.remove_device(source_id)

        if device is not None:
            self.proxy_table.remove_by_source_id(source_id)
            await self.send_pairing(device, add_sink=False)
            self.emit(DeviceLeft.event_type, DeviceLeft(device=device))

            LOGGER.info(
                "GP device decommissioned: source_id=0x%08X",
                source_id,
            )
        else:
            LOGGER.debug(
                "GP Decommissioning for unknown device 0x%08X",
                source_id,
            )

    async def _process_channel_request(
        self,
        source_id: int,
        payload: bytes,
        proxy_nwk: int | None = None,
    ) -> None:
        """Process a GP Channel Request (0xE3) by replying with Channel Configuration."""
        try:
            channel_req, _ = GPChannelRequestPayload.deserialize(payload)
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

    # --- Command dispatch ---

    def _security_matches(self, source_id: int, options: NotificationOptions) -> bool:
        """Compare a notification's security level with the GPD's (A.3.5.2.5).

        Runs before dispatch, so a rejected frame never reaches the frame
        counter. A.3.5.2.5 orders the checks the same way.
        """
        device = self.get_device(source_id)
        if device is None:
            # Nothing to compare against; _dispatch_gp_command reports it
            return True

        # A.3.5.2.5 compares the SecurityKeyType too, from the Sink Table. Only
        # a radio holding that table can: EZSP fills the sub-field from the
        # NCP's own tables, which zigpy never programs, so it arrives as NoKey
        # and comparing it would drop every frame from a secured GPD.
        if options.security_level == device.security_level:
            return True

        LOGGER.warning(
            "GP command from 0x%08X announces level %s, commissioned with %s",
            source_id,
            options.security_level,
            device.security_level,
        )
        return False

    async def _dispatch_gp_command(
        self,
        source_id: int,
        frame_counter: int,
        command_id: int,
        payload: bytes,
    ) -> None:
        """Dispatch a GP data command: verify the counter, emit CommandReceived.

        The payload is emitted as the forwarding GPP security-processed it: a
        GP Notification carries neither the MIC nor the RxAfterTx bit (Figures
        23/24), so the CCM* header of the original GPDF cannot be rebuilt here.
        """
        device = self.get_device(source_id)

        if device is None:
            LOGGER.debug(
                "GP command from unknown device 0x%08X (cmd=0x%02X)",
                source_id,
                command_id,
            )
            return

        if not device.update_frame_counter(frame_counter):
            return

        LOGGER.debug(
            "GP command from 0x%08X: cmd=0x%02X, payload=%s",
            source_id,
            command_id,
            payload.hex() if payload else "empty",
        )

        self.emit(
            CommandReceived.event_type,
            CommandReceived(
                device=device,
                command_id=GPDCommandID(command_id),
                payload=payload,
            ),
        )

    # --- Commissioning window control ---

    async def permit_join(self, time_s: int = DEFAULT_COMMISSIONING_WINDOW_S) -> None:
        """Open the GP commissioning window; time_s=0 closes it immediately."""
        if time_s == 0:
            await self._close_commissioning_window()
            return

        self._commissioning_window_end = time.monotonic() + time_s

        LOGGER.info("Opening GP commissioning window for %d seconds", time_s)

        await self._send_proxy_commissioning_mode(enter=True, window=time_s)

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

        try:
            frame_data = self._build_zcl_frame(
                command_id=GreenPowerProxy.ClientCommandDefs.proxy_commissioning_mode.id,
                is_client=True,
                payload=ProxyCommissioningModeSchema(**schema_kwargs).serialize(),
            )

            packet = t.ZigbeePacket(
                dst=t.AddrModeAddress(
                    addr_mode=t.AddrMode.Broadcast,
                    address=t.BroadcastAddress.ALL_ROUTERS_AND_COORDINATOR,
                ),
                dst_ep=t.uint8_t(GP_ENDPOINT),
                src_ep=t.uint8_t(GP_ENDPOINT),
                profile_id=t.uint16_t(zgp_profile.PROFILE_ID),
                cluster_id=t.uint16_t(GP_CLUSTER_ID),
                data=t.SerializableBytes(frame_data),
            )

            await self._application.send_packet(packet)
        except Exception:  # noqa: BLE001
            LOGGER.warning(
                "Failed to send GP Proxy Commissioning Mode",
                exc_info=True,
            )

    async def send_pairing(
        self,
        device: GPDevice,
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
        coordinator_ieee = self._application.state.node_info.ieee
        coordinator_nwk = self._application.state.node_info.nwk

        if proxy_nwk is not None:
            comm_mode = CommunicationMode.UnicastLightweight
        else:
            comm_mode = CommunicationMode.GroupcastForwardToDGroup

        options = PairingOptions(
            application_id=zgptypes.ApplicationID.SrcID,
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
            "gpd_id": zgptypes.DeviceID(device.source_id),
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
                # Encrypt the key for transport in the GP Pairing (A.3.7.1.2.3).
                # Proxies receive the encrypted key and decrypt it with the GP
                # link key to populate their proxy tables.
                encrypted_key, _ = encrypt_security_key(
                    device.source_id, bytes(device.security_key)
                )
                schema_kwargs["key"] = t.KeyData(encrypted_key)

        try:
            frame_data = self._build_zcl_frame(
                command_id=GreenPowerProxy.ClientCommandDefs.pairing.id,
                is_client=True,
                payload=PairingSchema(**schema_kwargs).serialize(),
            )

            packet = t.ZigbeePacket(
                dst=t.AddrModeAddress(
                    addr_mode=t.AddrMode.Broadcast,
                    address=t.BroadcastAddress.ALL_ROUTERS_AND_COORDINATOR,
                ),
                dst_ep=t.uint8_t(GP_ENDPOINT),
                src_ep=t.uint8_t(GP_ENDPOINT),
                profile_id=t.uint16_t(zgp_profile.PROFILE_ID),
                cluster_id=t.uint16_t(GP_CLUSTER_ID),
                data=t.SerializableBytes(frame_data),
            )

            await self._application.send_packet(packet)
            LOGGER.debug(
                "Sent GP Pairing for 0x%08X (add_sink=%s)",
                device.source_id,
                add_sink,
            )
        except Exception:  # noqa: BLE001
            LOGGER.warning(
                "Failed to send GP Pairing for 0x%08X",
                device.source_id,
                exc_info=True,
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

        response = ResponseSchema(
            options=ResponseOptions(
                application_id=zgptypes.ApplicationID.SrcID,
                transmit_on_endpoint_match=0,
                _reserved=0,
            ),
            temp_master_short_addr=t.uint16_t(temp_master),
            temp_master_tx_channel=TempMasterTxChannel(
                transmit_channel=t.uint4_t(channel - 11), _reserved=0
            ),
            gpd_id=zgptypes.DeviceID(source_id),
            gpd_command_id=t.uint8_t(gpd_command_id),
            gpd_command_payload=t.LVBytes(gpd_command_payload),
        )

        try:
            frame_data = self._build_zcl_frame(
                command_id=GreenPowerProxy.ClientCommandDefs.response.id,
                is_client=True,
                payload=response.serialize(),
            )

            packet = t.ZigbeePacket(
                dst=t.AddrModeAddress(
                    addr_mode=t.AddrMode.Broadcast,
                    address=t.BroadcastAddress.ALL_ROUTERS_AND_COORDINATOR,
                ),
                dst_ep=t.uint8_t(GP_ENDPOINT),
                src_ep=t.uint8_t(GP_ENDPOINT),
                profile_id=t.uint16_t(zgp_profile.PROFILE_ID),
                cluster_id=t.uint16_t(GP_CLUSTER_ID),
                data=t.SerializableBytes(frame_data),
            )

            await self._application.send_packet(packet)
            LOGGER.debug(
                "Sent GP Response (cmd=0x%02X) for GPD 0x%08X via proxy 0x%04X",
                gpd_command_id,
                source_id,
                temp_master,
            )
        except Exception:  # noqa: BLE001
            LOGGER.warning(
                "Failed to send GP Response for 0x%08X",
                source_id,
                exc_info=True,
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

    @staticmethod
    def _build_zcl_frame(command_id: int, is_client: bool, payload: bytes) -> bytes:
        """Build a ZCL frame for GP cluster commands."""
        direction = (
            foundation.Direction.Client_to_Server
            if is_client
            else foundation.Direction.Server_to_Client
        )

        hdr = foundation.ZCLHeader(
            frame_control=foundation.FrameControl(
                frame_type=foundation.FrameType.CLUSTER_COMMAND,
                is_manufacturer_specific=False,
                direction=direction,
                disable_default_response=True,
                reserved=0b000,
            ),
            tsn=0,
            command_id=command_id,
        )

        return hdr.serialize() + payload
