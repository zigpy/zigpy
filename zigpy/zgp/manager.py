"""Green Power Manager: commissioning of Green Power devices.

Opens and closes the GP commissioning window, handles the GPD commissioning commands
(0xE0-0xE3), and sends the GP cluster commands that configure proxies.
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from cryptography.exceptions import InvalidTag

import zigpy.application
from zigpy.datastructures import Debouncer
from zigpy.device import GP_DUPLICATE_TIMEOUT, GreenPowerDevice
from zigpy.exceptions import DeliveryError
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
import zigpy.zdo.types as zdo_types
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
    GP_GROUP_ID,
    ApplicationID,
    CommunicationMode,
    GPDCommandID,
    ProxyCommissioningModeExitMode,
    SecurityKeyType,
    SecurityLevel,
    SrcID,
)
from zigpy.zgp.util import synthetic_ieee

if TYPE_CHECKING:
    from zigpy.application import ControllerApplication

LOGGER = logging.getLogger(__name__)

# Dmax (A.3.6.3.1): proxies tunnel a GPDF within Dmin + Dmax of its reception, and the
# sink elects the TempMaster from the instances received within Dmax of the first one
# (A.3.6.2.3)
TEMP_MASTER_ELECTION_TIME = 0.100


@dataclasses.dataclass
class _TempMasterCandidates:
    """The instances of a GPD's latest GPDF with RxAfterTx, from all forwarders."""

    generation: int
    frame_counter: int | None
    security_level: SecurityLevel | None
    started: float
    packets: list[t.ZigbeeGpPacket]
    expiry: asyncio.TimerHandle


