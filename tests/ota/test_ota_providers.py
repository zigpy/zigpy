import json
import pathlib

from aioresponses import aioresponses

from zigpy.ota import providers

FILES_DIR = pathlib.Path(__file__).parent / "files"


def _test_z2m_index_entry(obj: dict, meta: providers.BaseOtaImageMetadata) -> bool:
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


async def test_local_z2m_provider():
    index_json = (FILES_DIR / "z2m_index.json").read_text()
    index_obj = json.loads(index_json)

    provider = providers.LocalZ2MProvider(FILES_DIR / "z2m_index.json")
    index = await provider.load_index()

    assert len(index) == len(index_obj)

    for obj, meta in zip(index_obj, index):
        assert _test_z2m_index_entry(obj, meta)

        if isinstance(meta, providers.RemoteOtaImageMetadata):
            assert meta.url == obj["url"]
        elif isinstance(meta, providers.LocalOtaImageMetadata):
            assert meta.path == FILES_DIR / obj["path"]
        else:
            assert False


async def test_remote_z2m_provider():
    index_json = (FILES_DIR / "z2m_index.json").read_text()
    index_obj = json.loads(index_json)

    index_url = "https://raw.githubusercontent.com/Koenkk/zigbee-OTA/master/index.json"
    provider = providers.RemoteZ2MProvider(index_url)

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
        assert meta.url == obj["url"]


async def test_trådfri_provider():
    index_json = (FILES_DIR / "ikea_version_info.json").read_text()
    index_obj = json.loads(index_json)

    provider = providers.Trådfri()

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

    # Skip the gateway firmware
    filtered_version_info_obj = [obj for obj in index_obj if obj["fw_type"] == 2]
    assert len(index) == len(index_obj) - 1 == len(filtered_version_info_obj)

    for obj, meta in zip(filtered_version_info_obj, index):
        assert isinstance(meta, providers.RemoteOtaImageMetadata)
        assert meta.file_version == int(
            obj["fw_binary_url"].split("_v", 1)[1].split("_", 1)[0]
        )
        assert meta.image_type == obj["fw_image_type"]
        assert meta.checksum == "sha3-256:" + obj["fw_sha3_256"]
        assert meta.url == obj["fw_binary_url"]
        assert meta.manufacturer_id == providers.Trådfri.MANUFACTURER_IDS[0] == 4476


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
        assert meta.url == obj["url"].replace("http://", "https://")
        assert meta.file_version == int(obj["version"], 16)
        assert meta.model_names == (obj["model"],)


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
        assert meta.url == obj["fw_binary_url"]
        assert meta.file_version == obj["fw_file_version"]
        assert meta.file_size == obj["fw_filesize"]
        assert meta.image_type == obj["fw_image_type"]
        assert meta.manufacturer_id == obj["fw_manufacturer_id"]
        assert meta.model_names == (obj["model_id"],)


async def test_inovelli_provider():
    index_json = (FILES_DIR / "inovelli_firmware-zha.json").read_text()
    index_obj = json.loads(index_json)

    provider = providers.Inovelli()

    with aioresponses() as mock_http:
        mock_http.get(
            "https://files.inovelli.com/firmware/firmware-zha.json",
            body=index_json,
        )

        index = await provider.load_index()

    unpacked_objs = [(model, obj) for model, fws in index_obj.items() for obj in fws]
    assert len(index) == len(unpacked_objs)

    for (model, obj), meta in zip(unpacked_objs, index):
        assert isinstance(meta, providers.RemoteOtaImageMetadata)
        assert meta.file_version == int(obj["version"], 16)
        assert meta.url == obj["firmware"]
        assert meta.manufacturer_id == obj["manufacturer_id"]
        assert meta.image_type == obj["image_type"]
        assert meta.model_names == (model,)


async def test_third_reality_provider():
    index_json = (FILES_DIR / "thirdreality_firmware.json").read_text()
    index_obj = json.loads(index_json)

    provider = providers.ThirdReality()

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
        assert meta.model_names == (obj["modelId"],)
        assert meta.url == obj["url"]
        assert meta.image_type == obj["imageType"]
        assert meta.manufacturer_id == obj["manufacturerId"]
        assert meta.file_version == obj["fileVersion"]


async def test_salus_unzipping_valid():
    valid_tarball = (FILES_DIR / "salus/Arjonstop_00000013.tar.gz").read_bytes()

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
