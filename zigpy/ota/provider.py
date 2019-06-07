"""OTA Firmware providers."""
import asyncio
import logging
from collections import defaultdict
from typing import Optional

import aiohttp
import attr

from zigpy.ota.image import ImageKey, OTAImage

LOGGER = logging.getLogger(__name__)


@attr.s
class IKEAImage(OTAImage):
    url = attr.ib(default=None)


class Trådfri:
    """IKEA OTA Firmware provider."""
    UPDATE_URL = 'https://fw.ota.homesmart.ikea.net/feed/version_info.json'
    OTA_HEADER = 0x0BEEF11E.to_bytes(4, 'little')
    MANUFACTURER_ID = 4476

    def __init__(self):
        self._cache = {}
        self._locks = defaultdict(asyncio.Semaphore)

    async def initialize_provider(self) -> None:
        LOGGER.debug("Downloading IKEA firmware update list")
        async with self._locks['firmware_list']:
            async with aiohttp.ClientSession() as req:
                async with req.get(self.UPDATE_URL) as rsp:
                    fw_lst = await rsp.json(
                        content_type='application/octet-stream')
        self._cache.clear()
        frm_to_fetch = []
        for fw in fw_lst:
            if 'fw_file_version_MSB' not in fw:
                continue
            img = IKEAImage()
            img.header.manufacturer_id = fw['fw_manufacturer_id']
            img.header.image_type = fw['fw_image_type']
            img.header.file_version = fw['fw_file_version_MSB'] << 16
            img.header.file_version |= fw['fw_file_version_LSB']
            img.header.image_size = fw['fw_filesize']
            img.url = fw['fw_binary_url']
            frm_to_fetch.append(self.fetch_firmware(img.key))
            self._cache[img.key] = img
        await asyncio.gather(*frm_to_fetch)

    async def fetch_firmware(self, key: ImageKey):
        if self._locks[key].locked():
            return

        img = self._cache[key]
        async with self._locks[key]:
            async with aiohttp.ClientSession() as req:
                LOGGER.debug("Downloading %s for %s", img.url, key)
                async with req.get(img.url) as rsp:
                    data = await rsp.read()
        offset = data.index(self.OTA_HEADER)
        img, data = IKEAImage.deserialize(data[offset:])
        self._cache[img.key] = img
        LOGGER.debug("Finished downloading %s bytes for %s ver %s",
                     img.header.image_size, img.key, img.version)

    def get_image(self, key: ImageKey) -> Optional[IKEAImage]:
        if key.manufacturer_id != self.MANUFACTURER_ID:
            return None

        try:
            image = self._cache[key]
            if image.subelements:
                return image
        except KeyError:
            pass

        # signal to query for new firmware
        asyncio.ensure_future(self.fetch_firmware(key))
        return None
