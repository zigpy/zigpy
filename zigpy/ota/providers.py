"""OTA Firmware providers."""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import io
import json
import logging
import pathlib
import re
import ssl
import tarfile
import typing
import urllib.parse

import aiohttp
import attrs
import jsonschema

from zigpy.ota.image import BaseOTAImage, parse_ota_image
import zigpy.types as t
import zigpy.util

LOGGER = logging.getLogger(__name__)


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
        raise NotImplementedError()

    async def fetch(self) -> BaseOTAImage:
        data = await self._fetch()

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

        image, _ = parse_ota_image(data)
        return image


@attrs.define(frozen=True, kw_only=True)
class RemoteOtaImageMetadata(BaseOtaImageMetadata):
    url: str

    async def _fetch(self) -> bytes:
        async with aiohttp.ClientSession(raise_for_status=True) as req:
            async with req.get(self.url) as rsp:
                return await rsp.read()


@attrs.define(frozen=True, kw_only=True)
class LocalOtaImageMetadata(BaseOtaImageMetadata):
    path: pathlib.Path

    async def _fetch(self) -> bytes:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.path.read_bytes)


@attrs.define(frozen=True, kw_only=True)
class SalusRemoteOtaImageMetadata(RemoteOtaImageMetadata):
    async def _fetch(self) -> bytes:
        data = await super()._fetch()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._extract_ota_from_tar, data)

    def _extract_ota_from_tar(self, data: bytes) -> bytes:
        files = {}

        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            for tarinfo in tar:
                if tarinfo.isfile():
                    f = tar.extractfile(tarinfo)
                    assert f is not None

                    files[tarinfo.name] = f.read()

        # Each archive contains a `networkinfo.json` file and an OTA file
        networkinfo_json = json.loads(files["networkinfo.json"])
        upgrade = networkinfo_json["upgrade"][0]
        ota_contents = files[upgrade["filename"]]

        # Pick the first file, there will only be one for Zigbee devices
        if hashlib.md5(ota_contents).hexdigest().upper() != upgrade["checksum"]:
            raise ValueError("Embedded OTA file has invalid MD5 checksum")

        return ota_contents


@attrs.define(frozen=True, kw_only=True)
class IkeaRemoteOtaImageMetadata(RemoteOtaImageMetadata):
    async def _fetch(self) -> bytes:
        async with aiohttp.ClientSession(raise_for_status=True) as req:
            # Use IKEA's self-signed certificate
            async with req.get(self.url, ssl=Trådfri.SSL_CTX) as rsp:
                return await rsp.read()


class BaseOtaProvider:
    MANUFACTURER_IDS: list[int] = []
    INDEX_EXPIRATION_TIME = datetime.timedelta(hours=24)

    def __init__(self):
        self._index_last_updated = datetime.datetime.fromtimestamp(
            0, tz=datetime.timezone.utc
        )

    def compatible_with_device(self, device: zigpy.device.Device) -> bool:
        if not self.MANUFACTURER_IDS:
            raise NotImplementedError

        return device.manufacturer_id in self.MANUFACTURER_IDS

    async def load_index(self) -> list[BaseOtaImageMetadata] | None:
        now = datetime.datetime.now(datetime.timezone.utc)

        # Don't hammer the OTA indexes too frequently
        if now - self._index_last_updated < self.INDEX_EXPIRATION_TIME:
            return

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


