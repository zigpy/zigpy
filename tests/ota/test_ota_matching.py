from __future__ import annotations

import asyncio
import pathlib
import typing
from unittest.mock import patch

import aiohttp
import attrs

from tests.ota.test_ota_providers import SelfContainedOtaImageMetadata, make_device
from zigpy import config
import zigpy.device
import zigpy.ota
from zigpy.ota.image import FieldControl
from zigpy.ota.providers import BaseOtaImageMetadata, BaseOtaProvider
from zigpy.zcl.clusters.general import Ota


class SelfContainedProvider(BaseOtaProvider):
    def __init__(
        self, index: list[SelfContainedOtaImageMetadata], load_index_delay: float = 0
    ) -> None:
        super().__init__()
        self._index = index
        self._load_index_delay = load_index_delay

    def compatible_with_device(self, device: zigpy.device.Device) -> bool:
        return True

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        await asyncio.sleep(self._load_index_delay)

        for meta in self._index:
            yield meta


class BrokenProvider(SelfContainedProvider):
    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
        if False:
            yield

        raise Exception("Broken provider")


@attrs.define(frozen=True, kw_only=True)
class BrokenOtaImageMetadata(BaseOtaImageMetadata):
    async def _fetch(self) -> bytes:
        raise RuntimeError("Some problem")


async def test_ota_matching_priority(tmp_path: pathlib.Path) -> None:
    device = make_device(model="device model", manufacturer_id=0x1234)

    query_cmd = Ota.ServerCommandDefs.query_next_image.schema(
        field_control=FieldControl.HARDWARE_VERSIONS_PRESENT,
        manufacturer_code=0x1234,
        image_type=0xABCD,
        current_file_version=1,
        hardware_version=1,
    )

    ota_hdr = zigpy.ota.image.OTAImageHeader(
        upgrade_file_id=zigpy.ota.image.OTAImageHeader.MAGIC_VALUE,
        file_version=query_cmd.current_file_version + 1,
        image_type=query_cmd.image_type,
        manufacturer_id=query_cmd.manufacturer_code,
        header_version=256,
        header_length=56,
        field_control=0,
        stack_version=2,
        header_string="This is a test header!",
        image_size=56 + 2 + 4 + 8,
    )

    ota_subelements = [zigpy.ota.image.SubElement(tag_id=0x0000, data=b"fw_image")]

    index = [
        # Manufacturer ID
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr,
                subelements=ota_subelements,
            ).serialize(),
        ),
        # Image type
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
            image_type=query_cmd.image_type,
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr,
                subelements=ota_subelements,
            ).serialize(),
        ),
        # Model string
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
            model_names=(device.model,),
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr,
                subelements=ota_subelements,
            ).serialize(),
        ),
        # Model string *and* more specific HW version: this is the right image to pick
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
            model_names=(device.model,),
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr.replace(
                    minimum_hardware_version=1,
                    maximum_hardware_version=1,
                ),
                subelements=ota_subelements,
            ).serialize(),
        ),
        # Nothing to exclude but we can't be sure
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr,
                subelements=ota_subelements,
            ).serialize(),
        ),
        # Irrelevant image
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version - 1,
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr.replace(file_version=query_cmd.current_file_version - 1),
                subelements=ota_subelements,
            ).serialize(),
        ),
        # Broken image that won't download
        BrokenOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
        ),
    ]

    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    ota.register_provider(BrokenProvider(index))
    ota.register_provider(SelfContainedProvider(index))
    ota.register_provider(BrokenProvider(index))

    images1 = await ota.get_ota_images(device, query_cmd)

    # The image that will be chosen is the correct one, others with less specificity
    # will still be present but they will be deprioritized
    assert images1.upgrades[0] == zigpy.ota.OtaImageWithMetadata(
        metadata=index[3],
        firmware=zigpy.ota.image.OTAImage.deserialize(index[3].test_data)[0],
    )

    images2 = await ota.get_ota_images(device, query_cmd)
    assert images2 == images1


