"""OTA Firmware providers."""

from __future__ import annotations

import asyncio
import dataclasses
import datetime
import hashlib
import json
import logging
import pathlib
import re
import ssl
import typing
import urllib.parse

import aiohttp
import attrs
import jsonschema
import voluptuous as vol

import zigpy.config
from zigpy.ota import json_schemas
from zigpy.ota.image import BaseOTAImage, parse_ota_image
import zigpy.types as t
import zigpy.util

LOGGER = logging.getLogger(__name__)

OTA_PROVIDER_TYPES: dict[str, type[BaseOtaProvider]] = {}


def register_provider(provider: type[BaseOtaProvider]) -> type[BaseOtaProvider]:
    """Register a new OTA provider."""
    OTA_PROVIDER_TYPES[provider.NAME] = provider
    return provider


@attrs.define(frozen=True, kw_only=True)
class BaseOtaImageMetadata(t.BaseDataclassMixin):
    file_version: int
    manufacturer_id: int | None = None
    image_type: int | None = None

    checksum: str | None = None
    file_size: int | None = None

    manufacturer_names: tuple[str] = ()
    model_names: tuple[str] = ()

    changelog: str | None = None
    release_notes: str | None = None

    min_hardware_version: int | None = None
    max_hardware_version: int | None = None
    min_current_file_version: int | None = None
    max_current_file_version: int | None = None
    specificity: int | None = None

    source: str = "Unknown"

    async def _fetch(self) -> bytes:
        raise NotImplementedError

    async def _validate(self, data: bytes) -> None:
        if self.file_size is not None and len(data) != self.file_size:
            raise ValueError(
                f"Image size is invalid: expected {self.file_size} bytes,"
                f" got {len(data)} bytes"
            )

        if self.checksum is not None:
            algorithm, checksum = self.checksum.split(":")
            hasher = hashlib.new(algorithm)
            await asyncio.get_running_loop().run_in_executor(None, hasher.update, data)

            if hasher.hexdigest() != checksum:
                raise ValueError(
                    f"Image checksum is invalid: expected {checksum},"
                    f" got {hasher.hexdigest()}"
                )

    async def fetch(self) -> BaseOTAImage:
        data = await self._fetch()
        await self._validate(data)

        image, _ = parse_ota_image(data)
        return image


@attrs.define(frozen=True, kw_only=True)
class RemoteOtaImageMetadata(BaseOtaImageMetadata):
    url: str

    # If a provider uses a self-signed certificate, it can override this
    ssl_ctx: ssl.SSLContext | None = None

    async def _fetch(self) -> bytes:
        async with aiohttp.ClientSession(raise_for_status=True) as req:
            async with req.get(self.url, ssl=self.ssl_ctx) as rsp:
                return await rsp.read()


@attrs.define(frozen=True, kw_only=True)
class LocalOtaImageMetadata(BaseOtaImageMetadata):
    path: pathlib.Path

    async def _fetch(self) -> bytes:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.path.read_bytes)


@attrs.define(frozen=True, kw_only=True)
class IkeaRemoteOtaImageMetadata(RemoteOtaImageMetadata):
    ssl_ctx = dataclasses.field(default_factory=lambda: Tradfri.SSL_CTX)

    async def _fetch(self) -> bytes:
        async with aiohttp.ClientSession(raise_for_status=True) as req:
            # Use IKEA's self-signed certificate
            async with req.get(self.url, ssl=Tradfri.SSL_CTX) as rsp:
                return await rsp.read()


