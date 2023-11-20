"""OTA Firmware providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections import defaultdict
import datetime
import hashlib
import io
import logging
import os
import os.path
import re
import ssl
import tarfile
import typing
import urllib.parse

import aiohttp
import attr

from zigpy.config import CONF_OTA_DIR, CONF_OTA_SONOFF_URL
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

    def __init__(self) -> None:
        self.config: dict[str, str | int] = {}
        self._cache: dict[ImageKey, BaseOTAImage] = {}
        self._is_enabled = False
        self._locks: defaultdict[asyncio.Semaphore] = defaultdict(asyncio.Semaphore)
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

    def update_expiration(self) -> None:
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

    def log(self, lvl: int, msg: str, *args, **kwargs) -> None:
        """Log a message"""
        msg = f"{self.__class__.__name__}: {msg}"
        return LOGGER.log(lvl, msg, *args, **kwargs)


@attr.s
class IKEAImage:
    image_type: int = attr.ib()
    binary_url: str = attr.ib()
    sha3_256_sum: str = attr.ib()

    @classmethod
    def new(cls, data: dict[str, str | int]) -> IKEAImage:
        return cls(
            image_type=data["fw_image_type"],
            sha3_256_sum=data["fw_sha3_256"],
            binary_url=data["fw_binary_url"],
        )

    @property
    def version(self) -> int:
        file_version_match = re.match(r".*_v(?P<v>\d+)_.*", self.binary_url)
        if file_version_match is None:
            raise ValueError(f"Couldn't parse firmware version from {self}")

        return int(file_version_match.group("v"), 10)

    @property
    def key(self) -> ImageKey:
        return ImageKey(Trådfri.MANUFACTURER_ID, self.image_type)

    async def fetch_image(self) -> BaseOTAImage | None:
        async with aiohttp.ClientSession() as req:
            LOGGER.debug("Downloading %s for %s", self.binary_url, self.key)
            async with req.get(self.binary_url, ssl=Trådfri.SSL_CTX) as rsp:
                data = await rsp.read()

        assert hashlib.sha3_256(data).hexdigest() == self.sha3_256_sum

        ota_image, _ = parse_ota_image(data)
        assert ota_image.header.key == self.key

        LOGGER.debug("Finished downloading %s", self)
        return ota_image


class Trådfri(Basic):
    """IKEA OTA Firmware provider."""

    UPDATE_URL = "https://fw.ota.homesmart.ikea.com/DIRIGERA/version_info.json"
    MANUFACTURER_ID = 4476
    HEADERS = {"accept": "application/json;q=0.9,*/*;q=0.8"}

    # `openssl s_client -connect fw.ota.homesmart.ikea.com:443 -showcerts`
    SSL_CTX = ssl.create_default_context(
        cadata="""\
