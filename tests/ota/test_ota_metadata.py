import hashlib
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_app
from zigpy.ota import OtaImageWithMetadata
import zigpy.ota.image
from zigpy.ota.providers import BaseOtaImageMetadata
from zigpy.zcl.clusters.general import Ota


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

    metadata = BaseOtaImageMetadata(  # type: ignore[call-arg]
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


def test_ota_mirrored_metadata(image_with_metadata: OtaImageWithMetadata) -> None:
    assert image_with_metadata._min_hardware_version == 1
    assert image_with_metadata._max_hardware_version == 5
    assert image_with_metadata._manufacturer_id == 0x1234
    assert image_with_metadata._image_type == 0x5678

    # Metadata info is preferred so the firmware file itself isn't necessary
    image_with_no_firmware = image_with_metadata.replace(firmware=None)
    assert image_with_no_firmware._min_hardware_version == 1
    assert image_with_no_firmware._max_hardware_version == 5
    assert image_with_no_firmware._manufacturer_id == 0x1234
    assert image_with_no_firmware._image_type == 0x5678

    # But we can use it
    image_with_no_metadata_hw_versions = image_with_metadata.replace(
        metadata=image_with_metadata.metadata.replace(
            min_hardware_version=None,
            max_hardware_version=None,
            manufacturer_id=None,
            image_type=None,
        )
    )
    assert image_with_no_metadata_hw_versions._min_hardware_version == 1
    assert image_with_no_metadata_hw_versions._max_hardware_version == 5
    assert image_with_no_metadata_hw_versions._manufacturer_id == 0x1234
    assert image_with_no_metadata_hw_versions._image_type == 0x5678

    # Only if all are missing will the properties be `None`
    image_with_no_hw_versions = image_with_metadata.replace(
        metadata=image_with_metadata.metadata.replace(
            min_hardware_version=None,
            max_hardware_version=None,
            manufacturer_id=None,
            image_type=None,
        ),
        firmware=None,
    )
    assert image_with_no_hw_versions._min_hardware_version is None
    assert image_with_no_hw_versions._max_hardware_version is None
    assert image_with_no_hw_versions._manufacturer_id is None
    assert image_with_no_hw_versions._image_type is None


def test_metadata_specificity(image_with_metadata: OtaImageWithMetadata) -> None:
    def replace_meta(**kwargs):
        return image_with_metadata.replace(
            metadata=image_with_metadata.metadata.replace(**kwargs)
        )

    # If we lose useful metadata, the specificity decreases
    assert (
        0
        < replace_meta(manufacturer_names=(), model_names=()).specificity
        < replace_meta(manufacturer_names=()).specificity
        < replace_meta(max_current_file_version=None).specificity
        < image_with_metadata.specificity
    )


async def test_metadata_compatibility(
    image_with_metadata: OtaImageWithMetadata,
    make_initialized_device,
) -> None:
    app = make_app({})
    await app.initialize()

    dev = make_initialized_device(app)
    dev.model = "model1"
    dev.manufacturer = "manufacturer1"

    assert image_with_metadata.version == 0x12345678

    query_cmd = Ota.ServerCommandDefs.query_next_image.schema(
        field_control=Ota.QueryNextImageCommand.FieldControl.HardwareVersion,
        manufacturer_code=0x1234,
        image_type=0x5678,
        current_file_version=0x12345678 - 5,
        hardware_version=3,
    )

    assert image_with_metadata.check_compatibility(dev, query_cmd)

    # The file version is ignored when checking compatibility
    assert image_with_metadata.check_compatibility(
        dev, query_cmd.replace(current_file_version=0x12345678)
    )

    # The min and max current file versions are respected
    assert image_with_metadata.check_version(0x12345678 - 10)
    assert image_with_metadata.check_version(0x12345678 - 2)
    assert not image_with_metadata.check_version(0x12345678 - 11)
    assert not image_with_metadata.check_version(0x12345678 - 1)
    assert not image_with_metadata.check_version(0x12345678)

    assert not image_with_metadata.check_compatibility(
        dev, query_cmd.replace(image_type=0xAAAA)
    )

    assert not image_with_metadata.check_compatibility(
        dev, query_cmd.replace(manufacturer_code=0xAAAA)
    )

    with patch.object(dev, attribute="_model", new="model3"):
        assert not image_with_metadata.check_compatibility(dev, query_cmd)

    with patch.object(dev, attribute="_manufacturer", new="manufacturer3"):
        assert not image_with_metadata.check_compatibility(dev, query_cmd)

    assert not image_with_metadata.check_compatibility(
        dev, query_cmd.replace(hardware_version=0)
    )

    assert not image_with_metadata.check_compatibility(
        dev, query_cmd.replace(hardware_version=100)
    )

    # The image is super well-specified: if anything is missing, it becomes incompatible
    assert not image_with_metadata.check_compatibility(
        dev,
        query_cmd.replace(
            field_control=Ota.QueryNextImageCommand.FieldControl(0),
            hardware_version=None,
        ),
    )

    await app.shutdown()


async def test_metadata_fetch(image_with_metadata: OtaImageWithMetadata) -> None:
    image_without_firmware = image_with_metadata.replace(firmware=None)
    assert image_with_metadata.firmware is not None

    # Pretend we download the image contents
    object.__setattr__(
        image_without_firmware.metadata,
        "_fetch",
        AsyncMock(return_value=image_with_metadata.firmware.serialize()),
    )

    # New image is identical
    new_img = await image_without_firmware.fetch()
    assert new_img == image_with_metadata