class Trådfri(BaseOtaProvider):
    MANUFACTURER_IDS = [4476]

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

    JSON_SCHEMA = {
        "type": "array",
        "items": {
            "oneOf": [
                {
                    "type": "object",
                    "properties": {
                        "fw_image_type": {"type": "integer"},
                        "fw_type": {"type": "integer"},
                        "fw_sha3_256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                        "fw_binary_url": {"type": "string", "format": "uri"},
                    },
                    "required": [
                        "fw_image_type",
                        "fw_type",
                        "fw_sha3_256",
                        "fw_binary_url",
                    ],
                },
                {
                    "type": "object",
                    "properties": {
                        "fw_update_prio": {"type": "integer"},
                        "fw_filesize": {"type": "integer"},
                        "fw_type": {"type": "integer"},
                        "fw_hotfix_version": {"type": "integer"},
                        "fw_major_version": {"type": "integer"},
                        "fw_binary_checksum": {
                            "type": "string",
                            "pattern": "^[a-f0-9]{128}$",
                        },
                        "fw_minor_version": {"type": "integer"},
                        "fw_sha3_256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                        "fw_binary_url": {"type": "string", "format": "uri"},
                    },
                    "required": [
                        "fw_update_prio",
                        "fw_filesize",
                        "fw_type",
                        "fw_hotfix_version",
                        "fw_major_version",
                        "fw_binary_checksum",
                        "fw_minor_version",
                        "fw_sha3_256",
                        "fw_binary_url",
                    ],
                },
            ]
        },
    }

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        async with session.get(
            "https://fw.ota.homesmart.ikea.com/DIRIGERA/version_info.json",
            ssl=self.SSL_CTX,
        ) as rsp:
            # IKEA does not always respond with an appropriate Content-Type but the
            # response is always JSON
            fw_lst = await rsp.json(content_type=None)

        jsonschema.validate(fw_lst, self.JSON_SCHEMA)

        for fw in fw_lst:
            # Skip the gateway image
            if "fw_image_type" not in fw:
                continue

            file_version_match = re.match(r".*_v(?P<v>\d+)_.*", fw["fw_binary_url"])

            if file_version_match is None:
                LOGGER.warning("Could not parse IKEA OTA JSON: %r", fw)
                continue

            yield IkeaRemoteOtaImageMetadata(  # type: ignore[call-arg]
                file_version=int(file_version_match.group("v"), 10),
                manufacturer_id=self.MANUFACTURER_IDS[0],
                image_type=fw["fw_image_type"],
                checksum="sha3-256:" + fw["fw_sha3_256"],
                url=fw["fw_binary_url"],
                source="IKEA",
            )


class Ledvance(BaseOtaProvider):
    # This isn't static but no more than these two have ever existed
    MANUFACTURER_IDS = [4489, 4364]

    JSON_SCHEMA = {
        "type": "object",
        "properties": {
            "firmwares": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "blob": {"type": ["null", "string"]},
                        "identity": {
                            "type": "object",
                            "properties": {
                                "company": {"type": "integer"},
                                "product": {"type": "integer"},
                                "version": {
                                    "type": "object",
                                    "properties": {
                                        "major": {"type": "integer"},
                                        "minor": {"type": "integer"},
                                        "build": {"type": "integer"},
                                        "revision": {"type": "integer"},
                                    },
                                    "required": ["major", "minor", "build", "revision"],
                                },
                            },
                            "required": ["company", "product", "version"],
                        },
                        "releaseNotes": {"type": "string"},
                        "shA256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                        "name": {"type": "string"},
                        "productName": {"type": "string"},
                        "fullName": {"type": "string"},
                        "extension": {"type": "string"},
                        "released": {"type": "string", "format": "date-time"},
                        "salesRegion": {"type": ["string", "null"]},
                        "length": {"type": "integer"},
                    },
                    "required": [
                        "blob",
                        "identity",
                        "releaseNotes",
                        "shA256",
                        "name",
                        "productName",
                        "fullName",
                        "extension",
                        "released",
                        "salesRegion",
                        "length",
                    ],
                },
            }
        },
        "required": ["firmwares"],
    }

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        async with session.get(
            "https://api.update.ledvance.com/v1/zigbee/firmwares"
        ) as rsp:
            fw_lst = await rsp.json()

        jsonschema.validate(fw_lst, self.JSON_SCHEMA)

        for fw in fw_lst["firmwares"]:
            identity = fw["identity"]
            version = identity["version"]

            yield RemoteOtaImageMetadata(  # type: ignore[call-arg]
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


class Salus(BaseOtaProvider):
    MANUFACTURER_IDS = [4216, 43981]

    JSON_SCHEMA = {
        "type": "object",
        "properties": {
            "versions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "model": {"type": "string"},
                        "version": {
                            "type": "string",
                            "pattern": "^(|[0-9A-F]{8}|[0-9A-F]{12})$",
                        },
                        "url": {"type": "string", "format": "uri"},
                    },
                    "required": ["model", "version", "url"],
                },
            }
        },
        "required": ["versions"],
    }

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        async with session.get(
            "https://eu.salusconnect.io/demo/default/status/firmware"
        ) as rsp:
            fw_lst = await rsp.json()

        jsonschema.validate(fw_lst, self.JSON_SCHEMA)

        for fw in fw_lst["versions"]:
            # A plain text file is present in the firmware list, ignore it
            if fw["version"] == "":
                continue

            # Not every firmware is actually Zigbee but since they filter by model name
            # there is little chance an invalid one will ever be matched
            yield SalusRemoteOtaImageMetadata(  # type: ignore[call-arg]
                file_version=int(fw["version"], 16),
                model_names=(fw["model"],),
                # Upgrade HTTP to HTTPS, the server supports it
                url=fw["url"].replace("http://", "https://", 1),
                source="SALUS",
            )


