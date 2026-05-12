"""Green Power Manager.

Central manager for Green Power protocol handling. Processes GP Notification
and GP Commissioning Notification ZCL commands arriving on cluster 0x0021,
endpoint 242. Manages GP device lifecycle (commissioning, decommissioning)
and dispatches GP commands to listeners.

This is the equivalent of zigbee-herdsman's `greenPower.ts`.
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
    PairingOptions,
    PairingSchema,
    ProxyCommissioningModeOptions,
    ProxyCommissioningModeSchema,
    ResponseOptions,
    ResponseSchema,
)
from zigpy.zgp.crypto import (
    SECURITY_LEVEL_MIC_LENGTH,
    decrypt_payload,
    decrypt_security_key,
    encrypt_security_key,
)
from zigpy.zgp.device import GPDevice
from zigpy.zgp.events import CommandReceived, DeviceJoined, DeviceLeft
from zigpy.zgp.frame import GPChannelRequestPayload, GPCommissioningPayload
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

# Default commissioning window duration in seconds
DEFAULT_COMMISSIONING_WINDOW_S: int = 180


class GreenPowerManager(EventBase):
    """Central manager for Green Power protocol handling.

    Attached to ControllerApplication. Processes GP frames arriving
    on endpoint 242, cluster 0x0021.

    Limitation: only ApplicationID.SrcID (0b000) is supported. GPDs using
    ApplicationID.IEEE (0b010) are not handled. This matches zigbee-herdsman
    which also only supports SrcID. No known consumer GPD uses IEEE mode.

    Emits the following events (subscribe via :meth:`on_event`):

    - :class:`~zigpy.zgp.events.DeviceJoined` when a GPD completes
      commissioning.
    - :class:`~zigpy.zgp.events.DeviceLeft` when a GPD is decommissioned.
    - :class:`~zigpy.zgp.events.CommandReceived` when a commissioned
      GPD emits an operational command.
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
        """Create a task owned by the manager.

        The task is stored until completion so :meth:`shutdown` can
        cancel pending work. This keeps the GP lifecycle self-contained
        rather than leaking tasks into the application.
        """
        task = asyncio.get_running_loop().create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def shutdown(self) -> None:
        """Cancel pending work and reset state.

        Called during :meth:`ControllerApplication.shutdown`. All
        background tasks spawned from incoming GP frames and the
        commissioning-window timer are cancelled here.
        """
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
        """Check if a GP notification is a duplicate from another proxy.

        Per ZGP spec A.3.6.1.2 the sink drops any ``(sourceID,
        frame_counter)`` pair seen again within ``DEDUP_TIMEOUT_S``.
        Multiple proxies forwarding the same GPDF is normal behaviour
        and must not be treated as a replay attack.
        """
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
        """Process a packet if it's a GP frame.

        Called from ControllerApplication.packet_received() when
        dst_ep == 242 and cluster_id == 0x0021.

        This method is synchronous and dispatches async processing
        as background tasks.

        Args:
            packet: Incoming ZigbeePacket.

        Returns:
            True if the packet was handled as a GP frame, False otherwise.

        """
        if packet.dst_ep != GP_ENDPOINT or packet.cluster_id != GP_CLUSTER_ID:
            return False

        try:
            # Parse the ZCL header using zigpy's ZCLHeader struct
            data = packet.data.serialize()
            hdr, zcl_payload = foundation.ZCLHeader.deserialize(data)
        except (ValueError, IndexError, KeyError, AttributeError):
            LOGGER.debug("Error processing GP packet", exc_info=True)
            return False

        if hdr.frame_control.frame_type != foundation.FrameType.CLUSTER_COMMAND:
            LOGGER.debug("GP frame is not cluster-specific, ignoring")
            return False

        is_server_to_client = (
            hdr.frame_control.direction == foundation.Direction.Server_to_Client
        )

        # Get proxy NWK address from packet source
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

        Only server-to-sink commands are consumed here. Client commands
        (sink → proxy) are sent by this manager, never received.
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
        """Handle a GP Notification command (server command 0x00).

        This is the main data path for GP devices. A GP Proxy has
        received a GPDF and forwarded it as a GP Notification.

        Notification payload structure (after ZCL header):
        - options (2 bytes)
        - gpd_id (4 bytes)
        - frame_counter (4 bytes)
        - command_id (1 byte)
        - payload (variable, length-prefixed)
        - [optional] short_addr (2 bytes)
        - [optional] distance (1 byte)
        """
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

        # Track the proxy that forwarded this notification
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

        # Check if this is a commissioning-related command
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

        # Regular data command - dispatch to listeners
        await self._dispatch_gp_command(
            source_id, frame_counter, gpd_command_id, gpd_payload
        )

    async def _handle_commissioning_notification(  # pragma: no cover
        self, payload: bytes, proxy_nwk: int | None
    ) -> None:
        """Handle a GP Commissioning Notification command (server command 0x04).

        This arrives during the commissioning window when a proxy
        forwards a GPD's commissioning frame.
        """
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
        """Process a GP Commissioning command (0xE0).

        Creates a new GPDevice, configures security, and sends
        GP Pairing to all proxies. For RX-capable GPDs, sends a
        GP Commissioning Reply via the forwarding proxy.
        """
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
            comm = GPCommissioningPayload.from_bytes(payload)
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

        # Determine security configuration
        security_level = SecurityLevel.NoSecurity
        security_key_type = SecurityKeyType.NoKey
        security_key = None

        if comm.extended_options is not None:
            security_level = comm.extended_options.security_level
            security_key_type = comm.extended_options.key_type

            if comm.extended_options.key_present and comm.security_key is not None:
                if comm.extended_options.key_encrypted and comm.key_mic is not None:
                    mic_bytes = struct.pack("<I", comm.key_mic)
                    try:
                        key_data = decrypt_security_key(
                            source_id, comm.security_key, mic_bytes
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

        # Create GP device
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
            gpd_commands=comm.gpd_commands,
            server_clusters=comm.server_clusters,
            client_clusters=comm.client_clusters,
            mac_seq_num_capability=comm.options.mac_seq_num_capability,
            rx_on_capability=comm.options.rx_on_capability,
            fixed_location=comm.options.fixed_location,
        )

        # Register the device
        self.add_device(device)

        if device.rx_on_capability:
            await self._send_commissioning_reply(source_id, proxy_nwk)

        # Send GP Pairing to proxies
        await self.send_pairing(device, add_sink=True, proxy_nwk=proxy_nwk)

        # Notify listeners
        self.emit(DeviceJoined.event_type, DeviceJoined(device=device))

        LOGGER.info(
            "GP device commissioned: %r",
            device,
        )

    async def _process_decommissioning(self, source_id: int) -> None:
        """Process a GP Decommissioning command (0xE1)."""
        device = self.remove_device(source_id)

        if device is not None:
            # Clean up proxy table entries for this device
            self.proxy_table.remove_by_source_id(source_id)

            # Send GP Pairing (remove) to proxies
            await self.send_pairing(device, add_sink=False)

            # Notify listeners
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
        """Process a GP Channel Request command (0xE3).

        The GPD is asking which channel to use. We respond with a
        GP Channel Configuration (0xF3) containing the coordinator's
        current operating channel.
        """
        try:
            channel_req = GPChannelRequestPayload.from_bytes(payload)
        except (ValueError, IndexError):
            LOGGER.warning("Failed to parse Channel Request from 0x%08X", source_id)
            return

        channel = self._application.state.network_info.channel

        LOGGER.debug(
            "GP Channel Request from 0x%08X: next=%d, second=%d, "
            "responding with channel %d",
            source_id,
            channel_req.next_channel,
            channel_req.second_next_channel,
            channel,
        )

        # GP Channel Configuration payload (1 byte):
        # Bits 0-3: operational channel (offset from 11)
        # Bit 4: basic (1 = basic operation, 0 = enhanced)
        # Bits 5-7: reserved
        channel_config_byte = ((channel - 11) & 0x0F) | 0x10  # basic=1

        await self._send_gp_response(
            source_id=source_id,
            gpd_command_id=GPDCommandID.ChannelConfiguration,
            gpd_command_payload=bytes([channel_config_byte]),
            proxy_nwk=proxy_nwk,
        )

    # --- Command dispatch ---

    async def _dispatch_gp_command(
        self,
        source_id: int,
        frame_counter: int,
        command_id: int,
        payload: bytes,
    ) -> None:
        """Dispatch a GP data command from a commissioned device.

        Verifies the frame counter, decrypts if necessary, and fires
        the gp_command_received listener event.
        """
        device = self.get_device(source_id)

        if device is None:
            LOGGER.debug(
                "GP command from unknown device 0x%08X (cmd=0x%02X)",
                source_id,
                command_id,
            )
            return

        # Frame counter replay protection
        if not device.update_frame_counter(frame_counter):
            return

        # Decrypt payload if security is active
        decrypted_payload = payload
        if (
            device.security_level != SecurityLevel.NoSecurity
            and device.security_key is not None
            and payload
        ):
            try:
                # For encrypted payloads, the MIC is appended to the payload
                mic_length = SECURITY_LEVEL_MIC_LENGTH[device.security_level]
                if mic_length > 0 and len(payload) >= mic_length:
                    encrypted_data = payload[:-mic_length]
                    mic = payload[-mic_length:]
                    decrypted_payload = decrypt_payload(
                        source_id,
                        frame_counter,
                        bytes(device.security_key),
                        encrypted_data,
                        mic,
                        device.security_level,
                    )
            except Exception:  # noqa: BLE001
                LOGGER.warning(
                    "Failed to decrypt GP payload from 0x%08X",
                    source_id,
                    exc_info=True,
                )
                return

        LOGGER.debug(
            "GP command from 0x%08X: cmd=0x%02X, payload=%s",
            source_id,
            command_id,
            decrypted_payload.hex() if decrypted_payload else "empty",
        )

        # Fire listener event
        self.emit(
            CommandReceived.event_type,
            CommandReceived(
                device=device,
                command_id=GPDCommandID(command_id),
                payload=decrypted_payload,
            ),
        )

    # --- Commissioning window control ---

    async def permit_join(self, time_s: int = DEFAULT_COMMISSIONING_WINDOW_S) -> None:
        """Open the GP commissioning window.

        Broadcasts a ProxyCommissioningMode command to all routers
        telling them to enter commissioning mode and forward
        GP commissioning frames.

        Args:
            time_s: Duration of the commissioning window in seconds.
                   Pass 0 to close the window immediately.

        """
        if time_s == 0:
            await self._close_commissioning_window()
            return

        self._commissioning_window_end = time.monotonic() + time_s

        LOGGER.info("Opening GP commissioning window for %d seconds", time_s)

        # Send ProxyCommissioningMode (enter)
        await self._send_proxy_commissioning_mode(enter=True, window=time_s)

        # Schedule window closure
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

        # Send ProxyCommissioningMode (exit)
        await self._send_proxy_commissioning_mode(enter=False)

    # --- Outgoing GP commands ---

    async def _send_proxy_commissioning_mode(
        self, enter: bool, window: int | None = None
    ) -> None:
        """Send GP Proxy Commissioning Mode command.

        Broadcasts to all routers and coordinator (0xFFFC) to
        enter or exit GP commissioning mode.

        Args:
            enter: True to enter commissioning, False to exit.
            window: Commissioning window duration in seconds (optional).

        """
        options = ProxyCommissioningModeOptions(
            enter=int(enter),
            exit_mode=zgptypes.ProxyCommissioningModeExitMode.OnExpire
            if enter
            else zgptypes.ProxyCommissioningModeExitMode.NotDefined,
            channel_present=0,
            unicast=0,
            _reserved=0,
        )

        schema_kwargs: dict[str, Any] = {"options": options}
        if window is not None and enter:
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
                profile_id=t.uint16_t(zgp_profile.PROFILE_ID),  # GP profile
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
        """Broadcast GP Pairing command to all proxies.

        Tells GP Proxy devices to add or remove a GPD from their
        proxy tables and start/stop forwarding its frames.

        The communication mode is selected based on context: if a specific
        proxy forwarded the commissioning notification (proxy_nwk provided),
        UnicastLightweight is used. Otherwise, GroupcastForwardToDGroup is
        used to reach all proxies via the GP group. This matches
        zigbee-herdsman's sendPairingCommand() behavior.

        Args:
            device: The GP device to pair/unpair.
            add_sink: True to add pairing, False to remove.
            proxy_nwk: NWK address of the proxy that forwarded the
                commissioning notification. If None, groupcast is used.

        """
        coordinator_ieee = self._application.state.node_info.ieee
        coordinator_nwk = self._application.state.node_info.nwk

        # Select communication mode based on commissioning context
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
            forwarding_radius_present=0,
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
                # Encrypt the key for transport in the GP Pairing, matching
                # zigbee-herdsman's sendPairingCommand() behavior. Proxies
                # receive the encrypted key and can decrypt it with the GP
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
        """Send a GP Response command via a proxy (temp master).

        The GP Response (client command 0x06) instructs a proxy to transmit
        a GPDF to a GPD during its rxAfterTx window. Used for Channel
        Configuration (0xF3) and Commissioning Reply (0xF0).

        Args:
            source_id: Target GPD source identifier.
            gpd_command_id: GPD command to send (0xF0, 0xF3, etc.).
            gpd_command_payload: Payload for the GPD command.
            proxy_nwk: NWK address of the proxy to use as temp master.
                If None, the coordinator address is used.

        """
        channel = self._application.state.network_info.channel
        temp_master = proxy_nwk or self._application.state.node_info.nwk

        response = ResponseSchema(
            options=ResponseOptions(
                application_id=zgptypes.ApplicationID.SrcID,
                _reserved=0,
            ),
            temp_master_short_addr=t.uint16_t(temp_master),
            temp_master_tx_channel=t.uint8_t(channel - 11),
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

        This is a minimal implementation matching zigbee-herdsman: the reply
        does not include a security key (options=0x00). The GPD will complete
        commissioning but must use a pre-shared (OOB) key or operate without
        security. Full key provisioning via Commissioning Reply would require
        encrypting the key and including it in the payload.

        Args:
            source_id: GPD source identifier.
            proxy_nwk: NWK address of the proxy that forwarded the
                commissioning notification (used as temp master).

        """
        LOGGER.info(
            "Sending GP Commissioning Reply to RX-capable GPD 0x%08X",
            source_id,
        )

        # Commissioning Reply payload (cmd 0xF0):
        # 1 byte options: 0x00 = no PAN ID, no key, no key encryption,
        #                 no security level
        commissioning_reply_payload = bytes([0x00])

        await self._send_gp_response(
            source_id=source_id,
            gpd_command_id=GPDCommandID.CommissioningReply,
            gpd_command_payload=commissioning_reply_payload,
            proxy_nwk=proxy_nwk,
        )

    # --- Helpers ---

    @staticmethod
    def _build_zcl_frame(command_id: int, is_client: bool, payload: bytes) -> bytes:
        """Build a ZCL frame for GP cluster commands.

        Uses zigpy's ZCLHeader for proper frame construction. GP frames
        are sent on the GP profile (0xA1E0) and endpoint (242), outside
        the standard ZCL device/endpoint/cluster lifecycle, but the ZCL
        header format is the same.

        Args:
            command_id: ZCL command ID.
            is_client: True for client-to-server direction.
            payload: Serialized command payload.

        Returns:
            Complete ZCL frame bytes.

        """
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

    # --- Persistence ---

    def load_devices(self, devices_data: list[dict]) -> None:
        """Load GP devices from persisted data.

        Called during startup to restore previously commissioned devices.

        Args:
            devices_data: List of dictionaries from GPDevice.as_dict().

        """
        for data in devices_data:
            try:
                device = GPDevice.from_dict(data)
                self._devices[device.source_id] = device
                LOGGER.debug("Loaded GP device: %r", device)
            except (KeyError, ValueError, TypeError):
                LOGGER.warning(
                    "Failed to load GP device from data: %s",
                    data,
                    exc_info=True,
                )

    def get_devices_data(self) -> list[dict]:
        """Serialize all GP devices for persistence.

        Returns:
            List of dictionaries suitable for JSON/database storage.

        """
        return [device.as_dict() for device in self._devices.values()]
