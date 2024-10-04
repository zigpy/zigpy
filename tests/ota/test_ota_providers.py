from __future__ import annotations

import asyncio
import hashlib
import io
import json
import pathlib
import tarfile
from unittest.mock import Mock

import aiohttp
from aioresponses import aioresponses
import attrs
import pytest

from tests.conftest import make_node_desc
from tests.ota.test_ota_metadata import image_with_metadata  # noqa: F401
import zigpy.device
from zigpy.ota import OtaImageWithMetadata, providers
import zigpy.types as t

FILES_DIR = pathlib.Path(__file__).parent / "files"


@pytest.fixture(scope="module", autouse=True)
def download_external_files():
    urls = json.loads((FILES_DIR / "external/urls.json").read_text())

    for path, obj in urls.items():
        path = FILES_DIR / "external" / path
        path.parent.mkdir(parents=True, exist_ok=True)

        if not path.is_file():

            async def download(path: pathlib.Path = path, obj: dict = obj) -> None:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        obj["url"],
                        ssl=False,
                        raise_for_status=True,
                    ) as resp:
                        data = await resp.read()

                path.write_bytes(data)

            asyncio.run(download())

        algorithm, digest = obj["checksum"].split(":")
        assert hashlib.new(algorithm, path.read_bytes()).hexdigest() == digest


def make_device(
    model: str | None = None,
    manufacturer: str | None = None,
    manufacturer_id: int | None = None,
) -> zigpy.device.Device:
    dev = zigpy.device.Device(
        application=Mock(),
        ieee=t.EUI64.convert("00:11:22:33:44:55:66:77"),
        nwk=0x1234,
    )

    dev.node_desc = make_node_desc()

    if manufacturer_id is not None:
        dev.node_desc.manufacturer_code = manufacturer_id

    if model is not None:
        dev.model = model

    if manufacturer is not None:
        dev.manufacturer = manufacturer

    return dev


@attrs.define(frozen=True, kw_only=True)
class SelfContainedOtaImageMetadata(providers.BaseOtaImageMetadata):
    test_data: bytes

    async def _fetch(self) -> bytes:
        return self.test_data


def _test_z2m_index_entry(obj: dict, meta: providers.BaseOtaImageMetadata) -> bool:
    assert meta.checksum == "sha512:" + obj.pop("sha512")
    assert meta.image_type == obj.pop("imageType")
    assert meta.file_size == obj.pop("fileSize")
    assert meta.file_version == obj.pop("fileVersion")
    assert meta.manufacturer_id == obj.pop("manufacturerCode")
    assert meta.min_current_file_version == obj.pop("minFileVersion", None)
    assert meta.max_current_file_version == obj.pop("maxFileVersion", None)

    if "modelId" in obj:
        assert meta.model_names == (obj.pop("modelId"),)
    else:
        assert meta.model_names == ()

    if "manufacturerName" in obj:
        assert meta.manufacturer_names == tuple(obj.pop("manufacturerName"))
    else:
        assert meta.manufacturer_names == ()

    return True


async def test_local_z2m_provider():
    index_json = (FILES_DIR / "z2m_index.json").read_text()
    index_obj = json.loads(index_json)

    provider = providers.LocalZ2MProvider(FILES_DIR / "z2m_index.json")

    # Test equality
    assert provider == providers.LocalZ2MProvider(FILES_DIR / "z2m_index.json")
    assert provider != providers.LocalZ2MProvider(FILES_DIR / "z2m_index2.json")
    assert provider != providers.LocalZigpyProvider(FILES_DIR / "z2m_index.json")

    # Compatible with all devices
    assert provider.compatible_with_device(make_device(manufacturer_id=1234))
    assert provider.compatible_with_device(make_device(manufacturer_id=5678))

    index = await provider.load_index()

    assert len(index) == len(index_obj)

    for obj, meta in zip(index_obj, index):
        assert _test_z2m_index_entry(obj, meta)

        if isinstance(meta, providers.RemoteOtaImageMetadata):
            assert meta.url == obj.pop("url")
        elif isinstance(meta, providers.LocalOtaImageMetadata):
            assert meta.path == FILES_DIR / obj.pop("path")
            obj.pop("url")
        else:
            pytest.fail(f"Unexpected metadata type: {meta!r}")

        assert not obj


