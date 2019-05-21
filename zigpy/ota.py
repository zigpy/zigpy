"""Implement OTA for Zigbee devices."""

import asyncio
from collections import defaultdict
import logging
from typing import Optional

import aiohttp
import attr
import zigpy.types as t
from zigpy.util import ListenableMixin

LOGGER = logging.getLogger(__name__)


@attr.s(frozen=True)
class FirmwareKey:
    manufacturer_id = attr.ib(default=None)
    image_type = attr.ib(default=None)


@attr.s
class Firmware:
    key = attr.ib(default=FirmwareKey)
    version = attr.ib(default=t.uint32_t(0))
    size = attr.ib(default=t.uint32_t(0))
    url = attr.ib(default=None)
    data = attr.ib(default=None)

    def upgradeable(self, manufacturer_id, img_type, ver, hw_ver) -> bool:
        """Check if it should upgrade"""
        key = FirmwareKey(manufacturer_id, img_type)
        # ToDo check for hardware version
        return all((self.key == key, self.version > ver, ))

    @property
    def is_valid(self):
        """Return True if firmware validation passes."""
        # ToDo proper validation
        return self.data is not None


class OTAManager(ListenableMixin):
    """OTA Manager."""

    def __init__(self, app, *args, **kwargs):
        self._app = app
        self._firmwares = {}
        self._not_initialized = True
        self._listeners = {}
        self.add_listener(TrådfriOTAProvider())

    async def _initialize(self) -> None:
        LOGGER.debug("Initialize OTA providers")
        handlers = self.listener_event('initialize_provider')
        if handlers:
            await asyncio.gather(*handlers)

    async def refresh_firmwares(self) -> None:
        LOGGER.debug("Refreshing OTA firmwares")
        handlers = self.listener_event('refresh_firmwares')
        if handlers:
            await asyncio.gather(*handlers)

    def initialize(self) -> None:
        self._not_initialized = False
        asyncio.ensure_future(self._initialize())

    def get_firmware(self,
                     manufacturer_id,
                     image_type) -> Optional[Firmware]:
        key = FirmwareKey(manufacturer_id, image_type)
        if key in self._firmwares:
            return self._firmwares[key]

        frmws = self.listener_event('get_firmware', key)
        frmws = {f.version: f for f in frmws if f and f.is_valid}
        if not frmws:
            return None

        latest_firmware = frmws[max(frmws)]
        self._firmwares[key] = latest_firmware
        return latest_firmware

    @property
    def not_initialized(self):
        return self._not_initialized


class TrådfriOTAProvider:
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
