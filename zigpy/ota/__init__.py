"""OTA support for Zigbee devices."""
import asyncio
import datetime
import logging
from typing import Optional

import attr
import zigpy.ota.provider
import zigpy.util
from zigpy.ota.image import ImageKey, OTAImage

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

    def __init__(self, app, *args, **kwargs):
        self._app = app
        self._image_cache = {}
        self._not_initialized = True
        self._listeners = {}
        self.add_listener(zigpy.ota.provider.Trådfri())
        self.add_listener(zigpy.ota.provider.FileStore())

    async def _initialize(self, ota_dir: str) -> None:
        LOGGER.debug("Initialize OTA providers")
        await self.async_event("initialize_provider", ota_dir)

    def initialize(self, ota_dir: str) -> None:
        self._not_initialized = False
        asyncio.ensure_future(self._initialize(ota_dir))

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
