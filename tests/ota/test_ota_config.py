from __future__ import annotations

import asyncio
import pathlib
from unittest.mock import patch

import pytest
import voluptuous as vol

from tests.conftest import make_app
from zigpy import config
import zigpy.device
import zigpy.ota
import zigpy.types as t


async def test_ota_disabled_legacy(tmp_path: pathlib.Path) -> None:
    (tmp_path / "index.json").write_text("{}")

    # Enable all the providers
    ota = zigpy.ota.OTA(
        config=config.SCHEMA_OTA(
            {
                config.CONF_OTA_ENABLED: False,  # But disable OTA
                config.CONF_OTA_ADVANCED_DIR: tmp_path,
                config.CONF_OTA_ALLOW_ADVANCED_DIR: config.CONF_OTA_ALLOW_ADVANCED_DIR_STRING,
                config.CONF_OTA_IKEA: True,
                config.CONF_OTA_INOVELLI: True,
                config.CONF_OTA_LEDVANCE: True,
                config.CONF_OTA_SALUS: True,
                config.CONF_OTA_SONOFF: True,
                config.CONF_OTA_THIRDREALITY: True,
                config.CONF_OTA_PROVIDERS: [],
                config.CONF_OTA_EXTRA_PROVIDERS: [],
                config.CONF_OTA_REMOTE_PROVIDERS: [
                    {
                        config.CONF_OTA_PROVIDER_URL: "https://example.org/remote_index.json",
                        config.CONF_OTA_PROVIDER_MANUF_IDS: [0x1234, 4476],
                    }
                ],
                config.CONF_OTA_Z2M_LOCAL_INDEX: tmp_path / "index.json",
                config.CONF_OTA_Z2M_REMOTE_INDEX: "https://example.org/z2m_index.json",
            }
        ),
        application=None,
    )

    # None are actually enabled
    assert not ota._providers


async def test_ota_enabled_legacy(tmp_path: pathlib.Path) -> None:
    (tmp_path / "index.json").write_text("{}")

    # Enable all the providers
    ota = zigpy.ota.OTA(
        config=config.SCHEMA_OTA(
            {
                config.CONF_OTA_ENABLED: True,
                config.CONF_OTA_BROADCAST_ENABLED: False,
                config.CONF_OTA_ADVANCED_DIR: tmp_path,
                config.CONF_OTA_ALLOW_ADVANCED_DIR: config.CONF_OTA_ALLOW_ADVANCED_DIR_STRING,
                config.CONF_OTA_IKEA: True,
                config.CONF_OTA_INOVELLI: True,
                config.CONF_OTA_LEDVANCE: True,
                config.CONF_OTA_SALUS: True,
                config.CONF_OTA_SONOFF: True,
                config.CONF_OTA_THIRDREALITY: True,
                config.CONF_OTA_PROVIDERS: [],
                config.CONF_OTA_EXTRA_PROVIDERS: [],
                config.CONF_OTA_REMOTE_PROVIDERS: [
                    {
                        config.CONF_OTA_PROVIDER_URL: "https://example.org/remote_index.json",
                        config.CONF_OTA_PROVIDER_MANUF_IDS: [0x1234, 4476],
                    }
                ],
                config.CONF_OTA_Z2M_LOCAL_INDEX: tmp_path / "index.json",
                config.CONF_OTA_Z2M_REMOTE_INDEX: "https://example.org/z2m_index.json",
            }
        ),
        application=None,
    )

    # All are enabled
    assert len(ota._providers) == 9


async def test_ota_config(tmp_path: pathlib.Path) -> None:
    # Enable all the providers
    ota = zigpy.ota.OTA(
        config=config.SCHEMA_OTA(
            {
                config.CONF_OTA_ENABLED: True,
                config.CONF_OTA_BROADCAST_ENABLED: False,
                config.CONF_OTA_EXTRA_PROVIDERS: [
                    {
                        config.CONF_OTA_PROVIDER_TYPE: "ikea",
                        config.CONF_OTA_PROVIDER_OVERRIDE_PREVIOUS: True,
                    }
                ],
            }
        ),
        application=None,
    )

    assert ota._providers == [
        zigpy.ota.providers.Ledvance(),
        zigpy.ota.providers.Sonoff(),
        zigpy.ota.providers.Inovelli(),
        zigpy.ota.providers.ThirdReality(),
        zigpy.ota.providers.Tradfri(),
    ]


