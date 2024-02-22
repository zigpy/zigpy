from __future__ import annotations

import pathlib
import typing

import aiohttp
import attrs

import zigpy.config as config
import zigpy.device
import zigpy.ota
from zigpy.ota.image import FieldControl
from zigpy.ota.providers import BaseOtaImageMetadata, BaseOtaProvider
from zigpy.zcl.clusters.general import Ota

from tests.ota.test_ota_providers import SelfContainedOtaImageMetadata, make_device


class SelfContainedProvider(BaseOtaProvider):
    def __init__(self, index: list[SelfContainedOtaImageMetadata]) -> None:
        super().__init__()
        self._index = index

    def compatible_with_device(self, device: zigpy.device.Device) -> bool:
        return True

    async def _load_index(
        self, session: aiohttp.ClientSession
    ) -> typing.AsyncIterator[BaseOtaImageMetadata]:
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
        SelfContainedOtaImageMetadata(  # type: ignore[call-arg]
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            #
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr,
                subelements=ota_subelements,
            ).serialize(),
        ),
        # Image type
        SelfContainedOtaImageMetadata(  # type: ignore[call-arg]
            file_version=query_cmd.current_file_version + 1,
            image_type=query_cmd.image_type,
            #
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr,
                subelements=ota_subelements,
            ).serialize(),
        ),
        # Model string
        SelfContainedOtaImageMetadata(  # type: ignore[call-arg]
            file_version=query_cmd.current_file_version + 1,
            model_names=(device.model,),
            #
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr,
                subelements=ota_subelements,
            ).serialize(),
        ),
        # Model string *and* more specific HW version: this is the right image to pick
        SelfContainedOtaImageMetadata(  # type: ignore[call-arg]
            file_version=query_cmd.current_file_version + 1,
            model_names=(device.model,),
            #
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr.replace(
                    minimum_hardware_version=1,
                    maximum_hardware_version=1,
                ),
                subelements=ota_subelements,
            ).serialize(),
        ),
        # Nothing to exclude but we can't be sure
        SelfContainedOtaImageMetadata(  # type: ignore[call-arg]
            file_version=query_cmd.current_file_version + 1,
            #
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr,
                subelements=ota_subelements,
            ).serialize(),
        ),
        # Irrelevant image
        SelfContainedOtaImageMetadata(  # type: ignore[call-arg]
            file_version=query_cmd.current_file_version - 1,
            #
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr.replace(file_version=query_cmd.current_file_version - 1),
                subelements=ota_subelements,
            ).serialize(),
        ),
        # Broken image that won't download
        BrokenOtaImageMetadata(  # type: ignore[call-arg]
            file_version=query_cmd.current_file_version + 1,
        ),
    ]

    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    ota.register_provider(BrokenProvider(index))
    ota.register_provider(SelfContainedProvider(index))
    ota.register_provider(BrokenProvider(index))

    image1 = await ota.get_ota_image(device, query_cmd)
    assert image1 is not None
    assert image1 == zigpy.ota.OtaImageWithMetadata(
        metadata=index[3],
        firmware=zigpy.ota.image.OTAImage.deserialize(index[3].test_data)[0],
    )

    image2 = await ota.get_ota_image(device, query_cmd)
    assert image2 is not None
    assert image2 is image1


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
        SelfContainedOtaImageMetadata(  # type: ignore[call-arg]
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            #
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr,
                subelements=[
                    zigpy.ota.image.SubElement(tag_id=0x0000, data=b"Firmware 1")
                ],
            ).serialize(),
        ),
        SelfContainedOtaImageMetadata(  # type: ignore[call-arg]
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            #
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
    image = await ota.get_ota_image(device, query_cmd)
    assert image is None


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
        SelfContainedOtaImageMetadata(  # type: ignore[call-arg]
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            #
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr,
                subelements=[
                    zigpy.ota.image.SubElement(tag_id=0x0000, data=b"Firmware 1")
                ],
            ).serialize(),
        ),
        SelfContainedOtaImageMetadata(  # type: ignore[call-arg]
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            #
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

    # No image will be provided if there is ambiguity
    image = await ota.get_ota_image(device, query_cmd)
    assert image is not None
    assert image == zigpy.ota.OtaImageWithMetadata(
        metadata=index[1],
        firmware=zigpy.ota.image.OTAImage.deserialize(index[1].test_data)[0],
    )