async def test_remote_z2m_provider():
    index_json = (FILES_DIR / "z2m_index.json").read_text()
    index_obj = json.loads(index_json)

    index_url = "https://raw.githubusercontent.com/Koenkk/zigbee-OTA/master/index.json"
    provider = providers.RemoteZ2MProvider(index_url)

    # Compatible with all devices
    assert provider.compatible_with_device(make_device(manufacturer_id=1234))
    assert provider.compatible_with_device(make_device(manufacturer_id=5678))

    with aioresponses() as mock_http:
        mock_http.get(
            index_url,
            body=index_json,
            content_type="text/plain; charset=utf-8",
        )

        index = await provider.load_index()

    assert len(index) == len(index_obj)

    for obj, meta in zip(index_obj, index):
        assert _test_z2m_index_entry(obj, meta)
        assert isinstance(meta, providers.RemoteOtaImageMetadata)
        assert meta.url == obj.pop("url")
        obj.pop("path", None)

        assert not obj


async def test_tradfri_provider_dirigera():
    index_json = (FILES_DIR / "ikea_version_info_dirigera.json").read_text()
    index_obj = json.loads(index_json)

    provider = providers.Tradfri()

    # Compatible only with IKEA devices
    assert provider.compatible_with_device(make_device(manufacturer_id=4476))
    assert not provider.compatible_with_device(make_device(manufacturer_id=4477))

    with aioresponses() as mock_http:
        mock_http.get(
            "https://fw.ota.homesmart.ikea.com/DIRIGERA/version_info.json",
            headers={"Location": "https://fw.ota.homesmart.ikea.com/check/update/prod"},
            status=302,
        )

        mock_http.get(
            "https://fw.ota.homesmart.ikea.com/check/update/prod",
            body=index_json,
            content_type="application/json",
        )

        index = await provider.load_index()

    # The provider will not allow itself to be loaded a second time this quickly
    with aioresponses() as mock_http:
        assert (await provider.load_index()) is None
        mock_http.assert_not_called()

    # Skip the gateway firmware
    filtered_version_info_obj = [
        obj
        for obj in index_obj
        if obj["fw_type"] == 2 and obj["fw_image_type"] not in (8710, 8704)
    ]
    assert len(index) == len(index_obj) - 3 == len(filtered_version_info_obj)

    for obj, meta in zip(filtered_version_info_obj, index):
        assert isinstance(meta, providers.RemoteOtaImageMetadata)
        assert meta.file_version == int(
            obj["fw_binary_url"].split("_v", 1)[1].split("_", 1)[0]
        )
        assert meta.image_type == obj.pop("fw_image_type")
        assert meta.checksum == "sha3-256:" + obj.pop("fw_sha3_256")
        assert meta.url == obj.pop("fw_binary_url")
        assert meta.manufacturer_id == providers.Tradfri.MANUFACTURER_IDS[0] == 4476

        obj.pop("fw_type")
        assert not obj

    meta = index[0]
    assert meta.image_type == 10242

    ota_contents = (
        FILES_DIR
        / "external/dl/ikea/mgm210l-light-cws-cv-rgbw_release_prod_v268572245_3ae78af7-14fd-44df-bca2-6d366f2e9d02.ota"
    ).read_bytes()

    with aioresponses() as mock_http:
        mock_http.get(
            meta.url,
            body=ota_contents,
            content_type="binary/octet-stream",
        )

        img = await meta.fetch()

    assert img.serialize() == ota_contents