-----BEGIN CERTIFICATE-----
MIICGDCCAZ+gAwIBAgIUdfH0KDnENv/dEcxH8iVqGGGDqrowCgYIKoZIzj0EAwMw
SzELMAkGA1UEBhMCU0UxGjAYBgNVBAoMEUlLRUEgb2YgU3dlZGVuIEFCMSAwHgYD
VQQDDBdJS0VBIEhvbWUgc21hcnQgUm9vdCBDQTAgFw0yMTA1MjYxOTAxMDlaGA8y
MDcxMDUxNDE5MDEwOFowSzELMAkGA1UEBhMCU0UxGjAYBgNVBAoMEUlLRUEgb2Yg
U3dlZGVuIEFCMSAwHgYDVQQDDBdJS0VBIEhvbWUgc21hcnQgUm9vdCBDQTB2MBAG
ByqGSM49AgEGBSuBBAAiA2IABIDRUvKGFMUu2zIhTdgfrfNcPULwMlc0TGSrDLBA
oTr0SMMV4044CRZQbl81N4qiuHGhFzCnXapZogkiVuFu7ZqSslsFuELFjc6ZxBjk
Kmud+pQM6QQdsKTE/cS06dA+P6NCMEAwDwYDVR0TAQH/BAUwAwEB/zAdBgNVHQ4E
FgQUcdlEnfX0MyZA4zAdY6CLOye9wfwwDgYDVR0PAQH/BAQDAgGGMAoGCCqGSM49
BAMDA2cAMGQCMG6mFIeB2GCFch3r0Gre4xRH+f5pn/bwLr9yGKywpeWvnUPsQ1KW
ckMLyxbeNPXdQQIwQc2YZDq/Mz0mOkoheTUWiZxK2a5bk0Uz1XuGshXmQvEg5TGy
2kVHW/Mz9/xwpy4u
-----END CERTIFICATE-----"""
    )

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
                async with req.get(self.UPDATE_URL, ssl=self.SSL_CTX) as rsp:
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
            if "fw_image_type" not in fw:
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
    def __init__(self) -> None:
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
        for root, _dirs, files in os.walk(self._ota_dir):
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
    image_type = attr.ib()
    version = attr.ib()
    url = attr.ib()

    @classmethod
    def from_json(cls, obj: dict[str, str | int]) -> INOVELLIImage:
        version = int(obj["version"], 16)

        # Old Inovelli OTA JSON versions were in hex, they then switched back to decimal
        if version > 0x10:
            version = int(obj["version"])

        return cls(
            manufacturer_id=obj["manufacturer_id"],
            image_type=obj["image_type"],
            version=version,
            url=obj["firmware"],
        )

    @property
    def key(self) -> ImageKey:
        return ImageKey(self.manufacturer_id, self.image_type)

    async def fetch_image(self) -> BaseOTAImage | None:
        async with aiohttp.ClientSession() as req:
            LOGGER.debug("Downloading %s for %s", self.url, self.key)
            async with req.get(self.url) as rsp:
                data = await rsp.read()

        ota_image, _ = parse_ota_image(data)
        assert ota_image.header.key == self.key

        LOGGER.debug(
            "Finished downloading from %s for %s ver %s",
            self.url,
            self.key,
            self.version,
        )
        return ota_image


class Inovelli(Basic):
    """Inovelli OTA Firmware provider."""

    UPDATE_URL = "https://files.inovelli.com/firmware/firmware-zha.json"
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

        for _model, firmwares in fw_lst.items():
            for firmware in firmwares:
                img = INOVELLIImage.from_json(firmware)

                # Only replace the previously-cached image if its version is smaller
                if (
                    img.key in self._cache
                    and self._cache[img.key].version > img.version
                ):
                    continue

                self._cache[img.key] = img

        self.update_expiration()

    async def filter_get_image(self, key: ImageKey) -> bool:
        return key.manufacturer_id != self.MANUFACTURER_ID


@attr.s
class ThirdRealityImage:
    model = attr.ib()
    url = attr.ib()
    version = attr.ib()
    image_type = attr.ib()
    manufacturer_id = attr.ib()
    file_version = attr.ib()

    @classmethod
    def from_json(cls, obj: dict[str, typing.Any]) -> ThirdRealityImage:
        return cls(
            model=obj["modelId"],
            url=obj["url"],
            version=obj["version"],
            image_type=obj["imageType"],
            manufacturer_id=obj["manufacturerId"],
            file_version=obj["fileVersion"],
        )

    @property
    def key(self) -> ImageKey:
        return ImageKey(self.manufacturer_id, self.image_type)

    async def fetch_image(self) -> BaseOTAImage:
        async with aiohttp.ClientSession() as req:
            LOGGER.debug("Downloading %s for %s", self.url, self.key)
            async with req.get(self.url) as rsp:
                data = await rsp.read()

        ota_image, _ = parse_ota_image(data)
        assert ota_image.header.key == self.key

        LOGGER.debug(
            "Finished downloading from %s for %s ver %s",
            self.url,
            self.key,
            self.version,
        )
        return ota_image


class ThirdReality(Basic):
    """Third Reality OTA Firmware provider."""

    UPDATE_URL = "https://tr-zha.s3.amazonaws.com/firmware.json"
    MANUFACTURER_IDS = (4659, 4877)
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
        for firmware in fw_lst["versions"]:
            img = ThirdRealityImage.from_json(firmware)
            self._cache[img.key] = img

        self.update_expiration()

    async def filter_get_image(self, key: ImageKey) -> bool:
        return key.manufacturer_id not in self.MANUFACTURER_IDS


@attr.s
class RemoteImage:
    binary_url = attr.ib()
    file_version = attr.ib()
    image_type = attr.ib()
    manufacturer_id = attr.ib()
    changelog = attr.ib()
    checksum = attr.ib()

    # Optional
    min_hardware_version = attr.ib()
    max_hardware_version = attr.ib()
    min_current_file_version = attr.ib()
    max_current_file_version = attr.ib()

    @classmethod
    def from_json(cls, obj: dict[str, typing.Any]) -> RemoteImage:
        return cls(
            binary_url=obj["binary_url"],
            file_version=obj["file_version"],
            image_type=obj["image_type"],
            manufacturer_id=obj["manufacturer_id"],
            changelog=obj["changelog"],
            checksum=obj["checksum"],
            min_hardware_version=obj.get("min_hardware_version"),
            max_hardware_version=obj.get("max_hardware_version"),
            min_current_file_version=obj.get("min_current_file_version"),
            max_current_file_version=obj.get("max_current_file_version"),
        )

    @property
    def key(self) -> ImageKey:
        return ImageKey(self.manufacturer_id, self.image_type)

    async def fetch_image(self) -> BaseOTAImage:
        async with aiohttp.ClientSession() as req:
            LOGGER.debug("Downloading %s for %s", self.binary_url, self.key)
            async with req.get(self.binary_url) as rsp:
                data = await rsp.read()

        algorithm, checksum = self.checksum.split(":")
        hasher = hashlib.new(algorithm)
        await asyncio.get_running_loop().run_in_executor(None, hasher.update, data)

        if hasher.hexdigest() != checksum:
            raise ValueError(
                f"Image checksum is invalid: expected {self.checksum},"
                f" got {hasher.hexdigest()}"
            )

        ota_image, _ = parse_ota_image(data)

        LOGGER.debug("Finished downloading %s", self)
        return ota_image


class RemoteProvider(Basic):
    """Generic zigpy OTA URL provider."""

    HEADERS = {"accept": "application/json"}

    def __init__(self, url: str, manufacturer_ids: list[int] | None) -> None:
        super().__init__()

        self.url = url
        self.manufacturer_ids = manufacturer_ids

    async def initialize_provider(self, ota_config: dict) -> None:
        self.info("OTA provider enabled")
        await self.refresh_firmware_list()
        self.enable()

    async def refresh_firmware_list(self) -> None:
        if self._locks[LOCK_REFRESH].locked():
            return

        async with self._locks[LOCK_REFRESH]:
            async with aiohttp.ClientSession(headers=self.HEADERS) as req:
                async with req.get(self.url) as rsp:
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
        for obj in fw_lst:
            img = RemoteImage.from_json(obj)
            self._cache[img.key] = img

        self.update_expiration()

    async def filter_get_image(self, key: ImageKey) -> bool:
        if not self.manufacturer_ids:
            return False

        return key.manufacturer_id not in self.manufacturer_ids