def _link_value(packet: t.ZigbeeGpPacket) -> tuple[int, int]:
    """Return the GPP-GPD link of a GPDF instance as (Link quality, RSSI)."""
    # Tunneled GPDFs spread the 2-bit Link quality over 0-255, so this recovers it.
    # An instance without a link (a GP 1.0 proxy's Distance) ranks last.
    link_quality = (packet.lqi // 85) if packet.lqi is not None else -1
    rssi = packet.rssi if packet.rssi is not None else -128

    return link_quality, rssi


# How long a GPDF waits for its GPD to listen
GPDF_LIFETIME = timedelta(seconds=20)


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
        # Closes the commissioning window when it expires
        self._window_timer: asyncio.TimerHandle | None = None
        self._window_generation = 0
        self._tasks: set[asyncio.Task[Any]] = set()
        # Commissioning GPDFs come from GPDs that are not registered yet, so
        # `GreenPowerDevice` cannot filter their duplicates (spec A.3.6.1.2)
        self._dedup_debouncer: Debouncer = Debouncer()
        # GPDs in bidirectional commissioning, until their Success GPDF arrives or the
        # window closes
        self._pending_devices: dict[t.EUI64, GreenPowerDevice] = {}
        # The latest GPDF with RxAfterTx of each GPD, for gpDuplicateTimeout. A gpTxQueue
        # holds a single GPDF per GPD (A.1.5.2.1.1), so older ones have no use.
        self._temp_master_candidates: dict[t.EUI64, _TempMasterCandidates] = {}

    def _has_devices(self) -> bool:
        return any(
            isinstance(device, GreenPowerDevice)
            for device in self._application.devices.values()
        )

    async def startup(self) -> None:
        """Join the GP group if any GPD is commissioned, to receive their GPDFs."""
        if self._has_devices():
            await self._application.subscribe_to_multicast_group(
                GP_GROUP_ID, endpoint_id=GP_ENDPOINT
            )

    async def shutdown(self) -> None:
        """Cancel commissioning in progress and close the window."""
        self._close_window()

        for candidates in self._temp_master_candidates.values():
            candidates.expiry.cancel()

        self._temp_master_candidates.clear()

        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)

    @property
    def is_commissioning(self) -> bool:
        """Return True if the GP commissioning window is currently open."""
        return self._window_timer is not None

    def _close_window(self) -> None:
        """Close the GP commissioning window, ending commissioning in progress."""
        self._window_generation += 1

        if self._window_timer is not None:
            self._window_timer.cancel()
            self._window_timer = None

        self._pending_devices.clear()

    async def permit_join(self, time_s: int) -> None:
        """Open the GP commissioning window; time_s=0 closes it immediately."""
        if time_s == 0:
            self._close_window()
            await self._send_proxy_commissioning_mode(window=None)
            return

        # Proxies leave commissioning mode on their own once the window expires
        # (A.3.6.3.2), so only an explicit close needs telling them
        await self._send_proxy_commissioning_mode(window=time_s)

        # Extending an open window keeps commissioning in progress
        if self._window_timer is not None:
            self._window_timer.cancel()
        else:
            self._window_generation += 1

        self._window_timer = asyncio.get_running_loop().call_later(
            time_s, self._close_window
        )

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

        assert packet.src_id is not None

        generation = self._window_generation
        key = (generation, packet.src_id, packet.frame_counter)
        ieee = synthetic_ieee(packet.src_id)

        # The GPD listens after a GPDF with RxAfterTx, and after a Channel Request: a
        # Maintenance frame, which has no RxAfterTx (A.3.9.1 step 6.b). Both are only
        # processed in commissioning mode, so outside of it they elect no TempMaster.
        listening = self.is_commissioning and (
            packet.rx_after_tx or packet.command_id == GPDCommandID.ChannelRequest
        )

        if self._dedup_debouncer.filter(key, GP_DUPLICATE_TIMEOUT.total_seconds()):
            LOGGER.debug("Dropping duplicate GP packet: %r", packet)

            if listening:
                self.add_temp_master_candidate(ieee, packet)

            return

        if packet.command_id != GPDCommandID.CommissioningRequest:
            assert packet.command_id == GPDCommandID.ChannelRequest

        if listening:
            self.start_temp_master_election(ieee, packet)

        self.create_task(
            self._process_packet(packet, generation),
            f"gp_process_command-0x{packet.command_id:02x}",
        )

    def start_temp_master_election(
        self, ieee: t.EUI64, packet: t.ZigbeeGpPacket
    ) -> None:
        """Collect TempMaster candidates for an accepted GPDF the GPD listens after."""
        loop = asyncio.get_running_loop()

        # A gpTxQueue holds a single GPDF per GPD (A.1.5.2.1.1), so a newer GPDF
        # replaces the election of the previous one
        if ieee in self._temp_master_candidates:
            self._temp_master_candidates[ieee].expiry.cancel()

        self._temp_master_candidates[ieee] = _TempMasterCandidates(
            generation=self._window_generation,
            frame_counter=packet.frame_counter,
            security_level=packet.security_level,
            started=loop.time(),
            packets=[packet],
            expiry=loop.call_later(
                GP_DUPLICATE_TIMEOUT.total_seconds(),
                self._temp_master_candidates.pop,
                ieee,
            ),
        )

    def add_temp_master_candidate(
        self, ieee: t.EUI64, packet: t.ZigbeeGpPacket
    ) -> None:
        """Add a later instance of an accepted GPDF as a TempMaster candidate.

        The sink processes each later instance of a GPDF with RxAfterTx only as a
        candidate for its election, within Dmax of the first one (A.3.6.1.2).
        """
        if ieee not in self._temp_master_candidates:
            LOGGER.debug("No election for TempMaster candidate: %r", packet)
            return

        candidates = self._temp_master_candidates[ieee]

        if (
            candidates.generation != self._window_generation
            or candidates.frame_counter != packet.frame_counter
            or candidates.security_level != packet.security_level
        ):
            LOGGER.debug("TempMaster candidate for another GPDF: %r", packet)
            return

        elapsed = asyncio.get_running_loop().time() - candidates.started

        if elapsed > TEMP_MASTER_ELECTION_TIME:
            LOGGER.debug("Dropping late TempMaster candidate: %r", packet)
            return

        LOGGER.debug("TempMaster candidate for a GP packet: %r", packet)
        candidates.packets.append(packet)

    async def _process_packet(self, packet: t.ZigbeeGpPacket, generation: int) -> None:
        """Process a GPDF only in the commissioning window in which it arrived."""
        if generation != self._window_generation:
            LOGGER.debug("Dropping GP packet from an earlier commissioning window")
            return

        if packet.command_id == GPDCommandID.CommissioningRequest:
            await self._process_commissioning(packet)
        else:
            await self._process_channel_request(packet)

    def _temp_master_address(self, temp_master: t.ZigbeeGpPacket) -> t.NWK:
        """Return the short address of the node that received a GPDF instance."""
        if temp_master.gpp_short_addr is None:
            return self._application.state.node_info.nwk

        return temp_master.gpp_short_addr

    async def _elect_temp_master(
        self, ieee: t.EUI64, channel: int, *, commissioning: bool
    ) -> t.ZigbeeGpPacket:
        """Elect the node to transmit a GPDF to a GPD on `channel` (A.3.6.2.3).

        Candidates are the instances of the GPD's latest GPDF with RxAfterTx received
        within Dmax of the first one: from proxies with bidirectional capability and
        room in their gpTxQueue, and from the sink itself if its radio can transmit
        the GPDF. The best GPP-GPD link wins and, among equals, the lowest short
        address. Returns the instance received by the elected node.
        """
        loop = asyncio.get_running_loop()

        # A newer GPDF with RxAfterTx replaces the election while it waits for Dmax
        while True:
            if ieee not in self._temp_master_candidates:
                raise DeliveryError(f"No recent GPDF with RxAfterTx from {ieee}")

            candidates = self._temp_master_candidates[ieee]
            elapsed = loop.time() - candidates.started

            if elapsed >= TEMP_MASTER_ELECTION_TIME:
                break

            await asyncio.sleep(TEMP_MASTER_ELECTION_TIME - elapsed)

        # Radio libraries that can transmit GPDFs implement `_send_gpdf`
        radio_sends_gpdfs = (
            type(self._application)._send_gpdf
            is not zigpy.application.ControllerApplication._send_gpdf
        )
        operational_channel = self._application.state.network_info.channel

        if (
            radio_sends_gpdfs
            and channel != operational_channel
            and any(c.gpp_short_addr is None for c in candidates.packets)
        ):
            LOGGER.debug(
                "Sink cannot transmit to %s on channel %d, only on the operational"
                " channel %d",
                ieee,
                channel,
                operational_channel,
            )

        eligible = [
            candidate
            for candidate in candidates.packets
            if (
                (
                    candidate.gpp_short_addr is None
                    and radio_sends_gpdfs
                    # TODO: a sink electing itself to transmit on another channel
                    # switches to it (A.3.9.1 step 7.d.iii), which no radio does yet
                    and channel == operational_channel
                )
                or (
                    candidate.gpp_short_addr is not None
                    and candidate.gpp_bidirectional_cap
                    and not candidate.gpp_tx_queue_full
                )
            )
        ]

        # In commissioning mode, proxies without bidirectional capability in operation
        # transmit as well
        if not eligible and commissioning:
            eligible = [
                candidate
                for candidate in candidates.packets
                if candidate.gpp_short_addr is not None
            ]

        if not eligible:
            raise DeliveryError(f"No TempMaster can transmit to {ieee}")

        temp_master = max(
            eligible,
            key=lambda candidate: (
                *_link_value(candidate),
                -self._temp_master_address(candidate),
            ),
        )

        LOGGER.debug(
            "Elected TempMaster 0x%04X for %s from %d candidate(s)",
            self._temp_master_address(temp_master),
            ieee,
            len(candidates.packets),
        )

        return temp_master

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
            comm, extra_commissioning_payload = GPCommissioningPayload.deserialize(
                packet.payload.serialize()
            )
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
            extra_commissioning_payload=extra_commissioning_payload,
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

                # A Commissioning GPDF older than the last GPDF accepted from the GPD
                # is a replay, or one a slow proxy tunnels after the Success GPDF of
                # bidirectional commissioning. Commissioning the GPD again from it
                # would divert its GPDFs to a pending device until the window closes.
                # Equality is valid if no newer protected GPDF has been received.
                if device.frame_counter < registered.frame_counter:
                    LOGGER.debug(
                        "GP Commissioning from 0x%08X ignored: outgoing counter %d"
                        " is older than %d",
                        source_id,
                        device.frame_counter,
                        registered.frame_counter,
                    )
                    return

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
            new_device = False
        else:
            # The device object was created before it was known to be new, so it may
            # hold the closed store of a GPD removed earlier under the same IEEE
            self._application.device_stores.reopen(device.ieee)
            device._store = self._application.device_stores[device.ieee]
            self._application.listener_event("device_joined", device)
            self._application.device_initialized(device)
            new_device = True

        await self._application.subscribe_to_multicast_group(
            GP_GROUP_ID, endpoint_id=GP_ENDPOINT
        )

        # Only the first commissioning of a GPD announces its alias (A.3.9.1 19.e)
        if new_device:
            await self._send_device_annce(device)

        await self.send_pairing(device, add_sink=True)

        LOGGER.info("GP device commissioned: %r", device)

    def decommission(self, device: GreenPowerDevice) -> None:
        """Remove a GPD whose Decommissioning command (0xE1) passed its checks."""
        self.create_task(
            self._application.remove(device.ieee),
            f"gp_process_command-0x{GPDCommandID.DecommissioningRequest:02x}",
        )

    async def unpair(self, device: GreenPowerDevice) -> None:
        """Remove a GPD from all proxies, and leave the GP group after the last one."""
        try:
            await self.send_pairing(device, add_sink=False)
        except (TimeoutError, DeliveryError) as ex:
            LOGGER.warning("Failed to remove %r from proxies: %s", device, ex)

        if not self._has_devices():
            await self._application.unsubscribe_from_multicast_group(
                GP_GROUP_ID, endpoint_id=GP_ENDPOINT
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
        try:
            await self._send_commissioning_gpdf(
                packet,
                GPDCommandID.ChannelConfiguration,
                channel_config.serialize(),
                maintenance=True,
                channel=request.next_channel + 11,
            )
        except DeliveryError as exc:
            LOGGER.debug("Channel Configuration to 0x%08X not sent: %s", source_id, exc)

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

        # TODO: proxies forward with groupcast, a single NWK broadcast per GPDF. Unicast
        # forwarding through a chosen set of proxies needs zigpy to maintain those
        # proxies as the network changes, from its topology scans.
        options = PairingOptions(
            application_id=ApplicationID.SrcID,
            add_sink=int(add_sink),
            remove_gpd=int(not add_sink),
            communication_mode=CommunicationMode.GroupcastForwardToCommGroup,
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
            schema_kwargs["sink_group"] = GP_GROUP_ID
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

    async def _send_device_annce(self, device: GreenPowerDevice) -> None:
        """Announce the alias of a GPD, to evict a Zigbee device using the address.

        The Device_annce is sent as the alias itself, with a fixed sequence number of
        0 and an invalid IEEE address (A.3.6.3.4.2).
        """
        # Only the security capability is set, inherited from this node (Figure 88)
        capability = zdo_types.MACCapabilityFlags.NONE

        if self._application.state.network_info.security_level > 0:
            capability |= zdo_types.MACCapabilityFlags.SecurityCapable

        tsn = t.uint8_t(0)
        data = tsn.serialize() + t.serialize(
            (device.nwk, t.EUI64.convert("ff:ff:ff:ff:ff:ff:ff:ff"), capability),
            zdo_types.CLUSTERS[zdo_types.ZDOCmd.Device_annce][1],
        )
        packet = t.ZigbeePacket(
            dst=t.AddrModeAddress(
                addr_mode=t.AddrMode.Broadcast,
                address=t.BroadcastAddress.RX_ON_WHEN_IDLE,
            ),
            dst_ep=t.uint8_t(0),
            src_ep=t.uint8_t(0),
            tsn=tsn,
            profile_id=t.uint16_t(0),
            cluster_id=t.uint16_t(zdo_types.ZDOCmd.Device_annce),
            data=t.SerializableBytes(data),
            alias_src=device.nwk,
            alias_seq=t.uint8_t(0),
        )

        try:
            await self._application.send_packet(packet)
        except NotImplementedError:
            # Address conflict detection works on the announced NWKAddr and IEEEAddr
            # (Zigbee 2.4.3.1.11.2, as amended by A.2.6), so sending the same payload
            # as ourselves still evicts a device holding the alias. Only the NWK
            # source and sequence number of A.3.6.3.4.2 are lost.
            LOGGER.debug(
                "Radio cannot send with an alias, announcing 0x%04X as ourselves",
                device.nwk,
            )
            await self._application.send_packet(
                packet.replace(
                    tsn=t.uint8_t(self._application.get_sequence()),
                    alias_src=None,
                    alias_seq=None,
                )
            )

    # --- GPDFs to GPDs ---

    async def send_gpdf(
        self, device: GreenPowerDevice, command_id: GPDCommandID, payload: bytes
    ) -> None:
        """Send a GPDF to a GPD, after its next GPDF with RxAfterTx."""
        channel = self._application.state.network_info.channel
        temp_master = await self._elect_temp_master(
            device.ieee, channel, commissioning=False
        )
        await self._send_gpdf(temp_master, command_id, payload, channel=channel)

    async def _send_commissioning_gpdf(
        self,
        packet: t.ZigbeeGpPacket,
        command_id: GPDCommandID,
        payload: bytes,
        *,
        maintenance: bool = False,
        channel: int | None = None,
    ) -> None:
        """Send a GPDF to a commissioning GPD, after its next GPDF like `packet`."""
        assert packet.src_id is not None

        if channel is None:
            channel = self._application.state.network_info.channel

        generation = self._window_generation
        temp_master = await self._elect_temp_master(
            synthetic_ieee(packet.src_id), channel, commissioning=True
        )

        # The GPD only listens in commissioning mode
        if not self.is_commissioning or generation != self._window_generation:
            LOGGER.debug(
                "GPDF for 0x%08X not sent: commissioning window changed",
                packet.src_id,
            )
            return

        await self._send_gpdf(
            temp_master, command_id, payload, maintenance=maintenance, channel=channel
        )

    async def _send_gpdf(
        self,
        temp_master: t.ZigbeeGpPacket,
        command_id: GPDCommandID,
        payload: bytes,
        *,
        channel: int,
        maintenance: bool = False,
    ) -> None:
        """Send a GPDF through the node that received the `temp_master` instance.

        A Maintenance frame is queued for SrcID 0 (A.1.5.2.2).
        """
        # TODO: `ResponseSchema` cannot carry an IEEE address
        if temp_master.application_id is ApplicationID.IEEE:
            if temp_master.gpp_short_addr is not None:
                raise DeliveryError("Proxies cannot be sent GPDFs for IEEE GPDs yet")
        else:
            assert temp_master.src_id is not None

            # The elected proxy queues the GPDF, and the others drop theirs. The sink
            # announces itself the same way when elected (A.3.6.2.3), before its radio
            # waits for the GPD to listen.
            await self._broadcast_command(
                GreenPowerProxy.ClientCommandDefs.response,
                options=ResponseOptions(
                    application_id=ApplicationID.SrcID,
                    transmit_on_endpoint_match=0,
                    _reserved=0,
                ),
                temp_master_short_addr=t.uint16_t(
                    self._temp_master_address(temp_master)
                ),
                temp_master_tx_channel=TempMasterTxChannel(
                    transmit_channel=t.uint4_t(channel - 11), _reserved=0
                ),
                gpd_id=SrcID(0x00000000) if maintenance else temp_master.src_id,
                gpd_command_id=command_id,
                gpd_command_payload=t.LVBytes(payload),
            )

        if temp_master.gpp_short_addr is None:
            target: SrcID | tuple[t.EUI64, int] | None
            if maintenance:
                target = None
            elif temp_master.application_id is ApplicationID.SrcID:
                assert temp_master.src_id is not None
                target = temp_master.src_id
            else:
                assert temp_master.ieee is not None
                assert temp_master.endpoint is not None
                target = (temp_master.ieee, temp_master.endpoint)

            await self._application.send_gpdf(
                target=target,
                command_id=command_id,
                payload=payload,
                channel=channel,
                lifetime=GPDF_LIFETIME,
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

        # A GPD repeats its Commissioning GPDF until it gets a reply, so a reply that is
        # never sent is not an error
        try:
            await self._send_commissioning_gpdf(
                packet, GPDCommandID.CommissioningReply, reply.serialize()
            )
        except DeliveryError as exc:
            LOGGER.debug("Commissioning Reply to %r not sent: %s", packet.src_id, exc)

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