@pytest.mark.parametrize(
    ("index_url", "index_file"),
    [
        (
            "http://fw.ota.homesmart.ikea.net/feed/version_info.json",
            "ikea_version_info_old.json",
        ),
        (
            "http://fw.test.ota.homesmart.ikea.net/feed/version_info.json",
            "ikea_version_info_old_test.json",
        ),
    ],
)
async def test_tradfri_provider_old(index_url: str, index_file: str) -> None:
    index_json = (FILES_DIR / index_file).read_text()
    index_obj = json.loads(index_json)

    provider = providers.Tradfri(index_url)

    # Compatible only with IKEA devices
    assert provider.compatible_with_device(make_device(manufacturer_id=4476))
    assert not provider.compatible_with_device(make_device(manufacturer_id=4477))

    with aioresponses() as mock_http:
        mock_http.get(index_url, body=index_json, content_type="application/json")

        index = await provider.load_index()

    # The provider will not allow itself to be loaded a second time this quickly
    with aioresponses() as mock_http:
        assert (await provider.load_index()) is None
        mock_http.assert_not_called()

    # Skip the gateway firmware
    filtered_version_info_obj = [
        obj
        for obj in index_obj
        if obj["fw_type"] == 2 and obj["fw_image_type"] not in (8710, 8704)
    ]
    assert index
    assert len(index) == len(filtered_version_info_obj)

    for obj, meta in zip(filtered_version_info_obj, index):
        assert isinstance(meta, providers.RemoteOtaImageMetadata)
        assert meta.file_version == (
            (obj.pop("fw_file_version_MSB") << 16)
            | (obj.pop("fw_file_version_LSB") << 0)
        )
        assert meta.manufacturer_id == obj.pop("fw_manufacturer_id")
        assert meta.image_type == obj.pop("fw_image_type")
        assert meta.file_size == obj.pop("fw_filesize")
        assert meta.url == obj.pop("fw_binary_url").replace("http://", "https://", 1)

        obj.pop("fw_type")
        assert not obj

    # Pick one of the images common to both feeds
    meta = next(m for m in index if "TRADFRI-motion-sensor-2-" in m.url)
    assert meta.image_type == 4552

    ota_contents = (
        FILES_DIR
        / "external/dl/ikea/10039874-1.0-TRADFRI-motion-sensor-2-2.0.022.ota.ota.signed"
    ).read_bytes()

    with aioresponses() as mock_http:
        mock_http.get(
            meta.url,
            body=ota_contents,
            content_type="binary/octet-stream",
        )

        img = await meta.fetch()

    assert img.serialize() in ota_contents


async def test_tradfri_provider_bad_image() -> None:
    index_json = (FILES_DIR / "ikea_version_info_old.json").read_text()
    provider = providers.Tradfri(
        "http://fw.ota.homesmart.ikea.net/feed/version_info.json"
    )

    with aioresponses() as mock_http:
        mock_http.get(
            "http://fw.ota.homesmart.ikea.net/feed/version_info.json",
            body=index_json,
            content_type="application/json",
        )

        index = await provider.load_index()

    assert index is not None
    meta = next(m for m in index if "TRADFRI-motion-sensor-2-" in m.url)
    assert meta.image_type == 4552

    ota_contents = (
        FILES_DIR
        / "external/dl/ikea/10039874-1.0-TRADFRI-motion-sensor-2-2.0.022.ota.ota.signed"
    ).read_bytes()

    # Flip a bit
    with aioresponses() as mock_http:
        flipped_contents = bytearray(ota_contents)
        flipped_contents[50000] ^= 0b00010000

        mock_http.get(
            meta.url,
            body=bytes(flipped_contents),
            content_type="binary/octet-stream",
        )

        with pytest.raises(ValueError, match="Block 3 has invalid checksum"):
            await meta.fetch()

    # Mess with the header
    with aioresponses() as mock_http:
        bad_contents = bytearray(ota_contents)
        bad_contents[0:4] = b"<htm"

        mock_http.get(
            meta.url,
            body=bytes(bad_contents),
            content_type="binary/octet-stream",
        )

        with pytest.raises(ValueError, match="Invalid signed container"):
            await meta.fetch()


async def test_tradfri_provider_invalid_json():
    index_json = (FILES_DIR / "ikea_version_info_dirigera.json").read_text()
    index_obj = [
        *json.loads(index_json),
        {
            "fw_image_type": 10242,
            "fw_type": 2,
            "fw_sha3_256": "e68e61bd57291e0b6358242e72ee2dfe098cb8b769f572b5b8f8e7a34dbcfaca",
            # We extract the version from the URL. Here, it is invalid.
            "fw_binary_url": "https://fw.ota.homesmart.ikea.com/files/bad.ota",
        },
    ]

    provider = providers.Tradfri()

    with aioresponses() as mock_http:
        mock_http.get(
            "https://fw.ota.homesmart.ikea.com/DIRIGERA/version_info.json",
            body=json.dumps(index_obj),
            content_type="application/json",
        )

        index = await provider.load_index()

    assert len(index) == len(index_obj) - 4