async def test_ota_matching_ambiguous_error() -> None:
    device = make_device(model="device model", manufacturer_id=0x1234)

    query_cmd = Ota.ServerCommandDefs.query_next_image.schema(
        field_control=FieldControl.HARDWARE_VERSIONS_PRESENT,
        manufacturer_code=0x1234,
        image_type=0xABCD,
        current_file_version=1,
        hardware_version=1,
    )

    ota_hdr = zigpy.ota.image.OTAImageHeader(
        upgrade_file_id=zigpy.ota.image.OTAImageHeader.MAGIC_VALUE,
        file_version=query_cmd.current_file_version + 1,
        image_type=query_cmd.image_type,
        manufacturer_id=query_cmd.manufacturer_code,
        header_version=256,
        header_length=56,
        field_control=0,
        stack_version=2,
        header_string="This is a test header!",
        image_size=56 + 2 + 4 + 10,
    )

    index = [
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr,
                subelements=[
                    zigpy.ota.image.SubElement(tag_id=0x0000, data=b"Firmware 1")
                ],
            ).serialize(),
        ),
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr,
                subelements=[
                    zigpy.ota.image.SubElement(tag_id=0x0000, data=b"Firmware 2")
                ],
            ).serialize(),
        ),
    ]

    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    ota.register_provider(SelfContainedProvider(index))

    # No image will be provided if there is ambiguity
    images = await ota.get_ota_images(device, query_cmd)
    assert not images.upgrades


async def test_ota_matching_ambiguous_specificity_tie_breaker() -> None:
    device = make_device(model="device model", manufacturer_id=0x1234)

    query_cmd = Ota.ServerCommandDefs.query_next_image.schema(
        field_control=FieldControl.HARDWARE_VERSIONS_PRESENT,
        manufacturer_code=0x1234,
        image_type=0xABCD,
        current_file_version=1,
        hardware_version=1,
    )

    ota_hdr = zigpy.ota.image.OTAImageHeader(
        upgrade_file_id=zigpy.ota.image.OTAImageHeader.MAGIC_VALUE,
        file_version=query_cmd.current_file_version + 1,
        image_type=query_cmd.image_type,
        manufacturer_id=query_cmd.manufacturer_code,
        header_version=256,
        header_length=56,
        field_control=0,
        stack_version=2,
        header_string="This is a test header!",
        image_size=56 + 2 + 4 + 10,
    )

    index = [
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr,
                subelements=[
                    zigpy.ota.image.SubElement(tag_id=0x0000, data=b"Firmware 1")
                ],
            ).serialize(),
        ),
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr,
                subelements=[
                    zigpy.ota.image.SubElement(tag_id=0x0000, data=b"Firmware 2")
                ],
            ).serialize(),
            # Break the tie by boosting the image's specificity
            specificity=1,
        ),
    ]

    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    ota.register_provider(SelfContainedProvider(index))

    # No image will be provided if there is ambiguity but specificity is enough to break
    # the tie
    images = await ota.get_ota_images(device, query_cmd)
    assert len(images.upgrades) == 2
    assert images.upgrades[0] == zigpy.ota.OtaImageWithMetadata(
        metadata=index[1],
        firmware=zigpy.ota.image.OTAImage.deserialize(index[1].test_data)[0],
    )


async def test_ota_concurrent_fetching() -> None:
    device = make_device(model="device model", manufacturer_id=0x1234)

    query_cmd = Ota.ServerCommandDefs.query_next_image.schema(
        field_control=FieldControl.HARDWARE_VERSIONS_PRESENT,
        manufacturer_code=0x1234,
        image_type=0xABCD,
        current_file_version=1,
        hardware_version=1,
    )

    index = [
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            test_data=zigpy.ota.image.OTAImage(
                header=zigpy.ota.image.OTAImageHeader(
                    upgrade_file_id=zigpy.ota.image.OTAImageHeader.MAGIC_VALUE,
                    file_version=query_cmd.current_file_version + 1,
                    image_type=query_cmd.image_type,
                    manufacturer_id=query_cmd.manufacturer_code,
                    header_version=256,
                    header_length=56,
                    field_control=0,
                    stack_version=2,
                    header_string="This is a test header!",
                    image_size=56 + 2 + 4 + 10,
                ),
                subelements=[
                    zigpy.ota.image.SubElement(tag_id=0x0000, data=b"Firmware 1")
                ],
            ).serialize(),
        )
    ]

    provider = SelfContainedProvider(index, load_index_delay=0.1)

    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    ota.register_provider(provider)

    with patch.object(
        provider, "_load_index", wraps=provider._load_index
    ) as load_index:
        images1, images2 = await asyncio.gather(
            ota.get_ota_images(device, query_cmd),
            ota.get_ota_images(device, query_cmd),
        )

    # Concurrent requests were combined
    assert len(load_index.mock_calls) == 1
    assert images1 == images2
