"""OTA Firmware providers."""
import asyncio
import datetime
import logging
from collections import defaultdict
from typing import Optional

import aiohttp
import attr

from zigpy.ota.image import ImageKey, OTAImage

LOGGER = logging.getLogger(__name__)
LOCK_REFRESH = 'firmware_list'


class Basic:
    """Skeleton OTA Firmware provider."""
    REFRESH = datetime.timedelta(hours=12)

    def __init__(self):
        self._cache = {}
        self._locks = defaultdict(asyncio.Semaphore)
        self._last_refresh = None

    async def initialize_provider(self) -> None:
        pass

    async def refresh_firmware_list(self) -> None:
        """Loads list of firmware into memory."""
        raise NotImplementedError

    async def get_image(self, key: ImageKey) -> Optional[OTAImage]:
        if self._locks[key].locked():
            return None

        if self.expired:
            await self.refresh_firmware_list()

        try:
            fw_file = self._cache[key]
        except KeyError:
            return None

        async with self._locks[key]:
            return await fw_file.fetch_image()

    def update_expiration(self):
        self._last_refresh = datetime.datetime.now()

    @property
    def expired(self) -> bool:
        """Return True if firmware list needs refreshing."""
        if self._last_refresh is None:
            return True

        return datetime.datetime.now() - self._last_refresh > self.REFRESH


@attr.s
class IKEAImage:
    OTA_HEADER = 0x0BEEF11E.to_bytes(4, 'little')

    manufacturer_id = attr.ib()
    image_type = attr.ib()
    version = attr.ib(default=None)
    file_size = attr.ib(default=None)
    url = attr.ib(default=None)

    @classmethod
    def new(cls, data):
        res = cls(data['fw_manufacturer_id'], data['fw_image_type'])
        res.file_version = data['fw_file_version_MSB'] << 16
        res.file_version |= data['fw_file_version_LSB']
        res.image_size = data['fw_filesize']
        res.url = data['fw_binary_url']
        return res

    @property
    def key(self):
        return ImageKey(self.manufacturer_id, self.image_type)

    async def fetch_image(self) -> Optional[OTAImage]:
        async with aiohttp.ClientSession() as req:
            LOGGER.debug("Downloading %s for %s", self.url, self.key)
            async with req.get(self.url) as rsp:
                data = await rsp.read()
        offset = data.index(self.OTA_HEADER)
        LOGGER.debug("Finished downloading %s bytes from %s for %s ver %s",
                     self.file_size, self.url, self.key, self.version)
        return OTAImage.deserialize(data[offset:])[0]


class Trådfri(Basic):
    """IKEA OTA Firmware provider."""
    UPDATE_URL = 'https://fw.ota.homesmart.ikea.net/feed/version_info.json'
    MANUFACTURER_ID = 4476

    async def refresh_firmware_list(self) -> None:
        if self._locks[LOCK_REFRESH].locked():
            return

        LOGGER.debug("Downloading IKEA firmware update list")
        async with self._locks[LOCK_REFRESH]:
            async with aiohttp.ClientSession() as req:
                async with req.get(self.UPDATE_URL) as rsp:
                    fw_lst = await rsp.json(
                        content_type='application/octet-stream')
        self._cache.clear()
        for fw in fw_lst:
            if 'fw_file_version_MSB' not in fw:
                continue
            img = IKEAImage.new(fw)
            self._cache[img.key] = img
        self.update_expiration()

    async def get_image(self, key: ImageKey) -> Optional[OTAImage]:
        if key.manufacturer_id != self.MANUFACTURER_ID:
            return None

        return await super().get_image(key)
