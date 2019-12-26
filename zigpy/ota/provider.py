"""OTA Firmware providers."""
import asyncio
import datetime
import logging
import os
import os.path
from collections import defaultdict
from typing import Optional

import aiohttp
import attr
from zigpy.ota.image import ImageKey, OTAImage, OTAImageHeader

LOGGER = logging.getLogger(__name__)
LOCK_REFRESH = "firmware_list"

ENABLE_IKEA_OTA = "enable_ikea_ota"
SKIP_OTA_FILES = (ENABLE_IKEA_OTA,)


class Basic:
    """Skeleton OTA Firmware provider."""

    REFRESH = datetime.timedelta(hours=12)

    def __init__(self):
        self._cache = {}
        self._is_enabled = False
        self._locks = defaultdict(asyncio.Semaphore)
        self._last_refresh = None

    async def initialize_provider(self, ota_dir: str) -> None:
        pass

    async def refresh_firmware_list(self) -> None:
        """Loads list of firmware into memory."""
        raise NotImplementedError

    async def filter_get_image(self, key: ImageKey) -> bool:
        """Filter unwanted get_image lookups."""
        return False

    async def get_image(self, key: ImageKey) -> Optional[OTAImage]:
        if await self.filter_get_image(key):
            return None

        if not self.is_enabled or self._locks[key].locked():
            return None

        if self.expired:
            await self.refresh_firmware_list()

        try:
            fw_file = self._cache[key]
        except KeyError:
            return None

        async with self._locks[key]:
            return await fw_file.fetch_image()

    def disable(self) -> None:
        self._is_enabled = False

    def enable(self) -> None:
        self._is_enabled = True

    def update_expiration(self):
        self._last_refresh = datetime.datetime.now()

    @property
    def is_enabled(self) -> bool:
        return self._is_enabled

    @property
    def expired(self) -> bool:
        """Return True if firmware list needs refreshing."""
        if self._last_refresh is None:
            return True

        return datetime.datetime.now() - self._last_refresh > self.REFRESH


@attr.s
class IKEAImage:
    manufacturer_id = attr.ib()
    image_type = attr.ib()
    version = attr.ib(default=None)
    image_size = attr.ib(default=None)
    url = attr.ib(default=None)

    @classmethod
    def new(cls, data):
        res = cls(data["fw_manufacturer_id"], data["fw_image_type"])
        res.file_version = data["fw_file_version_MSB"] << 16
        res.file_version |= data["fw_file_version_LSB"]
        res.image_size = data["fw_filesize"]
        res.url = data["fw_binary_url"]
        return res

    @property
    def key(self):
        return ImageKey(self.manufacturer_id, self.image_type)

    async def fetch_image(self) -> Optional[OTAImage]:
        async with aiohttp.ClientSession() as req:
            LOGGER.debug("Downloading %s for %s", self.url, self.key)
            async with req.get(self.url) as rsp:
                data = await rsp.read()

        assert len(data) > 24
        offset = int.from_bytes(data[16:20], 'little')
        size = int.from_bytes(data[20:24], 'little')
        assert len(data) > offset + size

        ota_image, _ = OTAImage.deserialize(data[offset:offset + size])
        assert ota_image.key == self.key

        LOGGER.debug(
            "Finished downloading %s bytes from %s for %s ver %s",
            self.image_size,
            self.url,
            self.key,
            self.version,
        )
        return ota_image


class Trådfri(Basic):
    """IKEA OTA Firmware provider."""

    UPDATE_URL = "https://fw.ota.homesmart.ikea.net/feed/version_info.json"
    MANUFACTURER_ID = 4476

    async def initialize_provider(self, ota_dir: str) -> None:
        if ota_dir is None:
            return

        if os.path.isfile(os.path.join(ota_dir, ENABLE_IKEA_OTA)):
            LOGGER.debug("IKEA OTA provider enabled")
            await self.refresh_firmware_list()
            self.enable()

    async def refresh_firmware_list(self) -> None:
        if self._locks[LOCK_REFRESH].locked():
            return

        LOGGER.debug("Downloading IKEA firmware update list")
        async with self._locks[LOCK_REFRESH]:
            async with aiohttp.ClientSession() as req:
                async with req.get(self.UPDATE_URL) as rsp:
                    fw_lst = await rsp.json(content_type=None)
        self._cache.clear()
        for fw in fw_lst:
            if "fw_file_version_MSB" not in fw:
                continue
            img = IKEAImage.new(fw)
            self._cache[img.key] = img
        self.update_expiration()

    async def filter_get_image(self, key: ImageKey) -> bool:
        return key.manufacturer_id != self.MANUFACTURER_ID