async def test_ledvance_provider():
    index_json = (FILES_DIR / "ledvance_firmwares.json").read_text()
    index_obj = json.loads(index_json)

    provider = providers.Ledvance()

    with aioresponses() as mock_http:
        mock_http.get(
            "https://api.update.ledvance.com/v1/zigbee/firmwares",
            body=index_json,
            content_type="application/json; charset=utf-8",
        )

        index = await provider.load_index()

    assert len(index) == len(index_obj["firmwares"])

    for obj, meta in zip(index_obj["firmwares"], index):
        assert isinstance(meta, providers.RemoteOtaImageMetadata)
        assert meta.image_type == obj["identity"]["product"]
        assert meta.checksum == "sha256:" + obj.pop("shA256")
        assert meta.release_notes == obj.pop("releaseNotes")
        assert meta.file_size == obj.pop("length")
        assert meta.manufacturer_id == obj["identity"]["company"]
        assert meta.model_names == (obj.pop("productName"),)
        assert meta.url == (
            f"https://api.update.ledvance.com/v1/zigbee/firmwares/download"
            f"?Company={obj['identity'].pop('company')}"
            f"&Product={obj['identity'].pop('product')}"
            f"&Version={obj['identity']['version'].pop('major')}"
            f".{obj['identity']['version'].pop('minor')}"
            f".{obj['identity']['version'].pop('build')}"
            f".{obj['identity']['version'].pop('revision')}"
        )

        assert not obj["identity"].pop("version")
        assert not obj.pop("identity")

        obj.pop("blob")
        obj.pop("extension")
        obj.pop("fullName")
        obj.pop("name")
        obj.pop("released")
        obj.pop("salesRegion")

        assert not obj


async def test_salus_provider():
    index_json = (FILES_DIR / "salus_firmware.json").read_text()
    index_obj = json.loads(index_json)

    provider = providers.Salus()

    with aioresponses() as mock_http:
        mock_http.get(
            "https://eu.salusconnect.io/demo/default/status/firmware",
            body=index_json,
        )

        index = await provider.load_index()

    filtered_firmware_obj = [o for o in index_obj["versions"] if o["version"] != ""]
    assert len(index) == len(index_obj["versions"]) - 1 == len(filtered_firmware_obj)

    for obj, meta in zip(filtered_firmware_obj, index):
        assert isinstance(meta, providers.SalusRemoteOtaImageMetadata)
        assert meta.url == obj.pop("url").replace("http://", "https://")
        assert meta.file_version == int(obj.pop("version"), 16)
        assert meta.model_names == (obj.pop("model"),)
        assert not obj


async def test_sonoff_provider():
    index_json = (FILES_DIR / "sonoff_upgrade.json").read_text()
    index_obj = json.loads(index_json)

    provider = providers.Sonoff()

    with aioresponses() as mock_http:
        mock_http.get(
            "https://zigbee-ota.sonoff.tech/releases/upgrade.json",
            body=index_json,
        )

        index = await provider.load_index()

    assert len(index) == len(index_obj)

    for obj, meta in zip(index_obj, index):
        assert isinstance(meta, providers.RemoteOtaImageMetadata)
        assert meta.url == obj.pop("fw_binary_url")
        assert meta.file_version == obj.pop("fw_file_version")
        assert meta.file_size == obj.pop("fw_filesize")
        assert meta.image_type == obj.pop("fw_image_type")
        assert meta.manufacturer_id == obj.pop("fw_manufacturer_id")
        assert meta.model_names == (obj.pop("model_id"),)
        assert not obj


async def test_inovelli_provider():
    index_json = (FILES_DIR / "inovelli_firmware-zha.json").read_text()
    index_obj = json.loads(index_json)

    provider = providers.Inovelli()

    with aioresponses() as mock_http:
        mock_http.get(
            "https://files.inovelli.com/firmware/firmware-zha-v2.json",
            body=index_json,
        )

        index = await provider.load_index()

    unpacked_objs = [(model, obj) for model, fws in index_obj.items() for obj in fws]
    assert len(index) == len(unpacked_objs)

    for (model, obj), meta in zip(unpacked_objs, index):
        assert isinstance(meta, providers.RemoteOtaImageMetadata)

        if obj["version"] == "0000000B":
            assert meta.file_version == 0x0000000B
        else:
            assert meta.file_version == int(obj["version"])

        obj.pop("version")

        assert meta.url == obj.pop("firmware")
        assert meta.manufacturer_id == obj.pop("manufacturer_id")
        assert meta.image_type == obj.pop("image_type")
        assert meta.model_names == (model,)

        obj.pop("channel")
        assert not obj


