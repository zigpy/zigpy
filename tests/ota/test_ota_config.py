from __future__ import annotations

import asyncio
import pathlib
from unittest.mock import patch

import zigpy.config as config
import zigpy.device
import zigpy.ota
import zigpy.types as t

from tests.conftest import make_app


async def test_ota_disabled(tmp_path: pathlib.Path) -> None:
    # Enable all the providers
    ota = zigpy.ota.OTA(
        config={
            config.CONF_OTA_ENABLED: False,  # But disable OTA
            config.CONF_OTA_ADVANCED_DIR: tmp_path,
            config.CONF_OTA_ALLOW_ADVANCED_DIR: True,
            config.CONF_OTA_IKEA: True,
            config.CONF_OTA_INOVELLI: True,
            config.CONF_OTA_LEDVANCE: True,
            config.CONF_OTA_SALUS: True,
            config.CONF_OTA_SONOFF: True,
            config.CONF_OTA_THIRDREALITY: True,
            config.CONF_OTA_REMOTE_PROVIDERS: [
                {
                    config.CONF_OTA_PROVIDER_URL: "https://example.org/remote_index.json",
                    config.CONF_OTA_PROVIDER_MANUF_IDS: [0x1234, 4476],
                }
            ],
            config.CONF_OTA_Z2M_LOCAL_INDEX: tmp_path / "index.json",
            config.CONF_OTA_Z2M_REMOTE_INDEX: "https://example.org/z2m_index.json",
        },
        application=None,
    )

    # None are actually enabled
    assert not ota._providers


async def test_ota_enabled(tmp_path: pathlib.Path) -> None:
    # Enable all the providers
    ota = zigpy.ota.OTA(
        config={
            config.CONF_OTA_ENABLED: True,
            config.CONF_OTA_BROADCAST_ENABLED: False,
            config.CONF_OTA_ADVANCED_DIR: tmp_path,
            config.CONF_OTA_ALLOW_ADVANCED_DIR: True,
            config.CONF_OTA_IKEA: True,
            config.CONF_OTA_INOVELLI: True,
            config.CONF_OTA_LEDVANCE: True,
            config.CONF_OTA_SALUS: True,
            config.CONF_OTA_SONOFF: True,
            config.CONF_OTA_THIRDREALITY: True,
            config.CONF_OTA_REMOTE_PROVIDERS: [
                {
                    config.CONF_OTA_PROVIDER_URL: "https://example.org/remote_index.json",
                    config.CONF_OTA_PROVIDER_MANUF_IDS: [0x1234, 4476],
                }
            ],
            config.CONF_OTA_Z2M_LOCAL_INDEX: tmp_path / "index.json",
            config.CONF_OTA_Z2M_REMOTE_INDEX: "https://example.org/z2m_index.json",
        },
        application=None,
    )

    # All are enabled
    assert len(ota._providers) == 10


async def test_ota_broadcast_loop() -> None:
    app = make_app(
        {
            config.CONF_OTA: {
                config.CONF_OTA_ENABLED: True,
                config.CONF_OTA_BROADCAST_ENABLED: True,
                config.CONF_OTA_BROADCAST_INITIAL_DELAY: 0.1,
                config.CONF_OTA_BROADCAST_INTERVAL: 0.2,
            }
        }
    )

    with patch.object(
        app.ota,
        "broadcast_notify",
        side_effect=[None, None, RuntimeError(), None, None, None],
    ) as mock_broadcast_notify:
        await app.startup()
        assert app.ota._broadcast_loop_task is not None
        await asyncio.sleep(1)
        await app.shutdown()

    assert app.ota._broadcast_loop_task is None
    assert len(mock_broadcast_notify.mock_calls) == 5


async def test_ota_broadcast() -> None:
    app = make_app({config.CONF_OTA: {config.CONF_OTA_ENABLED: True}})

    await app.startup()
    app.send_packet.reset_mock()
    await app.ota.broadcast_notify()
    await app.shutdown()

    assert len(app.send_packet.mock_calls) == 1
    assert app.send_packet.mock_calls[0].args[0].dst.addr_mode == t.AddrMode.Broadcast
