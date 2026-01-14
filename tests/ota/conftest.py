import asyncio
import hashlib
import json
import logging
import pathlib

import aiohttp
from filelock import FileLock
import pytest

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
