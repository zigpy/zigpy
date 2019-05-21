"""OTA Firmware providers."""
import asyncio
import logging
from collections import defaultdict
from typing import Optional

import aiohttp

from zigpy.ota.firmware import Firmware, FirmwareKey

LOGGER = logging.getLogger(__name__)


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
        for fw in fw_lst:
            if 'fw_file_version_MSB' not in fw:
                continue
            key = FirmwareKey(fw['fw_manufacturer_id'], fw['fw_image_type'])
            version = fw['fw_file_version_MSB'] << 16
            version |= fw['fw_file_version_LSB']
            firmware = Firmware(
                key, version, fw['fw_filesize'], fw['fw_binary_url'],
            )
            self._cache[key] = firmware

    async def fetch_firmware(self, key: FirmwareKey):
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

    def get_firmware(self, key: FirmwareKey) -> Optional[Firmware]:
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