@attrs.define(frozen=True, kw_only=True)
class SignedIkeaRemoteOtaImageMetadata(IkeaRemoteOtaImageMetadata):
    ssl_ctx = dataclasses.field(default_factory=lambda: Tradfri.SSL_CTX)

    async def _validate(self, data: bytes) -> None:
        ota_offset = int.from_bytes(data[16:20], "little")
        ota_size = int.from_bytes(data[20:24], "little")
        block_size = int.from_bytes(data[32:36], "little")
        num_block_hashes = int.from_bytes(data[36:40], "little")

        if (
            not data.startswith(b"NGIS")
            or self.file_size != ota_size
            or 40 + 32 * num_block_hashes != ota_offset
            or block_size * num_block_hashes < ota_size
        ):
            raise ValueError(f"Invalid signed container: {data[:16]!r}")

        loop = asyncio.get_running_loop()

        for block_num in range(num_block_hashes):
            offset = ota_offset + block_size * block_num
            size = block_size - max(0, offset + block_size - (ota_offset + ota_size))

            block = data[offset : offset + size]
            expected_checksum = data[40 + 32 * block_num : 40 + 32 * (block_num + 1)]
            hasher = await loop.run_in_executor(None, hashlib.sha256, block)

            if hasher.digest() != expected_checksum:
                raise ValueError(f"Block {block_num} has invalid checksum")


class BaseOtaProvider:
    NAME: str
    MANUFACTURER_IDS: tuple[int] = ()
    DEFAULT_URL: str | None = None
    VOL_SCHEMA: vol.Schema
    JSON_SCHEMA: dict | None = None
    INDEX_EXPIRATION_TIME = datetime.timedelta(hours=24)

    def __init__(
        self,
        url: str | typing.Literal[True] | None = None,
        manufacturer_ids: list[int] | None = None,
        *,
        override_previous: bool = False,
    ) -> None:
        self.url = self.DEFAULT_URL if url in (True, None) else url
        self._index_last_updated = datetime.datetime.fromtimestamp(
            0, tz=datetime.timezone.utc
        )

        if manufacturer_ids is not None:
            self.manufacturer_ids = tuple(manufacturer_ids)
        else:
            self.manufacturer_ids = tuple(self.MANUFACTURER_IDS)

        self.override_previous = override_previous

    def compatible_with_device(self, device: zigpy.device.Device) -> bool:
        if not self.manufacturer_ids:
            return True

        return device.manufacturer_id in self.manufacturer_ids

    async def load_index(self) -> list[BaseOtaImageMetadata] | None:
        now = datetime.datetime.now(datetime.timezone.utc)

        # Don't hammer the OTA indexes too frequently
        if now - self._index_last_updated < self.INDEX_EXPIRATION_TIME:
            return None

        try:
            async with aiohttp.ClientSession(
                headers={"accept": "application/json"},
                raise_for_status=True,
            ) as session:
                return [meta async for meta in self._load_index(session)]
        finally:
            self._index_last_updated = now

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        if typing.TYPE_CHECKING:
            yield

        raise NotImplementedError

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, self.__class__):
            return NotImplemented

        return self.url == other.url and self.manufacturer_ids == other.manufacturer_ids

    def __hash__(self) -> int:
        return hash((self.url, self.manufacturer_ids))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(url={self.url!r}, manufacturer_ids={self.manufacturer_ids!r})"


