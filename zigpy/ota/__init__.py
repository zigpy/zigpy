"""OTA support for Zigbee devices."""
import datetime
import logging
from typing import Optional

import attr
from zigpy.config import CONF_OTA, CONF_OTA_DIR, CONF_OTA_IKEA, CONF_OTA_LEDVANCE
from zigpy.ota.image import ImageKey, OTAImage
import zigpy.ota.provider
from zigpy.typing import ControllerApplicationType
import zigpy.util

LOGGER = logging.getLogger(__name__)

DELAY_EXPIRATION = datetime.timedelta(hours=2)
TIMEDELTA_0 = datetime.timedelta()


@attr.s
class CachedImage(OTAImage):
    DEFAULT_EXPIRATION = datetime.timedelta(hours=18)

    expires_on = attr.ib(default=None)

    @classmethod
    def new(cls, img: OTAImage):
        expiration = datetime.datetime.now() + cls.DEFAULT_EXPIRATION
        return cls(img.header, img.subelements, expiration)

    @property
    def expired(self) -> bool:
        if self.expires_on is None:
            return False
        return self.expires_on - datetime.datetime.now() < TIMEDELTA_0

    def get_image_block(self, *args, **kwargs) -> bytes:
        if (
            self.expires_on is not None
            and self.expires_on - datetime.datetime.now() < DELAY_EXPIRATION
        ):
            self.expires_on += DELAY_EXPIRATION
        return super().get_image_block(*args, **kwargs)


class OTA(zigpy.util.ListenableMixin):
    """OTA Manager."""

    def __init__(self, app: ControllerApplicationType, *args, **kwargs):
        self._app: ControllerApplicationType = app
        self._image_cache = {}
        self._not_initialized = True
        self._listeners = {}
        ota_config = app.config[CONF_OTA]
        if ota_config[CONF_OTA_IKEA]:
            self.add_listener(zigpy.ota.provider.Trådfri())
        if ota_config[CONF_OTA_DIR]:
            self.add_listener(zigpy.ota.provider.FileStore())
        if ota_config[CONF_OTA_LEDVANCE]:
            self.add_listener(zigpy.ota.provider.Ledvance())

    async def initialize(self) -> None:
        await self.async_event("initialize_provider", self._app.config[CONF_OTA])
        self._not_initialized = False

    async def get_ota_image(self, manufacturer_id, image_type) -> Optional[OTAImage]:
        key = ImageKey(manufacturer_id, image_type)
        if key in self._image_cache and not self._image_cache[key].expired:
            return self._image_cache[key]

        images = await self.async_event("get_image", key)
        images = [img for img in images if img]
        if not images:
            return None

        cached = CachedImage.new(max(images, key=lambda img: img.version))
        self._image_cache[key] = cached
        return cached

    @property
    def not_initialized(self):
        return self._not_initialized
