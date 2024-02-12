"""OTA support for Zigbee devices."""
from __future__ import annotations

import datetime
import logging

import attr

from zigpy.config import (
    CONF_OTA_ADVANCED_DIR,
    CONF_OTA_ALLOW_ADVANCED_DIR,
    CONF_OTA_IKEA,
    CONF_OTA_INOVELLI,
    CONF_OTA_LEDVANCE,
    CONF_OTA_PROVIDER_MANUF_IDS,
    CONF_OTA_PROVIDER_URL,
    CONF_OTA_REMOTE_PROVIDERS,
    CONF_OTA_SALUS,
    CONF_OTA_SONOFF,
    CONF_OTA_THIRDREALITY,
    CONF_OTA_Z2M_LOCAL_INDEX,
    CONF_OTA_Z2M_REMOTE_INDEX,
)
from zigpy.ota.image import BaseOTAImage, ImageKey, OTAImageHeader
import zigpy.ota.provider
import zigpy.types as t
import zigpy.util

LOGGER = logging.getLogger(__name__)

TIMEDELTA_0 = datetime.timedelta()
DELAY_EXPIRATION = datetime.timedelta(hours=2)
OTA_FETCH_TIMEOUT = 20


@attr.s
class CachedImage:
    MAXIMUM_DATA_SIZE = 40

    image = attr.ib(default=None)
    cached_data = attr.ib(default=None)

    @property
    def header(self) -> OTAImageHeader:
        return self.image.header

    @property
    def version(self) -> int:
        return self.image.header.file_version

    def get_image_block(self, offset: t.uint32_t, size: t.uint8_t) -> bytes:
        if self.cached_data is None:
            self.cached_data = self.image.serialize()

        if offset > len(self.cached_data):
            raise ValueError("Offset exceeds image size")

        return self.cached_data[offset : offset + min(self.MAXIMUM_DATA_SIZE, size)]

    def serialize(self) -> bytes:
        """Serialize the image."""
        if self.cached_data is None:
            self.cached_data = self.image.serialize()
        return self.cached_data


class OTA:
    """OTA Manager."""

    def __init__(self, config: dict[str, typing.Any]) -> None:
        self._config = config
        self._providers = []
        self._image_cache = {}

        if self._config[CONF_OTA_ALLOW_ADVANCED_DIR]:
            self.providers.append(
                zigpy.ota.provider.AdvancedFileProvider(
                    self._config[CONF_OTA_ADVANCED_DIR]
                )
            )

        if self._config[CONF_OTA_IKEA]:
            self.providers.append(zigpy.ota.provider.Trådfri())

        if self._config[CONF_OTA_INOVELLI]:
            self.providers.append(zigpy.ota.provider.Inovelli())

        if self._config[CONF_OTA_LEDVANCE]:
            self.providers.append(zigpy.ota.provider.Ledvance())

        if self._config[CONF_OTA_SALUS]:
            self.providers.append(zigpy.ota.provider.Salus())

        if self._config[CONF_OTA_SONOFF]:
            self.providers.append(zigpy.ota.provider.Sonoff())

        if self._config[CONF_OTA_THIRDREALITY]:
            self.providers.append(zigpy.ota.provider.ThirdReality())

        for provider_config in self._config[CONF_OTA_REMOTE_PROVIDERS]:
            self.providers.append(
                zigpy.ota.provider.RemoteProvider(
                    url=provider_config[CONF_OTA_PROVIDER_URL],
                    manufacturer_ids=provider_config[CONF_OTA_PROVIDER_MANUF_IDS],
                )
            )

        if self._config[CONF_OTA_Z2M_LOCAL_INDEX]:
            self.providers.append(
                zigpy.ota.provider.LocalZ2MProvider(
                    self._config[CONF_OTA_Z2M_LOCAL_INDEX]
                )
            )

        if self._config[CONF_OTA_Z2M_REMOTE_INDEX]:
            self.providers.append(
                zigpy.ota.provider.RemoteZ2MProvider(
                    self._config[CONF_OTA_Z2M_REMOTE_INDEX]
                )
            )

    def should_update(
        self,
        image: BaseOTAImage,
        device: zigpy.device.Device,
        query_cmd: zigpy.zcl.clusters.general.Ota.ServerCommands.query_next_image.schema,
    ) -> bool:
        """Check if it should upgrade"""

        if self.key != ImageKey(manufacturer_id, img_type):
            return False

        if ver >= self.version:
            return False

        if (
            hw_ver is not None
            and self.image.header.hardware_versions_present
            and not (
                self.image.header.minimum_hardware_version
                <= hw_ver
                <= self.image.header.maximum_hardware_version
            )
        ):
            return False

        return True

    async def get_ota_image(
        self,
        device: zigpy.device.Device,
        query_cmd: zigpy.zcl.clusters.general.Ota.ServerCommands.query_next_image.schema,
    ) -> CachedImage | None:
        results = []

        for result_coro in asyncio.as_completed(
            zigpy.util.timeout(p.get_image(device, query_cmd), OTA_FETCH_TIMEOUT)
            for p in self._providers
        ):
            try:
                image = await result_coro
            except Exception as exc:
                _LOGGER.debug("Failed to get image from provider", exc_info=exc)
                continue

            if image is None:
                continue

            results.append(image)

        if not images:
            return None

        cached = CachedImage.new(max(results, key=lambda img: img.header.file_version))
        self._image_cache[key] = cached
        return cached