class Sonoff(BaseOtaProvider):
    MANUFACTURER_IDS = [4742]

    JSON_SCHEMA = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "fw_binary_url": {"type": "string", "format": "uri"},
                "fw_file_version": {"type": "integer"},
                "fw_filesize": {"type": "integer"},
                "fw_image_type": {"type": "integer"},
                "fw_manufacturer_id": {"type": "integer"},
                "model_id": {"type": "string"},
            },
            "required": [
                "fw_binary_url",
                "fw_file_version",
                "fw_filesize",
                "fw_image_type",
                "fw_manufacturer_id",
                "model_id",
            ],
        },
    }

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        async with session.get(
            "https://zigbee-ota.sonoff.tech/releases/upgrade.json"
        ) as rsp:
            fw_lst = await rsp.json()

        jsonschema.validate(fw_lst, self.JSON_SCHEMA)

        for fw in fw_lst:
            yield RemoteOtaImageMetadata(  # type: ignore[call-arg]
                file_version=fw["fw_file_version"],
                manufacturer_id=fw["fw_manufacturer_id"],
                image_type=fw["fw_image_type"],
                file_size=fw["fw_filesize"],
                url=fw["fw_binary_url"],
                model_names=(fw["model_id"],),
                source="Sonoff",
            )


class Inovelli(BaseOtaProvider):
    MANUFACTURER_IDS = [4655]

    JSON_SCHEMA = {
        "type": "object",
        "patternProperties": {
            "^[A-Z0-9_-]+$": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "version": {
                            "type": "string",
                            "pattern": "^(?:[0-9A-F]{8}|[0-9]+)$",
                        },
                        "channel": {"type": "string"},
                        "firmware": {"type": "string", "format": "uri"},
                        "manufacturer_id": {"type": "integer"},
                        "image_type": {"type": "integer"},
                    },
                    "required": [
                        "version",
                        "channel",
                        "firmware",
                        "manufacturer_id",
                        "image_type",
                    ],
                },
            }
        },
    }

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

                yield RemoteOtaImageMetadata(  # type: ignore[call-arg]
                    file_version=version,
                    manufacturer_id=fw["manufacturer_id"],
                    image_type=fw["image_type"],
                    model_names=(model,),
                    url=fw["firmware"],
                    source="Inovelli",
                )


