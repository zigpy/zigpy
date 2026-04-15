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
import time
from typing import TYPE_CHECKING, Any

import zigpy.types as t
from zigpy.zcl.clusters.greenpower import (
    GreenPowerProxy,
    PairingOptions,
    PairingSchema,
    ProxyCommissioningModeOptions,
    ProxyCommissioningModeSchema,
    ResponseOptions,
    ResponseSchema,
)
import zigpy.zgp.types as zgptypes
from zigpy.zgp.crypto import decrypt_payload
from zigpy.zgp.device import GPDevice
from zigpy.zgp.proxy import GPProxyTable
from zigpy.zgp.frame import (
    GPChannelRequestPayload,
    GPCommissioningPayload,
)
from zigpy.zgp.types import (
    GP_CLUSTER_ID,
    GP_ENDPOINT,
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


class GreenPowerManager:
    """Central manager for Green Power protocol handling.

    Attached to ControllerApplication. Processes GP frames arriving
    on endpoint 242, cluster 0x0021.

    Fires the following listener events on the application:
    - ``gp_device_joined(gp_device)``: A new GP device was commissioned
    - ``gp_device_left(gp_device)``: A GP device was decommissioned
    - ``gp_command_received(gp_device, command_id, payload)``: A GP command
      was received from a commissioned device
    """

    # Duplicate filtering timeout per ZGP spec A.3.6.1.2
    DEDUP_TIMEOUT_S: float = 2.0

    def __init__(self, application: ControllerApplication) -> None:
        self._application = application
        self._devices: dict[int, GPDevice] = {}  # sourceID -> GPDevice
        self._commissioning_window_end: float = 0
        self._commissioning_task: asyncio.Task[None] | None = None
        self.proxy_table: GPProxyTable = GPProxyTable()
        # Duplicate filtering table: (source_id, frame_counter) -> monotonic timestamp
        self._dedup_cache: dict[tuple[int, int], float] = {}

    async def shutdown(self) -> None:
        """Clean up GP manager state.

        Cancels any running commissioning timer. Should be called
        during ControllerApplication shutdown.
        """
        if self._commissioning_task is not None:
            self._commissioning_task.cancel()
            self._commissioning_task = None
        self._commissioning_window_end = 0

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

        Per ZGP spec A.3.6.1.2, the sink maintains a duplicate filtering
        table indexed by (sourceID, frameCounter) with a 2-second timeout.
        Multiple proxies forwarding the same GPD frame is normal behavior
        and should be silently deduplicated, not treated as a replay attack.
        """
        key = (source_id, frame_counter)
        now = time.monotonic()

        # Purge expired entries
        self._dedup_cache = {
            k: ts
            for k, ts in self._dedup_cache.items()
            if now - ts < self.DEDUP_TIMEOUT_S
        }

        if key in self._dedup_cache:
            LOGGER.debug(
                "GP dedup: dropping duplicate from 0x%08X (fc=%d)",
                source_id,
                frame_counter,
            )
            return True

        self._dedup_cache[key] = now
        return False

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
            # Parse the ZCL frame to extract command and payload
            data = packet.data.serialize()
            if len(data) < 3:
                LOGGER.debug("GP packet too short: %d bytes", len(data))
                return False

            # ZCL frame: frame_control(1) + seq_num(1) + command_id(1) + payload
            frame_control = data[0]
            # seq_num = data[1]
            zcl_command_id = data[2]
            zcl_payload = data[3:]

            # Determine if this is cluster-specific (bit 0 of frame_control)
            is_cluster_specific = bool(frame_control & 0x01)
            if not is_cluster_specific:
                LOGGER.debug("GP frame is not cluster-specific, ignoring")
                return False

            # Direction bit (bit 3): 0 = client-to-server, 1 = server-to-client
            is_server_to_client = bool(frame_control & 0x08)

            # Get proxy NWK address from packet source
            proxy_nwk = None
            if packet.src and packet.src.addr_mode == t.AddrMode.NWK:
                proxy_nwk = packet.src.address

            self._application.create_task(
                self._process_zcl_command(
                    zcl_command_id, zcl_payload, is_server_to_client, proxy_nwk
                ),
                f"gp_process_command-0x{zcl_command_id:02x}",
            )
            return True

        except Exception:
            LOGGER.debug("Error processing GP packet", exc_info=True)
            return False

    async def _process_zcl_command(
        self,
        command_id: int,
        payload: bytes,
        is_server_to_client: bool,
        proxy_nwk: int | None,
    ) -> None:
        """Process a parsed ZCL command on the GP cluster.

        Server commands (from proxy to sink/coordinator):
        - 0x00: GP Notification
        - 0x01: GP Pairing Search
        - 0x04: GP Commissioning Notification

        Client commands (from sink to proxies):
        - 0x00: GP Notification Response
        - 0x01: GP Pairing
        - 0x02: GP Proxy Commissioning Mode
        - 0x06: GP Response
        """
        if not is_server_to_client:
            # Server commands (proxy → sink)
            if command_id == 0x00:
                await self._handle_gp_notification(payload, proxy_nwk)
            elif command_id == 0x04:
                await self._handle_commissioning_notification(payload, proxy_nwk)
            else:
                LOGGER.debug("Unhandled GP server command: 0x%02X", command_id)
        else:
            LOGGER.debug(
                "Received GP client command 0x%02X (unexpected direction)",
                command_id,
            )

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

    async def _handle_commissioning_notification(
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
                    # Key is encrypted - decrypt it
                    try:
                        from zigpy.zgp.crypto import decrypt_security_key

                        security_key = decrypt_security_key(
                            source_id,
                            comm.security_key,
                            comm.key_mic.to_bytes(4, "little")
                            if isinstance(comm.key_mic, int)
                            else comm.key_mic,
                        )
                    except Exception:
                        LOGGER.warning(
                            "Failed to decrypt security key from 0x%08X",
                            source_id,
                        )
                        return
                else:
                    security_key = comm.security_key

        # Create GP device
        device = GPDevice(
            source_id=source_id,
            device_id=comm.device_id,
            security_key=security_key,
            security_level=security_level,
            security_key_type=security_key_type,
            frame_counter=comm.outgoing_counter or frame_counter,
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
        await self.send_pairing(device, add_sink=True)

        # Notify listeners
        self._application.listener_event("gp_device_joined", device)

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
            self._application.listener_event("gp_device_left", device)

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
            LOGGER.warning(
                "Failed to parse Channel Request from 0x%08X", source_id
            )
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
            gpd_command_id=0xF3,  # GP Channel Configuration
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
                from zigpy.zgp.crypto import SECURITY_LEVEL_MIC_LENGTH

                mic_length = SECURITY_LEVEL_MIC_LENGTH[device.security_level]
                if mic_length > 0 and len(payload) >= mic_length:
                    encrypted_data = payload[:-mic_length]
                    mic = payload[-mic_length:]
                    decrypted_payload = decrypt_payload(
                        source_id,
                        frame_counter,
                        device.security_key,
                        encrypted_data,
                        mic,
                        device.security_level,
                    )
            except Exception:
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
        self._application.listener_event(
            "gp_command_received",
            device,
            command_id,
            decrypted_payload,
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

        self._commissioning_task = self._application.create_task(
            self._commissioning_window_timer(time_s),
            "gp_commissioning_window_timer",
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
                command_id=0x02,  # proxy_commissioning_mode
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
                profile_id=t.uint16_t(0xA1E0),  # GP profile
                cluster_id=t.uint16_t(GP_CLUSTER_ID),
                data=t.SerializableBytes(frame_data),
            )

            await self._application.send_packet(packet)
        except Exception:
            LOGGER.warning(
                "Failed to send GP Proxy Commissioning Mode",
                exc_info=True,
            )

    async def send_pairing(self, device: GPDevice, add_sink: bool = True) -> None:
        """Broadcast GP Pairing command to all proxies.

        Tells GP Proxy devices to add or remove a GPD from their
        proxy tables and start/stop forwarding its frames.

        Limitation: communication_mode is always UnicastLightweight.
        zigbee-herdsman dynamically chooses between Groupcast and Unicast
        depending on whether the commissioning notification was broadcast
        or unicast. UnicastLightweight works for most home networks but
        may fail in extended networks where groupcast forwarding is needed.

        Limitation: the security key is sent as-is in the Pairing command.
        zigbee-herdsman re-encrypts the key via encryptSecurityKey() before
        placing it in the GP Pairing. This may cause interoperability issues
        with proxies that expect the key to be encrypted in the Pairing.
        In practice, EZSP/Z-Stack firmware manages the GP Sink Table
        internally, so this field is less critical at the application level.

        Args:
            device: The GP device to pair/unpair.
            add_sink: True to add pairing, False to remove.

        """
        coordinator_ieee = self._application.state.node_info.ieee
        coordinator_nwk = self._application.state.node_info.nwk

        # TODO: dynamically select communication mode based on commissioning
        # context (broadcast vs unicast) instead of always UnicastLightweight.
        # See zigbee-herdsman sendPairingCommand() for reference.
        options = PairingOptions(
            application_id=zgptypes.ApplicationID.SrcID,
            add_sink=int(add_sink),
            remove_gpd=int(not add_sink),
            communication_mode=CommunicationMode.UnicastLightweight,
            gpd_fixed=int(device.fixed_location),
            gpd_mac_seq_num_cap=int(device.mac_seq_num_capability),
            security_level=device.security_level,
            security_key_type=device.security_key_type,
            security_frame_counter_present=int(add_sink and device.frame_counter > 0),
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
            schema_kwargs["sink_ieee"] = coordinator_ieee
            schema_kwargs["sink_nwk_addr"] = coordinator_nwk
            schema_kwargs["device_id"] = t.uint8_t(device.device_id)

            if device.frame_counter > 0:
                schema_kwargs["frame_counter"] = t.uint32_t(device.frame_counter)

            if device.security_key is not None:
                # TODO: zigbee-herdsman re-encrypts the key via
                # encryptSecurityKey(sourceID, key) before including it in
                # the Pairing. Investigate whether proxies expect the key
                # encrypted or in cleartext in this field.
                schema_kwargs["key"] = t.KeyData(
                    [t.uint8_t(b) for b in device.security_key]
                )

        try:
            frame_data = self._build_zcl_frame(
                command_id=0x01,  # pairing
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
                profile_id=t.uint16_t(0xA1E0),
                cluster_id=t.uint16_t(GP_CLUSTER_ID),
                data=t.SerializableBytes(frame_data),
            )

            await self._application.send_packet(packet)
            LOGGER.debug(
                "Sent GP Pairing for 0x%08X (add_sink=%s)",
                device.source_id,
                add_sink,
            )
        except Exception:
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
                command_id=0x06,  # GP Response
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
                profile_id=t.uint16_t(0xA1E0),
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
            gpd_command_id=0xF0,  # GP Commissioning Reply
            gpd_command_payload=commissioning_reply_payload,
            proxy_nwk=proxy_nwk,
        )

    # --- Helpers ---

    @staticmethod
    def _build_zcl_frame(command_id: int, is_client: bool, payload: bytes) -> bytes:
        """Build a minimal ZCL frame for GP cluster commands.

        Args:
            command_id: ZCL command ID.
            is_client: True for client-to-server direction.
            payload: Serialized command payload.

        Returns:
            Complete ZCL frame bytes.

        """
        # ZCL Frame Control byte (ZCL spec 2.4.1.1):
        # Bits 0-1: Frame type (0b01 = cluster-specific)
        # Bit 2:    Manufacturer specific (0 = no)
        # Bit 3:    Direction (0 = client-to-server, 1 = server-to-client)
        # Bit 4:    Disable default response (1 = yes)
        frame_control = 0x01  # cluster-specific
        if not is_client:
            frame_control |= 0x08  # bit 3: server-to-client direction
        frame_control |= 0x10  # bit 4: disable default response

        seq_num = 0x00  # GP doesn't use seq numbers meaningfully

        return bytes([frame_control, seq_num, command_id]) + payload

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
