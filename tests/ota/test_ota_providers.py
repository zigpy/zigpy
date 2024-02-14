import json
import pathlib

from aioresponses import aioresponses

from zigpy.ota import provider

FILES_DIR = pathlib.Path(__file__).parent / "files"


def _test_z2m_index_entry(obj: dict, meta: provider.BaseOtaImageMetadata) -> bool:
    assert meta.checksum == "sha512:" + obj["sha512"]
    assert meta.image_type == obj["imageType"]
    assert meta.file_size == obj["fileSize"]
    assert meta.manufacturer_id == obj["manufacturerCode"]
    assert meta.min_current_file_version == obj.get("minFileVersion", None)
    assert meta.max_current_file_version == obj.get("maxFileVersion", None)

    if "modelId" in obj:
        assert meta.model_names == (obj["modelId"],)
    else:
        assert meta.model_names == ()

    if "manufacturerNames" in obj:
        assert meta.manufacturer_names == tuple(obj["manufacturerNames"])
    else:
        assert meta.manufacturer_names == ()

    return True


async def test_remote_z2m_provider():
    index_json = (FILES_DIR / "z2m_index.json").read_text()
    index_obj = json.loads(index_json)

    index_url = "https://raw.githubusercontent.com/Koenkk/zigbee-OTA/master/index.json"

    z2m_provider = provider.RemoteZ2MProvider(index_url)

    with aioresponses() as mock_http:
        mock_http.get(
            index_url,
            body=index_json,
            content_type="text/plain; charset=utf-8",
        )

        index = await z2m_provider.load_index()

    assert len(index) == len(index_obj)

    for obj, meta in zip(index_obj, index):
        assert _test_z2m_index_entry(obj, meta)
        assert isinstance(meta, provider.RemoteOtaImageMetadata)
        assert meta.url == obj["url"]


async def test_local_z2m_provider():
    index_json = (FILES_DIR / "z2m_index.json").read_text()
    index_obj = json.loads(index_json)

    z2m_provider = provider.LocalZ2MProvider(FILES_DIR / "z2m_index.json")
    index = await z2m_provider.load_index()

    assert len(index) == len(index_obj)

    for obj, meta in zip(index_obj, index):
        assert _test_z2m_index_entry(obj, meta)

        if isinstance(meta, provider.RemoteOtaImageMetadata):
            assert meta.url == obj["url"]
        elif isinstance(meta, provider.LocalOtaImageMetadata):
            assert meta.path == FILES_DIR / obj["path"]
        else:
            assert False


async def test_trådfri_provider():
    version_info_json = (FILES_DIR / "ikea_version_info.json").read_text()
    version_info_obj = json.loads(version_info_json)

    ikea_provider = provider.Trådfri()

    with aioresponses() as mock_http:
        mock_http.get(
            "https://fw.ota.homesmart.ikea.com/DIRIGERA/version_info.json",
            headers={"Location": "https://fw.ota.homesmart.ikea.com/check/update/prod"},
            status=302,
        )

        mock_http.get(
            "https://fw.ota.homesmart.ikea.com/check/update/prod",
            body=version_info_json,
            content_type="application/json",
        )

        index = await ikea_provider.load_index()

    # Skip the gateway firmware
    filtered_version_info_obj = [obj for obj in version_info_obj if obj["fw_type"] == 2]
    assert len(index) == len(version_info_obj) - 1 == len(filtered_version_info_obj)

    for obj, meta in zip(filtered_version_info_obj, index):
        assert isinstance(meta, provider.RemoteOtaImageMetadata)
        assert meta.image_type == obj["fw_image_type"]
        assert meta.checksum == "sha3-256:" + obj["fw_sha3_256"]
        assert meta.url == obj["fw_binary_url"]
        assert meta.manufacturer_id == provider.Trådfri.MANUFACTURER_IDS[0] == 4476


async def test_ledvance_provider():
    firmwares_json = (FILES_DIR / "ledvance_firmwares.json").read_text()
    firmwares_obj = json.loads(firmwares_json)

    ledvance_provider = provider.Ledvance()

    with aioresponses() as mock_http:
        mock_http.get(
            "https://api.update.ledvance.com/v1/zigbee/firmwares",
            body=firmwares_json,
            content_type="application/json; charset=utf-8",
        )

        index = await ledvance_provider.load_index()

    assert len(index) == len(firmwares_obj["firmwares"])

    for obj, meta in zip(firmwares_obj["firmwares"], index):
        assert isinstance(meta, provider.RemoteOtaImageMetadata)
        assert meta.image_type == obj["identity"]["product"]
        assert meta.checksum == "sha256:" + obj["shA256"]
        assert meta.changelog == obj["releaseNotes"]
        assert meta.file_size == obj["length"]
        assert meta.manufacturer_id == obj["identity"]["company"]
        assert meta.url == (
            f"https://api.update.ledvance.com/v1/zigbee/firmwares/download"
            f"?Company={obj['identity']['company']}"
            f"&Product={obj['identity']['product']}"
            f"&Version={obj['identity']['version']['major']}"
            f".{obj['identity']['version']['minor']}"
            f".{obj['identity']['version']['build']}"
            f".{obj['identity']['version']['revision']}"
        )