async def test_third_reality_provider():
    index_json = (FILES_DIR / "thirdreality_firmware.json").read_text()
    index_obj = json.loads(index_json)

    provider = providers.ThirdReality()
    assert provider == provider  # noqa: PLR0124
    assert provider != object()

    with aioresponses() as mock_http:
        mock_http.get(
            "https://tr-zha.s3.amazonaws.com/firmware.json",
            body=index_json,
            content_type="application/json",
        )

        index = await provider.load_index()

    assert len(index) == len(index_obj["versions"])

    for obj, meta in zip(index_obj["versions"], index):
        assert isinstance(meta, providers.RemoteOtaImageMetadata)
        assert meta.model_names == (obj.pop("modelId"),)
        assert meta.url == obj.pop("url")
        assert meta.image_type == obj.pop("imageType")
        assert meta.manufacturer_id == obj.pop("manufacturerId")
        assert meta.file_version == obj.pop("fileVersion")

        obj.pop("version")
        assert not obj


async def test_remote_zigpy_provider():
    index_json = (FILES_DIR / "remote_index.json").read_text()
    index_obj = json.loads(index_json)

    # A provider with no manufacturer IDs is compatible with all images
    assert providers.RemoteZigpyProvider("foo").compatible_with_device(
        make_device(manufacturer_id=4476)
    )

    # Ours will have a predefined list, however
    provider = providers.RemoteZigpyProvider(
        "https://example.org/fw/index.json", manufacturer_ids=[1, 2, 3]
    )

    with aioresponses() as mock_http:
        mock_http.get(
            "https://example.org/fw/index.json",
            body=index_json,
            content_type="application/json",
        )

        index = await provider.load_index()

    assert len(index) == len(index_obj["firmwares"])

    for obj, meta in zip(index_obj["firmwares"], index):
        assert isinstance(meta, providers.RemoteOtaImageMetadata)
        assert meta.url == obj.pop("binary_url")
        assert meta.file_version == obj.pop("file_version")
        assert meta.file_size == obj.pop("file_size")
        assert meta.image_type == obj.pop("image_type")
        assert meta.manufacturer_names == tuple(obj.pop("manufacturer_names"))
        assert meta.model_names == tuple(obj.pop("model_names"))
        assert meta.manufacturer_id == obj.pop("manufacturer_id")
        assert meta.changelog == obj.pop("changelog")
        assert meta.release_notes == obj.pop("release_notes")
        assert meta.checksum == obj.pop("checksum")
        assert meta.min_hardware_version == obj.pop("min_hardware_version")
        assert meta.max_hardware_version == obj.pop("max_hardware_version")
        assert meta.min_current_file_version == obj.pop("min_current_file_version")
        assert meta.max_current_file_version == obj.pop("max_current_file_version")
        assert meta.specificity == obj.pop("specificity")
        assert not obj

    assert provider.manufacturer_ids == (1, 2, 3)


async def test_local_zigpy_provider():
    index_obj = json.loads((FILES_DIR / "local_index.json").read_text())
    provider = providers.LocalZigpyProvider(FILES_DIR / "local_index.json")
    assert str(provider)

    # Test equality
    assert provider == providers.LocalZigpyProvider(FILES_DIR / "local_index.json")
    assert provider != providers.LocalZigpyProvider(FILES_DIR / "local_index2.json")
    assert provider != providers.LocalZ2MProvider(FILES_DIR / "local_index.json")

    index = await provider.load_index()

    assert len(index) == len(index_obj["firmwares"])

    for obj, meta in zip(index_obj["firmwares"], index):
        assert isinstance(meta, providers.LocalOtaImageMetadata)
        assert meta.path == pathlib.Path(FILES_DIR / obj.pop("path"))
        assert meta.file_version == obj.pop("file_version")
        assert meta.file_size == obj.pop("file_size")
        assert meta.image_type == obj.pop("image_type")
        assert meta.manufacturer_names == tuple(obj.pop("manufacturer_names"))
        assert meta.model_names == tuple(obj.pop("model_names"))
        assert meta.manufacturer_id == obj.pop("manufacturer_id")
        assert meta.changelog == obj.pop("changelog")
        assert meta.release_notes == obj.pop("release_notes")
        assert meta.checksum == obj.pop("checksum")
        assert meta.min_hardware_version == obj.pop("min_hardware_version")
        assert meta.max_hardware_version == obj.pop("max_hardware_version")
        assert meta.min_current_file_version == obj.pop("min_current_file_version")
        assert meta.max_current_file_version == obj.pop("max_current_file_version")
        assert meta.specificity == obj.pop("specificity")
        assert not obj