class ThirdReality(BaseOtaProvider):
    MANUFACTURER_IDS = [4659, 4877]

    JSON_SCHEMA = {
        "type": "object",
        "properties": {
            "versions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "modelId": {"type": "string"},
                        "url": {"type": "string", "format": "uri"},
                        "version": {
                            "type": "string",
                            "pattern": "^\\d+\\.\\d+\\.\\d+$",
                        },
                        "imageType": {"type": "integer"},
                        "manufacturerId": {"type": "integer"},
                        "fileVersion": {"type": "integer"},
                    },
                    "required": [
                        "modelId",
                        "url",
                        "version",
                        "imageType",
                        "manufacturerId",
                        "fileVersion",
                    ],
                },
            }
        },
        "required": ["versions"],
    }

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        async with session.get("https://tr-zha.s3.amazonaws.com/firmware.json") as rsp:
            fw_lst = await rsp.json()

        jsonschema.validate(fw_lst, self.JSON_SCHEMA)

        for fw in fw_lst["versions"]:
            yield RemoteOtaImageMetadata(  # type: ignore[call-arg]
                file_version=fw["fileVersion"],
                manufacturer_id=fw["manufacturerId"],
                model_names=(fw["modelId"],),
                image_type=fw["imageType"],
                url=fw["url"],
                source="ThirdReality",
            )


class RemoteProvider(BaseOtaProvider):
    JSON_SCHEMA = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "firmwares": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "binary_url": {"type": "string", "format": "uri"},
                        "file_version": {"type": "integer"},
                        "file_size": {"type": "integer"},
                        "image_type": {"type": "integer"},
                        "manufacturer_names": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "model_names": {"type": "array", "items": {"type": "string"}},
                        "manufacturer_id": {"type": "integer"},
                        "changelog": {"type": "string"},
                        "release_notes": {"type": "string"},
                        "checksum": {
                            "type": "string",
                            "pattern": "^sha3-256:[a-f0-9]{64}$",
                        },
                        "min_hardware_version": {"type": "integer"},
                        "max_hardware_version": {"type": "integer"},
                        "min_current_file_version": {"type": "integer"},
                        "max_current_file_version": {"type": "integer"},
                        "specificity": {"type": "integer"},
                    },
                    "required": [
                        "binary_url",
                        "file_version",
                        "file_size",
                        "image_type",
                        # "manufacturer_names",
                        # "model_names",
                        "manufacturer_id",
                        # "changelog",
                        "checksum",
                        # "min_hardware_version",
                        # "max_hardware_version",
                        # "min_current_file_version",
                        # "max_current_file_version",
                        # "release_notes",
                        # "specificity",
                    ],
                },
            }
        },
        "required": ["firmwares"],
    }

    def __init__(self, url: str, manufacturer_ids: list[int] | None = None):
        super().__init__()
        self.url = url
        self.manufacturer_ids = manufacturer_ids

    def compatible_with_device(self, device: zigpy.device.Device) -> bool:
        if self.manufacturer_ids is None:
            return True

        return device.manufacturer_id in self.manufacturer_ids

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        async with session.get(self.url) as rsp:
            index = await rsp.json()

        jsonschema.validate(index, self.JSON_SCHEMA)

        for fw in index["firmwares"]:
            meta = RemoteOtaImageMetadata(  # type: ignore[call-arg]
                file_version=fw["file_version"],
                manufacturer_id=fw["manufacturer_id"],
                image_type=fw["image_type"],
                manufacturer_names=tuple(fw.get("manufacturer_names", [])),
                model_names=tuple(fw.get("model_names", [])),
                checksum=fw["checksum"],
                file_size=fw["file_size"],
                url=fw["binary_url"],
                min_hardware_version=fw.get("min_hardware_version"),
                max_hardware_version=fw.get("max_hardware_version"),
                min_current_file_version=fw.get("min_current_file_version"),
                max_current_file_version=fw.get("max_current_file_version"),
                changelog=fw.get("changelog"),
                release_notes=fw.get("release_notes"),
                specificity=fw.get("specificity"),
                source=f"Remote provider ({self.url})",
            )

            # To ensure all remote images can be used, extend the list of known
            # manufacturer IDs at runtime if we encounter a new one
            if (
                self.manufacturer_ids is not None
                and meta.manufacturer_id not in self.manufacturer_ids
            ):
                LOGGER.warning(
                    "Remote provider manufacturer ID is unknown: %d",
                    meta.manufacturer_id,
                )
                self.manufacturer_ids.append(meta.manufacturer_id)

            yield meta