async def test_ota_config_invalid_message(tmp_path: pathlib.Path) -> None:
    with pytest.raises(vol.Invalid):
        zigpy.ota.OTA(
            config=config.SCHEMA_OTA(
                {
                    config.CONF_OTA_ENABLED: True,
                    config.CONF_OTA_BROADCAST_ENABLED: False,
                    config.CONF_OTA_PROVIDERS: [
                        {
                            config.CONF_OTA_PROVIDER_TYPE: "advanced",
                            config.CONF_OTA_PROVIDER_WARNING: "oops",
                            config.CONF_OTA_PROVIDER_PATH: tmp_path,
                        }
                    ],
                }
            ),
            application=None,
        )


async def test_ota_config_invalid_provider(tmp_path: pathlib.Path) -> None:
    with pytest.raises(vol.Invalid):
        zigpy.ota.OTA(
            config=config.SCHEMA_OTA(
                {
                    config.CONF_OTA_ENABLED: True,
                    config.CONF_OTA_BROADCAST_ENABLED: False,
                    config.CONF_OTA_PROVIDERS: [
                        {
                            config.CONF_OTA_PROVIDER_TYPE: "oops",
                        }
                    ],
                }
            ),
            application=None,
        )


async def test_ota_config_complex(tmp_path: pathlib.Path) -> None:
    # Enable all the providers
    ota = zigpy.ota.OTA(
        config=config.SCHEMA_OTA(
            {
                config.CONF_OTA_ENABLED: True,
                config.CONF_OTA_BROADCAST_ENABLED: False,
                config.CONF_OTA_DISABLE_DEFAULT_PROVIDERS: [
                    "ikea",
                    "sonoff",
                    "ledvance",
                ],
                config.CONF_OTA_EXTRA_PROVIDERS: [
                    {
                        config.CONF_OTA_PROVIDER_TYPE: "ikea",
                        config.CONF_OTA_PROVIDER_URL: "https://ikea1.example.org/",
                    },
                    {
                        config.CONF_OTA_PROVIDER_TYPE: "ikea",
                        config.CONF_OTA_PROVIDER_URL: "https://ikea2.example.org/",
                        config.CONF_OTA_PROVIDER_MANUF_IDS: [0x1234, 0x5678],
                    },
                    {
                        config.CONF_OTA_PROVIDER_TYPE: "z2m",
                        config.CONF_OTA_PROVIDER_URL: "https://z2m.example.org/",
                    },
                    {
                        config.CONF_OTA_PROVIDER_TYPE: "ikea",
                        config.CONF_OTA_PROVIDER_OVERRIDE_PREVIOUS: True,
                        config.CONF_OTA_PROVIDER_URL: "https://ikea3.example.org/",
                        config.CONF_OTA_PROVIDER_MANUF_IDS: [0xABCD, 0xDCBA],
                    },
                    {
                        config.CONF_OTA_PROVIDER_TYPE: "advanced",
                        config.CONF_OTA_PROVIDER_PATH: tmp_path,
                        config.CONF_OTA_PROVIDER_WARNING: config.CONF_OTA_ALLOW_ADVANCED_DIR_STRING,
                    },
                ],
            }
        ),
        application=None,
    )

    assert ota._providers == [
        # zigpy.ota.providers.Ledvance(),
        # zigpy.ota.providers.Sonoff(),
        zigpy.ota.providers.Inovelli(),
        zigpy.ota.providers.ThirdReality(),
        zigpy.ota.providers.RemoteZ2MProvider(url="https://z2m.example.org/"),
        zigpy.ota.providers.Tradfri(
            url="https://ikea3.example.org/",
            manufacturer_ids=[0xABCD, 0xDCBA],
        ),
        zigpy.ota.providers.AdvancedFileProvider(path=tmp_path),
    ]


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