async def test_advanced_file_provider(tmp_path: pathlib.Path) -> None:
    files = list((FILES_DIR / "external/dl/local_provider").glob("[!.]*"))
    files.sort(key=lambda f: f.name)

    (tmp_path / "foo/bar").mkdir(parents=True)
    (tmp_path / "foo/bar" / files[0].name).write_bytes(files[0].read_bytes())
    (tmp_path / "foo" / files[1].name).write_bytes(files[1].read_bytes())
    (tmp_path / "empty").mkdir(parents=True)
    (tmp_path / "bad.ota").write_bytes(b"This is not an OTA file")

    provider = providers.AdvancedFileProvider(tmp_path)

    # Test equality
    assert provider == providers.AdvancedFileProvider(tmp_path)
    assert provider != providers.AdvancedFileProvider(tmp_path / "foo")
    assert provider != providers.LocalZigpyProvider(tmp_path)

    # The provider is compatible with all devices
    assert provider.compatible_with_device(make_device(manufacturer_id=4476))
    assert provider.compatible_with_device(make_device(manufacturer_id=4454))

    index = await provider.load_index()

    assert index is not None
    index.sort(key=lambda m: m.path.name)

    assert len(index) == len(files)

    for path, meta in zip(files, index):
        data = path.read_bytes()

        assert isinstance(meta, providers.LocalOtaImageMetadata)
        assert meta.path.name == path.name
        assert meta.checksum == "sha1:" + hashlib.sha1(data).hexdigest()
        assert meta.file_size == len(data)

        fw = await meta.fetch()
        assert fw.serialize() == data


async def test_salus_unzipping_valid():
    valid_tarball = (
        FILES_DIR / "external/dl/salus/Arjonstop_00000013.tar.gz"
    ).read_bytes()

    meta = providers.SalusRemoteOtaImageMetadata(
        file_version=0x00000013,
        model_names=("Arjonstop",),
        url="https://eu.salusconnect.io/download/firmware/e18c41d0-c3e7-48cc-bba5-aacc3f289640/Arjonstop_00000013.tar.gz",
    )

    with aioresponses() as mock_http:
        mock_http.get(meta.url, body=valid_tarball, content_type="application/gzip")
        ota_image = await meta.fetch()

    assert ota_image.header.file_version == meta.file_version == 19

    # This exists only in the OTA image
    assert ota_image.header.manufacturer_id == 43981


async def test_salus_unzipping_invalid():
    def _add_file_to_tar(tar: tarfile.TarFile, path: str, contents: bytes) -> None:
        info = tarfile.TarInfo(name=path)
        info.size = len(contents)
        tar.addfile(tarinfo=info, fileobj=io.BytesIO(contents))

    f = io.BytesIO()

    with tarfile.open(mode="w:gz", fileobj=f) as tar:
        _add_file_to_tar(tar, path="Jasco_5_0_1_OnOff_45856_v6.ota", contents=b"bad")
        _add_file_to_tar(
            tar,
            path="networkinfo.json",
            contents=json.dumps(
                {
                    "upgrade": [
                        {
                            "filename": "Jasco_5_0_1_OnOff_45856_v6.ota",
                            "version": "00000006",
                            "checksum": "AAAAAA03B382B7DD79B81FC50E13BEB7",
                            "type": 4,
                        }
                    ]
                }
            ).encode("utf-8"),
        )

    meta = providers.SalusRemoteOtaImageMetadata(
        file_version=0x00000006,
        model_names=("45856",),
        url="http://eu.salusconnect.io/download/firmware/a65779cd-13cd-41e5-a7e0-5346f24a0f62/45856_00000006.tar.gz",
    )

    with aioresponses() as mock_http:
        mock_http.get(meta.url, body=f.getvalue(), content_type="application/gzip")

        with pytest.raises(
            ValueError, match="Embedded OTA file has invalid MD5 checksum"
        ):
            await meta.fetch()


async def test_ota_fetch_size_and_checksum_validation(
    image_with_metadata: OtaImageWithMetadata,
) -> None:
    assert image_with_metadata.firmware is not None

    meta = SelfContainedOtaImageMetadata(
        file_version=image_with_metadata.metadata.file_version,
        checksum=image_with_metadata.metadata.checksum,
        file_size=image_with_metadata.metadata.file_size,
        test_data=image_with_metadata.firmware.serialize(),
    )

    fw = await meta.fetch()
    assert fw == image_with_metadata.firmware

    with pytest.raises(ValueError):
        await meta.replace(file_size=meta.file_size + 1).fetch()

    assert meta.checksum is not None
    assert not meta.checksum.endswith("c")

    with pytest.raises(ValueError):
        await meta.replace(checksum=meta.checksum[:-1] + "c").fetch()
