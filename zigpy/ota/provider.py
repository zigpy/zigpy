"""OTA Firmware providers."""
import asyncio
import logging
from collections import defaultdict
from typing import Optional

import aiohttp
import attr

from zigpy import types as t

from zigpy.ota.image import ImageKey

LOGGER = logging.getLogger(__name__)


@attr.s
class Firmware:
    key = attr.ib(default=ImageKey)
    version = attr.ib(default=t.uint32_t(0))
    size = attr.ib(default=t.uint32_t(0))
    url = attr.ib(default=None)
    data = attr.ib(default=None)

    def upgradeable(self, manufacturer_id, img_type, ver, hw_ver=None) -> bool:
        """Check if it should upgrade"""
        key = ImageKey(manufacturer_id, img_type)
        # ToDo check for hardware version
        return all((self.key == key, self.version > ver, self.is_valid))

    @property
    def is_valid(self):
        """Return True if firmware validation passes."""
        # ToDo proper validation
        return self.data is not None


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
            key = ImageKey(fw['fw_manufacturer_id'], fw['fw_image_type'])
            version = fw['fw_file_version_MSB'] << 16
            version |= fw['fw_file_version_LSB']
            firmware = Firmware(
                key, version, fw['fw_filesize'], fw['fw_binary_url'],
            )
            frm_to_fetch.append(self.fetch_firmware(key))
            self._cache[key] = firmware
        await asyncio.gather(*frm_to_fetch)

    async def fetch_firmware(self, key: ImageKey):
        if self._locks[key].locked():
            return

        frm = self._cache[key]
        async with self._locks[key]:
            async with aiohttp.ClientSession() as req:
                LOGGER.debug("Downloading %s for %s", frm.url, key)
                async with req.get(frm.url) as rsp:
                    data = await rsp.read()
        offset = data.index(self.OTA_HEADER)
        frm.data = data[offset:offset + frm.size]
        assert len(frm.data) == frm.size
        self._cache[key] = frm
        LOGGER.debug("Finished downloading %s bytes from %s",
                     frm.size, frm.url)

    def get_firmware(self, key: ImageKey) -> Optional[Firmware]:
        if key.manufacturer_id != self.MANUFACTURER_ID:
            return None

        try:
            frm = self._cache[key]
            if frm.is_valid:
                return frm
        except KeyError:
            pass

        # signal to query for new firmware
        asyncio.ensure_future(self.fetch_firmware(key))
        return None
