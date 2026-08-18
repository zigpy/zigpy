import asyncio
import hashlib
import json
import logging
import pathlib

import aiohttp
from filelock import FileLock
import pytest

from zigpy.ota import OtaImageWithMetadata
import zigpy.ota.image
from zigpy.ota.providers import BaseOtaImageMetadata

_LOGGER = logging.getLogger(__name__)
FILES_DIR = pathlib.Path(__file__).parent / "files"


async def download(url: str) -> bytes | None:
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=10)
    ) as session:
        async with session.get(url, ssl=False, raise_for_status=True) as resp:
            return await resp.read()


@pytest.fixture(scope="session", autouse=True)
def download_external_files(tmp_path_factory) -> None:
    root_tmp_dir = tmp_path_factory.getbasetemp().parent
    lock_file = root_tmp_dir / "download.lock"

    with FileLock(lock_file):
        urls = json.loads((FILES_DIR / "external/urls.json").read_text())

        for path, obj in urls.items():
            path = FILES_DIR / "external" / path
            path.parent.mkdir(parents=True, exist_ok=True)

            if not path.is_file():
                try:
                    data = asyncio.run(download(obj["url"]))
                except (TimeoutError, aiohttp.ClientError) as e:
                    _LOGGER.error("Failed to download %s: %s", obj["url"], e)
                    continue
                else:
                    path.write_bytes(data)

            algorithm, digest = obj["checksum"].split(":")
            assert hashlib.new(algorithm, path.read_bytes()).hexdigest() == digest


@pytest.fixture
def image_with_metadata() -> OtaImageWithMetadata:
    firmware = zigpy.ota.image.OTAImage(
        header=zigpy.ota.image.OTAImageHeader(
            upgrade_file_id=zigpy.ota.image.OTAImageHeader.MAGIC_VALUE,
            file_version=0x12345678,
            image_type=0x5678,
            manufacturer_id=0x1234,
            header_version=256,
            header_length=60,
            field_control=zigpy.ota.image.FieldControl.HARDWARE_VERSIONS_PRESENT,
            minimum_hardware_version=1,
            maximum_hardware_version=5,
            stack_version=2,
            header_string="This is a test header!",
            image_size=60 + 2 + 4 + 8,
        ),
        subelements=[zigpy.ota.image.SubElement(tag_id=0x0000, data=b"fw_image")],
    )

    metadata = BaseOtaImageMetadata(
        file_version=0x12345678,
        manufacturer_id=0x1234,
        image_type=0x5678,
        checksum="sha256:" + hashlib.sha256(firmware.serialize()).hexdigest(),
        file_size=len(firmware.serialize()),
        manufacturer_names=("manufacturer1", "manufacturer2"),
        model_names=("model1", "model2"),
        changelog="Some simple changelog",
        min_hardware_version=1,
        max_hardware_version=5,
        min_current_file_version=0x12345678 - 10,
        max_current_file_version=0x12345678 - 2,
        specificity=0,
    )

    return OtaImageWithMetadata(metadata=metadata, firmware=firmware)
