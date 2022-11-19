"""OTA support for Zigbee devices."""
import datetime
import logging
from typing import Optional

import attr

from zigpy.config import (
    CONF_OTA,
    CONF_OTA_DIR,
    CONF_OTA_IKEA,
    CONF_OTA_INOVELLI,
    CONF_OTA_LEDVANCE,
    CONF_OTA_SALUS,
    CONF_OTA_SONOFF,
    CONF_OTA_THIRDREALITY,
)
from zigpy.ota.image import BaseOTAImage, ImageKey, OTAImageHeader
import zigpy.ota.provider
from zigpy.ota.validators import check_invalid
import zigpy.types as t
from zigpy.typing import ControllerApplicationType
import zigpy.util

LOGGER = logging.getLogger(__name__)

TIMEDELTA_0 = datetime.timedelta()
DELAY_EXPIRATION = datetime.timedelta(hours=2)


@attr.s
class CachedImage:
    MAXIMUM_DATA_SIZE = 40
    DEFAULT_EXPIRATION = datetime.timedelta(hours=18)

    image = attr.ib(default=None)
    expires_on = attr.ib(default=None)
    cached_data = attr.ib(default=None)

    @classmethod
    def new(cls, img: BaseOTAImage) -> "CachedImage":
        expiration = datetime.datetime.now() + cls.DEFAULT_EXPIRATION
        return cls(img, expiration)

    @property
    def expired(self) -> bool:
        if self.expires_on is None:
            return False
        return self.expires_on - datetime.datetime.now() < TIMEDELTA_0

    @property
    def key(self) -> ImageKey:
        return self.image.header.key

    @property
    def header(self) -> OTAImageHeader:
        return self.image.header

    @property
    def version(self) -> int:
        return self.image.header.file_version

    def should_update(self, manufacturer_id, img_type, ver, hw_ver=None) -> bool:
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

    def get_image_block(self, offset: t.uint32_t, size: t.uint8_t) -> bytes:
        if (
            self.expires_on is not None
            and self.expires_on - datetime.datetime.now() < DELAY_EXPIRATION
        ):
            self.expires_on += DELAY_EXPIRATION

        if self.cached_data is None:
            self.cached_data = self.image.serialize()

        if offset > len(self.cached_data):
            raise ValueError("Offset exceeds image size")

        return self.cached_data[offset : offset + min(self.MAXIMUM_DATA_SIZE, size)]


class OTA(zigpy.util.ListenableMixin):
    """OTA Manager."""

    def __init__(self, app: ControllerApplicationType, *args, **kwargs):
        self._app: ControllerApplicationType = app
        self._image_cache: dict[ImageKey, CachedImage] = {}
        self._not_initialized = True
        self._listeners = {}
        ota_config = app.config[CONF_OTA]
        if ota_config[CONF_OTA_DIR]:
            self.add_listener(zigpy.ota.provider.FileStore())
        if ota_config[CONF_OTA_IKEA]:
            self.add_listener(zigpy.ota.provider.Trådfri())
        if ota_config[CONF_OTA_INOVELLI]:
            self.add_listener(zigpy.ota.provider.Inovelli())
        if ota_config[CONF_OTA_LEDVANCE]:
            self.add_listener(zigpy.ota.provider.Ledvance())
        if ota_config[CONF_OTA_SALUS]:
            self.add_listener(zigpy.ota.provider.Salus())
        if ota_config[CONF_OTA_SONOFF]:
            self.add_listener(zigpy.ota.provider.Sonoff())
        if ota_config[CONF_OTA_THIRDREALITY]:
            self.add_listener(zigpy.ota.provider.ThirdReality())

    async def initialize(self) -> None:
        await self.async_event("initialize_provider", self._app.config[CONF_OTA])
        self._not_initialized = False

    async def get_ota_image(
        self, manufacturer_id, image_type, model=None
    ) -> Optional[CachedImage]:
        if manufacturer_id in (
            zigpy.ota.provider.Salus.MANUFACTURER_ID,
        ):  # Salus/computime do not pass a useful image_type
            # in the message from the device. So construct key based on model name.
            key = ImageKey(manufacturer_id, model)
        else:
            key = ImageKey(manufacturer_id, image_type)
        if key in self._image_cache and not self._image_cache[key].expired:
            return self._image_cache[key]

        images = await self.async_event("get_image", key)
        valid_images = []

        for image in images:
            if image is None or check_invalid(image):
                continue

            valid_images.append(image)

        if not valid_images:
            return None

        cached = CachedImage.new(
            max(valid_images, key=lambda img: img.header.file_version)
        )
        self._image_cache[key] = cached
        return cached

    @property
    def not_initialized(self):
        return self._not_initialized
