"""Implement OTA for Zigbee devices."""

import asyncio
import logging

import attr
import zigpy.types as t
from zigpy.util import ListenableMixin

LOGGER = logging.getLogger(__name__)


@attr.s(frozen=True)
class Firmware:
    manufacturer_code = attr.ib(default=None)
    image_type = attr.ib(default=None)
    file_version = attr.ib(default=t.uint32_t(0))
    file_size = attr.ib(default=t.uint32_t(0))


class OTAManager(ListenableMixin):

    def __init__(self, app, *args, **kwargs):
        self._app = app
        self._firmwares = {}
        self._listeners = {}

    async def fetch_firmware(self, manufacturer_code, img_type):
        LOGGER.debug("Fetching firmware for (%s %s)",
                     manufacturer_code, img_type)
        handlers = self.listener_event('fetch_firmware',
                                       manufacturer_code, img_type)
        frmws = await asyncio.gather(*handlers)
        frmws = {f.file_version: f for f in frmws if f is not None}
        if not frmws:
            return

        latest = frmws[max(frmws)]
        self._firmwares[(latest.manufacturer_code, latest.image_type)] = latest

    async def refresh_firmwares(self):
        LOGGER.debug("Refreshing OTA firmwares")
        handlers = self.listener_event('refresh_firmwares')
        await asyncio.gather(*handlers)

    def register_firmware_provider(self, provider):
        return self.add_listener(provider)

    def get_firmware(self, key):
        if key in self._firmwares:
            return self._firmwares[key]
        # signal to query for new firmware
        asyncio.create_task(self.fetch_firmware(key[0], key[1]))
        return None

