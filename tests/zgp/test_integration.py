"""Integration tests for Green Power with ControllerApplication."""

from __future__ import annotations

from tests.async_mock import AsyncMock, Mock

import zigpy.types as t
from zigpy.zgp.manager import GreenPowerManager
from zigpy.zgp.types import (
    GP_CLUSTER_ID,
    GP_ENDPOINT,
)

from tests.conftest import (
    app,
    add_initialized_device
)


def test_app_has_gp_manager():
    """Application should have a green_power manager attribute."""
    assert hasattr(app, "green_power")
    assert isinstance(app.green_power, GreenPowerManager)


def test_gp_manager_references_app():
    """GP manager should reference its parent application."""
    assert app.green_power._application is app


async def test_packet_received_routes_gp_to_manager():
    """GP packets should be routed to the GP manager."""
    # Patch the GP manager's handle_packet
    app.green_power.handle_packet = Mock(return_value=True)

    # Create a GP notification packet from a known proxy device
    # First add a "proxy" device to the app so get_device_with_address works
    proxy_ieee = t.EUI64.convert("00:11:22:33:44:55:66:88")
    proxy_nwk = t.NWK(0x1234)
    add_initialized_device(app, nwk=proxy_nwk, ieee=proxy_ieee)

    packet = t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=proxy_nwk),
        src_ep=t.uint8_t(GP_ENDPOINT),
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x0000)),
        dst_ep=t.uint8_t(GP_ENDPOINT),
        profile_id=t.uint16_t(0xA1E0),
        cluster_id=t.uint16_t(GP_CLUSTER_ID),
        data=t.SerializableBytes(b"\x01\x00\x00" + b"\x00" * 20),
    )

    app.packet_received(packet)

    # GP manager should have been called
    app.green_power.handle_packet.assert_called_once_with(packet)


async def test_non_gp_packet_not_routed_to_manager():
    """Non-GP packets should NOT be routed to the GP manager."""
    app.green_power.handle_packet = Mock(return_value=True)

    dev_ieee = t.EUI64.convert("00:11:22:33:44:55:66:99")
    dev_nwk = t.NWK(0x5678)
    add_initialized_device(app, nwk=dev_nwk, ieee=dev_ieee)

    packet = t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=dev_nwk),
        src_ep=t.uint8_t(1),
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x0000)),
        dst_ep=t.uint8_t(1),
        profile_id=t.uint16_t(0x0104),  # HA profile
        cluster_id=t.uint16_t(0x0006),  # On/Off
        data=t.SerializableBytes(b"\x01\x00\x00"),
    )

    app.packet_received(packet)

    # GP manager should NOT have been called
    app.green_power.handle_packet.assert_not_called()


async def test_gp_packet_from_unknown_device():
    """GP packets from unknown devices should still be routed to GP manager."""
    app.green_power.handle_packet = Mock(return_value=True)

    # Don't add any device - the source is "unknown"
    packet = t.ZigbeePacket(
        src=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x9999)),
        src_ep=t.uint8_t(GP_ENDPOINT),
        dst=t.AddrModeAddress(addr_mode=t.AddrMode.NWK, address=t.NWK(0x0000)),
        dst_ep=t.uint8_t(GP_ENDPOINT),
        profile_id=t.uint16_t(0xA1E0),
        cluster_id=t.uint16_t(GP_CLUSTER_ID),
        data=t.SerializableBytes(b"\x01\x00\x00" + b"\x00" * 10),
    )

    app.packet_received(packet)

    # GP packets should be intercepted BEFORE the unknown device check
    app.green_power.handle_packet.assert_called_once_with(packet)


async def test_permit_gp():
    """permit_gp should delegate to GP manager."""
    app.green_power.permit_join = AsyncMock()

    await app.permit_gp(time_s=120)

    app.green_power.permit_join.assert_called_once_with(120)


async def test_permit_gp_close():
    """permit_gp(0) should close the window."""
    app.green_power.permit_join = AsyncMock()

    await app.permit_gp(time_s=0)

    app.green_power.permit_join.assert_called_once_with(0)