@register_provider
class Tradfri(BaseOtaProvider):
    NAME = "ikea"
    MANUFACTURER_IDS = (4476,)
    DEFAULT_URL = "https://fw.ota.homesmart.ikea.com/DIRIGERA/version_info.json"
    VOL_SCHEMA = zigpy.config.SCHEMA_OTA_PROVIDER_URL
    JSON_SCHEMA = json_schemas.TRADFRI_SCHEMA

    # `openssl s_client -connect fw.ota.homesmart.ikea.com:443 -showcerts`
    SSL_CTX: ssl.SSLContext = ssl.create_default_context()
    SSL_CTX.load_verify_locations(
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

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        async with session.get(self.url, ssl=self.SSL_CTX) as rsp:
            # IKEA does not always respond with an appropriate Content-Type but the
            # response is always JSON
            fw_lst = await rsp.json(content_type=None)

        jsonschema.validate(fw_lst, self.JSON_SCHEMA)

        for fw in fw_lst:
            # Skip the gateway image
            if "fw_image_type" not in fw:
                continue

            if "fw_sha3_256" in fw:
                # New style IKEA
                file_version_match = re.match(r".*_v(?P<v>\d+)_.*", fw["fw_binary_url"])

                if file_version_match is None:
                    LOGGER.warning("Could not parse IKEA OTA JSON: %r", fw)
                    continue

                image = IkeaRemoteOtaImageMetadata(
                    file_version=int(file_version_match.group("v"), 10),
                    manufacturer_id=self.MANUFACTURER_IDS[0],
                    image_type=fw["fw_image_type"],
                    checksum="sha3-256:" + fw["fw_sha3_256"],
                    url=fw["fw_binary_url"],
                    source="IKEA (DIRIGERA)",
                )
            else:
                # Old style IKEA
                if fw["fw_type"] != 2:
                    continue

                image = SignedIkeaRemoteOtaImageMetadata(
                    file_version=(
                        (fw["fw_file_version_MSB"] << 16)
                        | (fw["fw_file_version_LSB"] << 0)
                    ),
                    manufacturer_id=fw["fw_manufacturer_id"],
                    image_type=fw["fw_image_type"],
                    # The file size is of the contained image, not the container!
                    file_size=fw["fw_filesize"],
                    url=fw["fw_binary_url"].replace("http://", "https://", 1),
                    source="IKEA (TRÅDFRI)",
                )

            # Bricking update: https://github.com/zigpy/zigpy/issues/1428
            if image.image_type in (8704, 8710):
                continue

            yield image


@register_provider
class Ledvance(BaseOtaProvider):
    NAME = "ledvance"
    # This isn't static but no more than these two have ever existed
    MANUFACTURER_IDS = (4489, 4364)
    DEFAULT_URL = "https://api.update.ledvance.com/v1/zigbee/firmwares"
    JSON_SCHEMA = json_schemas.LEDVANCE_SCHEMA
    VOL_SCHEMA = zigpy.config.SCHEMA_OTA_PROVIDER_URL

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        async with session.get(self.url) as rsp:
            fw_lst = await rsp.json()

        jsonschema.validate(fw_lst, self.JSON_SCHEMA)

        for fw in fw_lst["firmwares"]:
            identity = fw["identity"]
            version = identity["version"]

            yield RemoteOtaImageMetadata(
                file_version=int(fw["fullName"].split("/")[1], 16),
                manufacturer_id=identity["company"],
                image_type=identity["product"],
                checksum="sha256:" + fw["shA256"],
                file_size=fw["length"],
                model_names=(fw["productName"],),
                url=(
                    "https://api.update.ledvance.com/v1/zigbee/firmwares/download?"
                    + urllib.parse.urlencode(
                        {
                            "Company": identity["company"],
                            "Product": identity["product"],
                            "Version": (
                                f"{version['major']}.{version['minor']}"
                                f".{version['build']}.{version['revision']}"
                            ),
                        }
                    )
                ),
                release_notes=fw["releaseNotes"],
                source="Ledvance",
            )


# stub provider to keep existing configurations working
@register_provider
class Salus(BaseOtaProvider):
    NAME = "salus"
    MANUFACTURER_IDS = (4216, 43981)

    VOL_SCHEMA = zigpy.config.SCHEMA_OTA_PROVIDER_URL

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        if False:
            yield  # pragma: no cover


@register_provider
class Sonoff(BaseOtaProvider):
    NAME = "sonoff"
    MANUFACTURER_IDS = (4742,)

    JSON_SCHEMA = json_schemas.SONOFF_SCHEMA
    VOL_SCHEMA = zigpy.config.SCHEMA_OTA_PROVIDER_URL

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        async with session.get(
            "https://zigbee-ota.sonoff.tech/releases/upgrade.json"
        ) as rsp:
            fw_lst = await rsp.json()

        jsonschema.validate(fw_lst, self.JSON_SCHEMA)

        for fw in fw_lst:
            yield RemoteOtaImageMetadata(
                file_version=fw["fw_file_version"],
                manufacturer_id=fw["fw_manufacturer_id"],
                image_type=fw["fw_image_type"],
                file_size=fw["fw_filesize"],
                url=fw["fw_binary_url"],
                model_names=(fw["model_id"],),
                source="Sonoff",
            )


@register_provider
class Inovelli(BaseOtaProvider):
    NAME = "inovelli"
    MANUFACTURER_IDS = (4655,)

    JSON_SCHEMA = json_schemas.INOVELLI_SCHEMA
    VOL_SCHEMA = zigpy.config.SCHEMA_OTA_PROVIDER_URL

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        async with session.get(
            "https://files.inovelli.com/firmware/firmware-zha-v2.json"
        ) as rsp:
            fw_lst = await rsp.json()

        jsonschema.validate(fw_lst, self.JSON_SCHEMA)

        for model, firmwares in fw_lst.items():
            for fw in firmwares:
                version = int(fw["version"], 16)

                if version > 0x0000000B:
                    # Only the first firmware was in hex, all others are decimal
                    version = int(fw["version"])

                yield RemoteOtaImageMetadata(
                    file_version=version,
                    manufacturer_id=fw["manufacturer_id"],
                    image_type=fw["image_type"],
                    model_names=(model,),
                    url=fw["firmware"],
                    source="Inovelli",
                )


@register_provider
class ThirdReality(BaseOtaProvider):
    NAME = "thirdreality"
    MANUFACTURER_IDS = (4659, 4877, 5127)

    JSON_SCHEMA = json_schemas.THIRD_REALITY_SCHEMA
    VOL_SCHEMA = zigpy.config.SCHEMA_OTA_PROVIDER_URL

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        async with session.get("https://tr-zha.s3.amazonaws.com/firmware.json") as rsp:
            fw_lst = await rsp.json()

        jsonschema.validate(fw_lst, self.JSON_SCHEMA)

        for fw in fw_lst["versions"]:
            yield RemoteOtaImageMetadata(
                file_version=fw["fileVersion"],
                manufacturer_id=fw["manufacturerId"],
                model_names=(fw["modelId"],),
                image_type=fw["imageType"],
                url=fw["url"],
                source="ThirdReality",
            )


class BaseZigpyProvider(BaseOtaProvider):
    JSON_SCHEMA = json_schemas.REMOTE_PROVIDER_SCHEMA

    @classmethod
    def _load_zigpy_index(cls, index: dict, *, index_root: pathlib.Path | None = None):
        jsonschema.validate(index, cls.JSON_SCHEMA)

        for fw in index["firmwares"]:
            shared_kwargs = {
                "file_version": fw["file_version"],
                "manufacturer_id": fw["manufacturer_id"],
                "image_type": fw["image_type"],
                "manufacturer_names": tuple(fw.get("manufacturer_names", [])),
                "model_names": tuple(fw.get("model_names", [])),
                "checksum": fw["checksum"],
                "file_size": fw["file_size"],
                "min_hardware_version": fw.get("min_hardware_version"),
                "max_hardware_version": fw.get("max_hardware_version"),
                "min_current_file_version": fw.get("min_current_file_version"),
                "max_current_file_version": fw.get("max_current_file_version"),
                "changelog": fw.get("changelog"),
                "release_notes": fw.get("release_notes"),
                "specificity": fw.get("specificity"),
                "source": "",  # Set in a subclass
            }

            if "path" in fw and index_root is not None:
                yield LocalOtaImageMetadata(
                    **shared_kwargs, path=index_root / fw["path"]
                )
            else:
                yield RemoteOtaImageMetadata(**shared_kwargs, url=fw["binary_url"])


@register_provider
class LocalZigpyProvider(BaseZigpyProvider):
    NAME = "zigpy_local"
    VOL_SCHEMA = zigpy.config.SCHEMA_OTA_PROVIDER_JSON_INDEX

    def __init__(self, index_file: pathlib.Path, **kwargs):
        super().__init__(url=None, **kwargs)
        self.index_file = index_file

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        index_text = await asyncio.get_running_loop().run_in_executor(
            None, self.index_file.read_text
        )
        index = json.loads(index_text)

        for img in self._load_zigpy_index(index, index_root=self.index_file.parent):
            yield img.replace(source=f"Local zigpy provider ({self.index_file})")

    def __eq__(self, other: object) -> bool:
        if (
            not isinstance(other, self.__class__)
            or super().__eq__(other) is NotImplemented
        ):
            return NotImplemented

        return super().__eq__(other) and self.index_file == other.index_file

    def __hash__(self) -> int:
        return hash((self.index_file, self.manufacturer_ids))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(index_file={self.index_file!r}, manufacturer_ids={self.manufacturer_ids!r})"


@register_provider
class RemoteZigpyProvider(BaseZigpyProvider):
    NAME = "zigpy_remote"
    VOL_SCHEMA = zigpy.config.SCHEMA_OTA_PROVIDER_URL_REQUIRED

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        async with session.get(self.url) as rsp:
            fw_lst = await rsp.json(content_type=None)

        jsonschema.validate(fw_lst, self.JSON_SCHEMA)

        for img in self._load_zigpy_index(fw_lst):
            yield img.replace(source=f"Remote zigpy provider ({self.url})")


class BaseZ2MProvider(BaseOtaProvider):
    JSON_SCHEMA = json_schemas.Z2M_SCHEMA

    @classmethod
    def _load_z2m_index(
        cls,
        index: dict,
        *,
        index_root: pathlib.Path | None = None,
        ssl_ctx: ssl.SSLContext | None = None,
    ) -> typing.Iterator[LocalOtaImageMetadata | RemoteOtaImageMetadata]:
        jsonschema.validate(index, cls.JSON_SCHEMA)

        for fw in index:
            shared_kwargs = {
                "file_version": fw["fileVersion"],
                "manufacturer_id": fw["manufacturerCode"],
                "image_type": fw["imageType"],
                "checksum": "sha512:" + fw["sha512"],
                "file_size": fw["fileSize"],
                "manufacturer_names": tuple(fw.get("manufacturerName", [])),
                "model_names": tuple([fw["modelId"]] if "modelId" in fw else []),
                "min_current_file_version": fw.get("minFileVersion"),
                "max_current_file_version": fw.get("maxFileVersion"),
                "min_hardware_version": fw.get("hardwareVersionMin"),
                "max_hardware_version": fw.get("hardwareVersionMax"),
                "changelog": fw.get("releaseNotes"),  # Changelog is short
                "source": "",  # Set in a subclass
            }

            if "path" in fw and index_root is not None:
                yield LocalOtaImageMetadata(
                    **shared_kwargs, path=index_root / fw["path"]
                )
            else:
                yield RemoteOtaImageMetadata(
                    **shared_kwargs, url=fw["url"], ssl_ctx=ssl_ctx
                )


@register_provider
class LocalZ2MProvider(BaseZ2MProvider):
    NAME = "z2m_local"
    VOL_SCHEMA = zigpy.config.SCHEMA_OTA_PROVIDER_JSON_INDEX

    def __init__(self, index_file: pathlib.Path, **kwargs):
        super().__init__(**kwargs)
        self.index_file = index_file

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        index_text = await asyncio.get_running_loop().run_in_executor(
            None, self.index_file.read_text
        )
        index = json.loads(index_text)

        for img in self._load_z2m_index(index, index_root=self.index_file.parent):
            yield img.replace(source=f"Local Z2M provider ({self.index_file})")

    def __eq__(self, other: object) -> bool:
        if (
            not isinstance(other, self.__class__)
            or super().__eq__(other) is NotImplemented
        ):
            return NotImplemented

        return super().__eq__(other) and self.index_file == other.index_file

    def __hash__(self) -> int:
        return hash((self.index_file, self.manufacturer_ids))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(index_file={self.index_file!r}, manufacturer_ids={self.manufacturer_ids!r})"


@register_provider
class RemoteZ2MProvider(BaseZ2MProvider):
    NAME = "z2m"
    DEFAULT_URL = (
        "https://raw.githubusercontent.com/Koenkk/zigbee-OTA/master/index.json"
    )
    VOL_SCHEMA = zigpy.config.SCHEMA_OTA_PROVIDER_URL

    # `openssl s_client -connect otau.meethue.com:443 -showcerts`
    SSL_CTX = ssl.create_default_context()
    SSL_CTX.load_verify_locations(
        cadata="""\
-----BEGIN CERTIFICATE-----
MIIBwDCCAWagAwIBAgIJAJtrMkoTxs+WMAoGCCqGSM49BAMCMDIxCzAJBgNVBAYT
Ak5MMRQwEgYDVQQKDAtQaGlsaXBzIEh1ZTENMAsGA1UEAwwEcm9vdDAgFw0xNjA4
MjUwNzU5NDNaGA8yMDY4MDEwNTA3NTk0M1owMjELMAkGA1UEBhMCTkwxFDASBgNV
BAoMC1BoaWxpcHMgSHVlMQ0wCwYDVQQDDARyb290MFkwEwYHKoZIzj0CAQYIKoZI
zj0DAQcDQgAEENC1JOl6BxJrwCb+YK655zlM57VKFSi5OHDsmlCaF/EfTGGgU08/
JUtkCyMlHUUoYBZyzCBKXqRKkrT512evEKNjMGEwHQYDVR0OBBYEFAlkFYACVzir
qTr++cWia8AKH/fOMB8GA1UdIwQYMBaAFAlkFYACVzirqTr++cWia8AKH/fOMA8G
A1UdEwEB/wQFMAMBAf8wDgYDVR0PAQH/BAQDAgGGMAoGCCqGSM49BAMCA0gAMEUC
IQDcGfyXaUl5hjr5YE8m2piXhMcDzHTNbO1RvGgz4r9IswIgFTTw/R85KyfIiW+E
clwJRVSsq8EApeFREenCkRM0EIk=
-----END CERTIFICATE-----"""
    )

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        async with session.get(self.url) as rsp:
            fw_lst = await rsp.json(content_type=None)

        for img in self._load_z2m_index(fw_lst, ssl_ctx=self.SSL_CTX):
            yield img.replace(source=f"Remote Z2M provider ({self.url})")


@register_provider
class AdvancedFileProvider(BaseOtaProvider):
    NAME = "advanced"
    VOL_SCHEMA = zigpy.config.SCHEMA_OTA_PROVIDER_FOLDER

    def __init__(self, path: pathlib.Path, **kwargs):
        # The `vol` schema passes through the `warning` key, which is unused
        kwargs.pop("warning", None)

        super().__init__(url=None, **kwargs)
        self.path = path

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        loop = asyncio.get_running_loop()

        paths = await loop.run_in_executor(None, self.path.rglob, "*")

        async for chunk in zigpy.util.async_iterate_in_chunks(paths, chunk_size=100):
            for path in chunk:
                if not path.is_file():
                    continue

                data = await loop.run_in_executor(None, path.read_bytes)

                try:
                    image, _ = parse_ota_image(data)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.debug("Failed to parse image %s: %r", path, exc)
                    continue

                # This protects against images being swapped out in the local filesystem
                hasher = await loop.run_in_executor(None, hashlib.sha1, data)

                yield LocalOtaImageMetadata(
                    path=path,
                    file_version=image.header.file_version,
                    manufacturer_id=image.header.manufacturer_id,
                    image_type=image.header.image_type,
                    checksum="sha1:" + hasher.hexdigest(),
                    file_size=len(data),
                    min_hardware_version=image.header.minimum_hardware_version,
                    max_hardware_version=image.header.maximum_hardware_version,
                    source=f"Advanced file provider ({self.path})",
                )

    def __eq__(self, other: object) -> bool:
        if (
            not isinstance(other, self.__class__)
            or super().__eq__(other) is NotImplemented
        ):
            return NotImplemented

        return super().__eq__(other) and self.path == other.path

    def __hash__(self) -> int:
        return hash((self.path, self.manufacturer_ids))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(path={self.path!r}, manufacturer_ids={self.manufacturer_ids!r})"