@attr.s
class FileImage(OTAImageHeader):
    REFRESH = datetime.timedelta(hours=24)
    OTA_HEADER = 0x0BEEF11E .to_bytes(4, "little")

    file_name = attr.ib(default=None)

    @property
    def key(self) -> ImageKey:
        return ImageKey(self.manufacturer_id, self.image_type)

    @property
    def version(self) -> int:
        return self.file_version

    @classmethod
    def scan_image(cls, file_name: str):
        """Check the header of the image."""
        try:
            with open(file_name, mode="rb") as file:
                data = file.read(512)
                offset = data.index(cls.OTA_HEADER)
                if offset >= 0:
                    img = cls.deserialize(data[offset:])[0]
                    img.file_name = file_name
                    LOGGER.debug(
                        ("%s: %s, version: %s, hw_ver: (%s, %s)," " OTA string: %s"),
                        img.key,
                        file_name,
                        img.file_version,
                        img.minimum_hardware_version,
                        img.maximum_hardware_version,
                        img.header_string,
                    )
                    return img
        except (OSError, ValueError) as exc:
            LOGGER.debug(
                "File '%s' doesn't appear to be a OTA image: %s", file_name, exc
            )
        return None

    def fetch_image(self) -> Optional[OTAImage]:
        """Load image using executor."""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(None, self._fetch_image)

    def _fetch_image(self) -> Optional[OTAImage]:
        """Loads full OTA Image from the file."""
        try:
            with open(self.file_name, mode="rb") as file:
                data = file.read()
                offset = data.index(self.OTA_HEADER)
                if offset >= 0:
                    img = OTAImage.deserialize(data[offset:])[0]
                    return img
        except (OSError, ValueError) as exc:
            LOGGER.debug("Couldn't load '%s' OTA image: %s", self.file_name, exc)
        return None


class FileStore(Basic):
    def __init__(self, ota_dir=None):
        super().__init__()
        self._ota_dir = self.validate_ota_dir(ota_dir)

    @staticmethod
    def validate_ota_dir(ota_dir: str) -> str:
        """Return True if exists and is a dir."""
        if ota_dir is None:
            return None

        if os.path.exists(ota_dir):
            if os.path.isdir(ota_dir):
                return ota_dir
            LOGGER.error("OTA image path '%s' is not a directory", ota_dir)
        else:
            LOGGER.debug("OTA image directory '%s' does not exist", ota_dir)
        return None

    async def initialize_provider(self, ota_dir: str) -> None:
        if self._ota_dir is None:
            self._ota_dir = self.validate_ota_dir(ota_dir)

        if self._ota_dir is not None:
            self.enable()
            await self.refresh_firmware_list()

    async def refresh_firmware_list(self) -> None:
        if self._ota_dir is None:
            return None

        self._cache.clear()
        loop = asyncio.get_event_loop()
        for root, dirs, files in os.walk(self._ota_dir):
            for file in files:
                if file in SKIP_OTA_FILES:
                    continue
                file_name = os.path.join(root, file)
                img = await loop.run_in_executor(None, FileImage.scan_image, file_name)
                if img is None:
                    continue

                if img.key in self._cache:
                    if img.version > self._cache[img.key].version:
                        LOGGER.debug(
                            "%s: Preferring '%s' over '%s'",
                            img.key,
                            file_name,
                            self._cache[img.key].file_name,
                        )
                        self._cache[img.key] = img
                    elif img.version == self._cache[img.key].version:
                        LOGGER.debug(
                            "%s: Ignoring '%s' already have %s version",
                            img.key,
                            file_name,
                            img.version,
                        )
                    else:
                        LOGGER.debug(
                            "%s: Preferring '%s' over '%s'",
                            img.key,
                            self._cache[img.key].file_name,
                            file_name,
                        )
                else:
                    self._cache[img.key] = img

        self.update_expiration()