class AdvancedFileProvider(BaseOtaProvider):
    def __init__(self, image_dir: pathlib.Path):
        super().__init__()
        self.image_dir = image_dir

    def compatible_with_device(self, device: zigpy.device.Device) -> bool:
        return True

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        loop = asyncio.get_running_loop()

        for path in self.image_dir.rglob("*"):
            if not path.is_file():
                continue

            data = await loop.run_in_executor(None, path.read_bytes)

            try:
                image, _ = parse_ota_image(data)
            except Exception as exc:
                LOGGER.debug("Failed to parse image %s: %r", path, exc)
                continue

            # This protects against images being swapped out in the local filesystem
            hasher = await loop.run_in_executor(None, hashlib.sha1, data)

            yield LocalOtaImageMetadata(  # type: ignore[call-arg]
                path=path,
                file_version=image.header.file_version,
                manufacturer_id=image.header.manufacturer_id,
                image_type=image.header.image_type,
                checksum="sha1:" + hasher.hexdigest(),
                file_size=len(data),
                min_hardware_version=image.header.minimum_hardware_version,
                max_hardware_version=image.header.maximum_hardware_version,
                source=f"Advanced file provider ({self.image_dir})",
            )


def _load_z2m_index(index: dict, *, index_root: pathlib.Path | None = None):
    for obj in index:
        shared_kwargs = {
            "file_version": obj["fileVersion"],
            "manufacturer_id": obj["manufacturerCode"],
            "image_type": obj["imageType"],
            "checksum": "sha512:" + obj["sha512"],
            "file_size": obj["fileSize"],
            "manufacturer_names": tuple(obj.get("manufacturerName", [])),
            "model_names": tuple([obj["modelId"]] if "modelId" in obj else []),
            "min_current_file_version": obj.get("minFileVersion"),
            "max_current_file_version": obj.get("maxFileVersion"),
            "source": "",  # Set in a subclass
        }

        if "path" in obj and index_root is not None:
            yield LocalOtaImageMetadata(**shared_kwargs, path=index_root / obj["path"])  # type: ignore[call-arg]
        else:
            yield RemoteOtaImageMetadata(**shared_kwargs, url=obj["url"])  # type: ignore[call-arg]


class BaseZ2MProvider(BaseOtaProvider):
    JSON_SCHEMA = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "fileVersion": {"type": "integer"},
                "fileSize": {"type": "integer"},
                "manufacturerCode": {"type": "integer"},
                "imageType": {"type": "integer"},
                "sha512": {"type": "string", "pattern": "^[a-f0-9]{128}$"},
                "url": {"type": "string", "format": "uri"},
                "path": {"type": "string"},
                "minFileVersion": {"type": "integer"},
                "maxFileVersion": {"type": "integer"},
                "manufacturerName": {"type": "array", "items": {"type": "string"}},
                "modelId": {"type": "string"},
            },
            "required": [
                "fileVersion",
                "fileSize",
                "manufacturerCode",
                "imageType",
                "sha512",
                "url",
            ],
        },
    }

    def compatible_with_device(self, device: zigpy.device.Device) -> bool:
        return True


class LocalZ2MProvider(BaseZ2MProvider):
    def __init__(self, index_file: pathlib.Path):
        super().__init__()
        self.index_file = index_file

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        index_text = await asyncio.get_running_loop().run_in_executor(
            None, self.index_file.read_text
        )
        index = json.loads(index_text)

        jsonschema.validate(index, self.JSON_SCHEMA)

        for img in _load_z2m_index(index, index_root=self.index_file.parent):
            yield img.replace(source=f"Local Z2M provider ({self.index_file})")


class RemoteZ2MProvider(BaseZ2MProvider):
    def __init__(self, url: str):
        super().__init__()
        self.url = url

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        async with session.get(self.url) as rsp:
            fw_lst = await rsp.json(content_type=None)

        jsonschema.validate(fw_lst, self.JSON_SCHEMA)

        for img in _load_z2m_index(fw_lst):
            yield img.replace(source=f"Remote Z2M provider ({self.url})")
