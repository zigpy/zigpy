"""OTA Firmware providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections import defaultdict
import datetime
import io
import logging
import os
import os.path
import tarfile
import urllib.parse

import aiohttp
import attr

from zigpy.config import CONF_OTA_DIR, CONF_OTA_IKEA_URL, CONF_OTA_SONOFF_URL
from zigpy.ota.image import BaseOTAImage, ImageKey, OTAImageHeader, parse_ota_image
import zigpy.util

LOGGER = logging.getLogger(__name__)
LOCK_REFRESH = "firmware_list"

ENABLE_IKEA_OTA = "enable_ikea_ota"
ENABLE_INOVELLI_OTA = "enable_inovelli_ota"
ENABLE_LEDVANCE_OTA = "enable_ledvance_ota"
SKIP_OTA_FILES = (ENABLE_IKEA_OTA, ENABLE_INOVELLI_OTA, ENABLE_LEDVANCE_OTA)


class Basic(zigpy.util.LocalLogMixin, ABC):
    """Skeleton OTA Firmware provider."""

    REFRESH = datetime.timedelta(hours=12)

    def __init__(self):
        self.config = {}
        self._cache = {}
        self._is_enabled = False
        self._locks = defaultdict(asyncio.Semaphore)
        self._last_refresh = None

    @abstractmethod
    async def initialize_provider(self, ota_config: dict) -> None:
        """Initialize OTA provider."""

    @abstractmethod
    async def refresh_firmware_list(self) -> None:
        """Loads list of firmware into memory."""

    async def filter_get_image(self, key: ImageKey) -> bool:
        """Filter unwanted get_image lookups."""
        return False

    async def get_image(self, key: ImageKey) -> BaseOTAImage | None:
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

    def log(self, lvl, msg, *args, **kwargs):
        """Log a message"""
        msg = f"{self.__class__.__name__}: {msg}"
        return LOGGER.log(lvl, msg, *args, **kwargs)


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

    async def fetch_image(self) -> BaseOTAImage | None:
        async with aiohttp.ClientSession() as req:
            LOGGER.debug("Downloading %s for %s", self.url, self.key)
            async with req.get(self.url) as rsp:
                data = await rsp.read()

        ota_image, _ = parse_ota_image(data)
        assert ota_image.header.key == self.key

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

    UPDATE_URL = "http://fw.ota.homesmart.ikea.net/feed/version_info.json"
    MANUFACTURER_ID = 4476
    HEADERS = {"accept": "application/json;q=0.9,*/*;q=0.8"}

    async def initialize_provider(self, ota_config: dict) -> None:
        self.info("OTA provider enabled")
        self.config = ota_config
        await self.refresh_firmware_list()
        self.enable()

    async def refresh_firmware_list(self) -> None:
        if self._locks[LOCK_REFRESH].locked():
            return

        async with self._locks[LOCK_REFRESH]:
            async with aiohttp.ClientSession(headers=self.HEADERS) as req:
                url = self.config.get(CONF_OTA_IKEA_URL, self.UPDATE_URL)
                async with req.get(url) as rsp:
                    # IKEA does not always respond with an appropriate Content-Type
                    # but the response is always JSON
                    if not (200 <= rsp.status <= 299):
                        self.warning(
                            "Couldn't download '%s': %s/%s",
                            rsp.url,
                            rsp.status,
                            rsp.reason,
                        )
                        return
                    fw_lst = await rsp.json(content_type=None)
        self.debug("Finished downloading firmware update list")
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
class LedvanceImage:
    """Ledvance image handler."""

    manufacturer_id = attr.ib()
    image_type = attr.ib()
    version = attr.ib(default=None)
    image_size = attr.ib(default=None)
    url = attr.ib(default=None)

    @classmethod
    def new(cls, data):
        identity = data["identity"]
        version_parts = identity["version"]

        # This matches the OTA file's `image_version` for every image
        version = (
            (version_parts["major"] << 24)
            | (version_parts["minor"] << 16)
            | (version_parts["build"] << 8)
            | (version_parts["revision"] << 0)
        )

        res = cls(
            manufacturer_id=identity["company"],
            image_type=identity["product"],
            version=version,
        )
        res.file_version = int(data["fullName"].split("/")[1], 16)
        res.image_size = data["length"]
        res.url = (
            "https://api.update.ledvance.com/v1/zigbee/firmwares/download?"
            + urllib.parse.urlencode(
                {
                    "Company": identity["company"],
                    "Product": identity["product"],
                    "Version": (
                        f"{version_parts['major']}.{version_parts['minor']}"
                        f".{version_parts['build']}.{version_parts['revision']}"
                    ),
                }
            )
        )

        return res

    @property
    def key(self):
        return ImageKey(self.manufacturer_id, self.image_type)

    async def fetch_image(self) -> BaseOTAImage | None:
        async with aiohttp.ClientSession() as req:
            LOGGER.debug("Downloading %s for %s", self.url, self.key)
            async with req.get(self.url) as rsp:
                data = await rsp.read()

        img, _ = parse_ota_image(data)
        assert img.header.key == self.key

        LOGGER.debug(
            "%s: version: %s, hw_ver: (%s, %s), OTA string: %s",
            img.header.key,
            img.header.file_version,
            img.header.minimum_hardware_version,
            img.header.maximum_hardware_version,
            img.header.header_string,
        )

        LOGGER.debug(
            "Finished downloading %s bytes from %s for %s ver %s",
            self.image_size,
            self.url,
            self.key,
            self.version,
        )
        return img


class Ledvance(Basic):
    """Ledvance firmware provider"""

    # documentation: https://portal.update.ledvance.com/docs/services/firmware-rest-api/

    UPDATE_URL = "https://api.update.ledvance.com/v1/zigbee/firmwares"
    HEADERS = {"accept": "application/json"}

    async def initialize_provider(self, ota_config: dict) -> None:
        self.info("OTA provider enabled")
        await self.refresh_firmware_list()
        self.enable()

    async def refresh_firmware_list(self) -> None:
        if self._locks[LOCK_REFRESH].locked():
            return

        async with self._locks[LOCK_REFRESH]:
            async with aiohttp.ClientSession(headers=self.HEADERS) as req:
                async with req.get(self.UPDATE_URL) as rsp:
                    if not (200 <= rsp.status <= 299):
                        self.warning(
                            "Couldn't download '%s': %s/%s",
                            rsp.url,
                            rsp.status,
                            rsp.reason,
                        )
                        return
                    fw_lst = await rsp.json()
        self.debug("Finished downloading firmware update list")
        self._cache.clear()
        for fw in fw_lst["firmwares"]:
            img = LedvanceImage.new(fw)

            # Ignore earlier images
            if img.key in self._cache and self._cache[img.key].version > img.version:
                continue

            self._cache[img.key] = img
        self.update_expiration()


@attr.s
class SalusImage:
    """Salus image handler."""

    manufacturer_id = attr.ib()
    model = attr.ib()
    version = attr.ib(default=None)
    image_size = attr.ib(default=None)
    url = attr.ib(default=None)

    @classmethod
    def new(cls, data):
        mod = data["model"]
        ver = data["version"]
        url = data["url"]

        res = cls(
            manufacturer_id=Salus.MANUFACTURER_ID, model=mod, version=ver, url=url
        )

        return res

    @property
    def key(self):
        return ImageKey(self.manufacturer_id, self.model)

    async def fetch_image(self) -> BaseOTAImage | None:
        async with aiohttp.ClientSession() as req:
            LOGGER.debug("Downloading %s for %s", self.url, self.key)
            async with req.get(self.url) as rsp:
                data = await rsp.read()
            img_tgz = io.BytesIO(data)
            with tarfile.open(fileobj=img_tgz) as tar:  # Unpack tar
                for item in tar:
                    if item.name.endswith(".ota"):
                        f = tar.extractfile(item)
                        if f is None:
                            raise ValueError(
                                f"Issue extracting {item.name} from {self.url}"
                            )
                        else:
                            file_bytes = f.read()
                        break
            img, _ = parse_ota_image(file_bytes)

            LOGGER.debug(
                "%s: version: %s, hw_ver: (%s, %s), OTA string: %s",
                img.header.key,
                img.header.file_version,
                img.header.minimum_hardware_version,
                img.header.maximum_hardware_version,
                img.header.header_string,
            )
            assert img.header.manufacturer_id == self.manufacturer_id
            # we can't check assert img.header.key == self.key because
            # self.key does not include any valid image_type data for salus
            # devices.  It is not known at the point of generating the FW
            # list cache, so it can't be checked here (Ikea and ledvance have
            # this listed in the JSON, so they already know and can do this).

        LOGGER.debug(
            "Finished downloading %s bytes from %s for %s ver %s",
            self.image_size,
            self.url,
            self.key,
            self.version,
        )
        return img


class Salus(Basic):
    """Salus firmware provider"""

    # documentation: none known.

    UPDATE_URL = "https://eu.salusconnect.io/demo/default/status/firmware"
    MANUFACTURER_ID = 4216
    HEADERS = {"accept": "application/json"}

    async def initialize_provider(self, ota_config: dict) -> None:
        self.info("OTA provider enabled")
        await self.refresh_firmware_list()
        self.enable()

    async def refresh_firmware_list(self) -> None:
        if self._locks[LOCK_REFRESH].locked():
            return

        async with self._locks[LOCK_REFRESH]:
            async with aiohttp.ClientSession(headers=self.HEADERS) as req:
                async with req.get(self.UPDATE_URL) as rsp:
                    if not (200 <= rsp.status <= 299):
                        self.warning(
                            "Couldn't download '%s': %s/%s",
                            rsp.url,
                            rsp.status,
                            rsp.reason,
                        )
                        return
                    fw_lst = await rsp.json()
        self.debug("Finished downloading firmware update list")
        self._cache.clear()
        for fw in fw_lst["versions"]:
            img = SalusImage.new(fw)
            self._cache[img.key] = img
        self.update_expiration()


@attr.s
class SONOFFImage:
    manufacturer_id = attr.ib()
    image_type = attr.ib()
    version = attr.ib(default=None)
    image_size = attr.ib(default=None)
    url = attr.ib(default=None)

    @classmethod
    def new(cls, data):
        res = cls(data["fw_manufacturer_id"], data["fw_image_type"])
        res.version = data["fw_file_version"]
        res.image_size = data["fw_filesize"]
        res.url = data["fw_binary_url"]
        return res

    @property
    def key(self):
        return ImageKey(self.manufacturer_id, self.image_type)

    async def fetch_image(self) -> BaseOTAImage | None:
        async with aiohttp.ClientSession() as req:
            LOGGER.debug("Downloading %s for %s", self.url, self.key)
            async with req.get(self.url) as rsp:
                data = await rsp.read()

        ota_image, _ = parse_ota_image(data)
        assert ota_image.header.key == self.key

        LOGGER.debug(
            "Finished downloading %s bytes from %s for %s ver %s",
            self.image_size,
            self.url,
            self.key,
            self.version,
        )
        return ota_image


class Sonoff(Basic):
    """Sonoff OTA Firmware provider."""

    UPDATE_URL = "https://zigbee-ota.sonoff.tech/releases/upgrade.json"
    MANUFACTURER_ID = 4742
    HEADERS = {"accept": "application/json;q=0.9,*/*;q=0.8"}

    async def initialize_provider(self, ota_config: dict) -> None:
        self.info("OTA provider enabled")
        self.config = ota_config
        await self.refresh_firmware_list()
        self.enable()

    async def refresh_firmware_list(self) -> None:
        if self._locks[LOCK_REFRESH].locked():
            return

        async with self._locks[LOCK_REFRESH]:
            async with aiohttp.ClientSession(headers=self.HEADERS) as req:
                url = self.config.get(CONF_OTA_SONOFF_URL, self.UPDATE_URL)
                async with req.get(url) as rsp:
                    if not (200 <= rsp.status <= 299):
                        self.warning(
                            "Couldn't download '%s': %s/%s",
                            rsp.url,
                            rsp.status,
                            rsp.reason,
                        )
                        return
                    fw_lst = await rsp.json()
        self.debug("Finished downloading firmware update list")
        self._cache.clear()
        for fw in fw_lst:
            img = SONOFFImage.new(fw)
            self._cache[img.key] = img

        self.update_expiration()

    async def filter_get_image(self, key: ImageKey) -> bool:
        return key.manufacturer_id != self.MANUFACTURER_ID


@attr.s
class FileImage:
    REFRESH = datetime.timedelta(hours=24)

    file_name = attr.ib(default=None)
    header = attr.ib(factory=OTAImageHeader)

    @property
    def key(self) -> ImageKey:
        return ImageKey(self.header.manufacturer_id, self.header.image_type)

    @property
    def version(self) -> int:
        return self.header.file_version

    @classmethod
    def scan_image(cls, file_name: str):
        """Check the header of the image."""
        try:
            with open(file_name, mode="rb") as f:
                parsed_image, _ = parse_ota_image(f.read())
                img = cls(file_name=file_name, header=parsed_image.header)

                LOGGER.debug(
                    "%s: %s, version: %s, hw_ver: (%s, %s), OTA string: %s",
                    img.key,
                    img.file_name,
                    img.version,
                    img.header.minimum_hardware_version,
                    img.header.maximum_hardware_version,
                    img.header.header_string,
                )
                return img
        except (OSError, ValueError):
            LOGGER.debug(
                "File '%s' doesn't appear to be a OTA image", file_name, exc_info=True
            )
        return None

    def fetch_image(self) -> BaseOTAImage | None:
        """Load image using executor."""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(None, self._fetch_image)

    def _fetch_image(self) -> BaseOTAImage | None:
        """Loads full OTA Image from the file."""
        try:
            with open(self.file_name, mode="rb") as f:
                data = f.read()
                img, _ = parse_ota_image(data)

                return img
        except (OSError, ValueError):
            LOGGER.debug("Couldn't load '%s' OTA image", self.file_name, exc_info=True)
        return None


class FileStore(Basic):
    def __init__(self):
        super().__init__()
        self._ota_dir = None

    @staticmethod
    def validate_ota_dir(ota_dir: str) -> str | None:
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

    async def initialize_provider(self, ota_config: dict) -> None:
        ota_dir = ota_config[CONF_OTA_DIR]
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
                        self.debug(
                            "%s: Preferring '%s' over '%s'",
                            img.key,
                            file_name,
                            self._cache[img.key].file_name,
                        )
                        self._cache[img.key] = img
                    elif img.version == self._cache[img.key].version:
                        self.debug(
                            "%s: Ignoring '%s' already have %s version",
                            img.key,
                            file_name,
                            img.version,
                        )
                    else:
                        self.debug(
                            "%s: Preferring '%s' over '%s'",
                            img.key,
                            self._cache[img.key].file_name,
                            file_name,
                        )
                else:
                    self._cache[img.key] = img

        self.update_expiration()


@attr.s
class INOVELLIImage:
    manufacturer_id = attr.ib()
    model = attr.ib()
    version = attr.ib(default=None)
    url = attr.ib(default=None)

    @classmethod
    def new(cls, data, model):
        ver = int(data["version"], 16)
        url = data["firmware"]

        res = cls(
            manufacturer_id=Inovelli.MANUFACTURER_ID, model=model, version=ver, url=url
        )
        return res

    @property
    def key(self):
        return ImageKey(self.manufacturer_id, self.model)

    async def fetch_image(self) -> BaseOTAImage | None:
        async with aiohttp.ClientSession() as req:
            LOGGER.debug("Downloading %s for %s", self.url, self.key)
            async with req.get(self.url) as rsp:
                data = await rsp.read()

        ota_image, _ = parse_ota_image(data)
        assert ota_image.header.manufacturer_id == self.key.manufacturer_id

        LOGGER.debug(
            "Finished downloading from %s for %s ver %s",
            self.url,
            self.key,
            self.version,
        )
        return ota_image


class Inovelli(Basic):
    """Inovelli OTA Firmware provider."""

    UPDATE_URL = "https://files.inovelli.com/firmware/firmware.json"
    MANUFACTURER_ID = 4655
    HEADERS = {"accept": "application/json"}

    async def initialize_provider(self, ota_config: dict) -> None:
        self.info("OTA provider enabled")
        self.config = ota_config
        await self.refresh_firmware_list()
        self.enable()

    async def refresh_firmware_list(self) -> None:
        if self._locks[LOCK_REFRESH].locked():
            return

        async with self._locks[LOCK_REFRESH]:
            async with aiohttp.ClientSession(headers=self.HEADERS) as req:
                async with req.get(self.UPDATE_URL) as rsp:
                    if not (200 <= rsp.status <= 299):
                        self.warning(
                            "Couldn't download '%s': %s/%s",
                            rsp.url,
                            rsp.status,
                            rsp.reason,
                        )
                        return
                    fw_lst = await rsp.json()
        self.debug("Finished downloading firmware update list")
        self._cache.clear()
        for model, firmwares in fw_lst.items():
            # Pick the most recent firmware
            firmware = max(firmwares, key=lambda obj: obj["version"])
            img = INOVELLIImage.new(data=firmware, model=model)
            self._cache[img.key] = img

        self.update_expiration()

    async def filter_get_image(self, key: ImageKey) -> bool:
        return key.manufacturer_id != self.MANUFACTURER_ID
