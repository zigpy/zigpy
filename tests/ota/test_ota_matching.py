from __future__ import annotations

import asyncio
import hashlib
import typing
from unittest.mock import patch

import aiohttp
import attrs
import pytest

from tests.ota.test_ota_providers import SelfContainedOtaImageMetadata, make_device
from zigpy import config
import zigpy.device
import zigpy.ota
from zigpy.ota.image import FieldControl
from zigpy.ota.providers import BaseOtaImageMetadata, BaseOtaProvider
from zigpy.zcl.clusters.general import Ota


@pytest.fixture
def query_cmd():
    """Common query command for OTA tests."""
    return Ota.ServerCommandDefs.query_next_image.schema(
        field_control=FieldControl.HARDWARE_VERSIONS_PRESENT,
        manufacturer_code=0x1234,
        image_type=0xABCD,
        current_file_version=1,
        hardware_version=1,
    )


@pytest.fixture
def ota_hdr(query_cmd):
    """Common OTA image header for tests (can be customized with .replace())."""
    return zigpy.ota.image.OTAImageHeader(
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


@pytest.fixture
def ota_subelements():
    """Common OTA subelements for tests."""
    return [zigpy.ota.image.SubElement(tag_id=0x0000, data=b"fw_image")]


@pytest.fixture
def ota_image(ota_hdr, ota_subelements):
    """Common OTA image for tests."""
    return zigpy.ota.image.OTAImage(header=ota_hdr, subelements=ota_subelements)


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


async def test_ota_matching_priority(query_cmd, ota_hdr, ota_subelements) -> None:
    device = make_device(model="device model", manufacturer_id=0x1234)

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


async def test_ota_matching_ambiguous_error(query_cmd, ota_hdr) -> None:
    device = make_device(model="device model", manufacturer_id=0x1234)

    # Adjust header size for different firmware content
    ota_hdr = ota_hdr.replace(image_size=56 + 2 + 4 + 10)

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


async def test_ota_matching_ambiguous_specificity_tie_breaker(
    query_cmd, ota_hdr
) -> None:
    device = make_device(model="device model", manufacturer_id=0x1234)

    # Adjust header size for different firmware content
    ota_hdr = ota_hdr.replace(image_size=56 + 2 + 4 + 10)

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


async def test_ota_concurrent_fetching(query_cmd, ota_hdr) -> None:
    device = make_device(model="device model", manufacturer_id=0x1234)

    # Adjust header size for different firmware content
    ota_hdr = ota_hdr.replace(image_size=56 + 2 + 4 + 10)

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


async def test_ota_matching_hardware_version_changes_after_download(
    query_cmd, ota_hdr
) -> None:
    device = make_device(model="device model", manufacturer_id=0x1234)

    # Create headers with hardware version constraints
    ota_hdr_01 = ota_hdr.replace(
        header_length=60,
        field_control=FieldControl.HARDWARE_VERSIONS_PRESENT,
        minimum_hardware_version=0,
        maximum_hardware_version=1,
        image_size=56 + 2 + 4 + 4 + 10,
    )

    ota_hdr_27 = ota_hdr.replace(
        header_length=60,
        field_control=FieldControl.HARDWARE_VERSIONS_PRESENT,
        minimum_hardware_version=2,
        maximum_hardware_version=7,
        image_size=56 + 2 + 4 + 4 + 10,
    )

    index = [
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr_01,
                subelements=[
                    zigpy.ota.image.SubElement(tag_id=0x0000, data=b"Firmware 1")
                ],
            ).serialize(),
        ),
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            test_data=zigpy.ota.image.OTAImage(
                header=ota_hdr_27,
                subelements=[
                    zigpy.ota.image.SubElement(tag_id=0x0000, data=b"Firmware 2")
                ],
            ).serialize(),
        ),
    ]

    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    ota.register_provider(SelfContainedProvider(index))

    # Only the first image is considered
    images = await ota.get_ota_images(device, query_cmd)
    assert images.upgrades == (
        zigpy.ota.OtaImageWithMetadata(
            metadata=index[0],
            firmware=zigpy.ota.image.OTAImage.deserialize(index[0].test_data)[0],
        ),
    )


class TrustedSelfContainedProvider(SelfContainedProvider):
    """A trusted provider that defers image downloads."""

    TRUSTED = True


async def test_ota_trusted_provider_deferred_download(query_cmd, ota_image) -> None:
    """Trusted providers should not download images proactively."""
    device = make_device(model="device model", manufacturer_id=0x1234)
    test_data = ota_image.serialize()

    index = [
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            checksum="sha3-256:" + hashlib.sha3_256(test_data).hexdigest(),
            file_size=len(test_data),
            test_data=test_data,
        ),
    ]

    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    ota.register_provider(TrustedSelfContainedProvider(index))

    images = await ota.get_ota_images(device, query_cmd)

    # Image should be returned but firmware should NOT be downloaded
    assert len(images.upgrades) == 1
    assert images.upgrades[0].firmware is None
    assert images.upgrades[0].metadata.trusted is True


async def test_ota_untrusted_provider_proactive_download(query_cmd, ota_image) -> None:
    """Untrusted providers should download images proactively."""
    device = make_device(model="device model", manufacturer_id=0x1234)

    index = [
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            test_data=ota_image.serialize(),
        ),
    ]

    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    ota.register_provider(SelfContainedProvider(index))  # Untrusted (default)

    images = await ota.get_ota_images(device, query_cmd)

    # Image should be returned WITH firmware downloaded
    assert len(images.upgrades) == 1
    assert images.upgrades[0].firmware is not None
    assert images.upgrades[0].metadata.trusted is False


async def test_ota_trusted_provider_specificity_boost(query_cmd, ota_image) -> None:
    """Trusted provider images should have higher specificity."""
    device = make_device(model="device model", manufacturer_id=0x1234)
    test_data = ota_image.serialize()

    # Same image from trusted and untrusted providers
    trusted_meta = SelfContainedOtaImageMetadata(
        file_version=query_cmd.current_file_version + 1,
        manufacturer_id=query_cmd.manufacturer_code,
        checksum="sha3-256:" + hashlib.sha3_256(test_data).hexdigest(),
        file_size=len(test_data),
        test_data=test_data,
    )

    untrusted_meta = SelfContainedOtaImageMetadata(
        file_version=query_cmd.current_file_version + 1,
        manufacturer_id=query_cmd.manufacturer_code,
        test_data=test_data,
    )

    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    # Register untrusted first, then trusted to ensure ordering is due to specificity
    ota.register_provider(SelfContainedProvider([untrusted_meta]))
    ota.register_provider(TrustedSelfContainedProvider([trusted_meta]))

    images = await ota.get_ota_images(device, query_cmd)

    # Both images should be present, but trusted one should be first (higher specificity)
    assert len(images.upgrades) == 2
    assert images.upgrades[0].metadata.trusted is True
    assert images.upgrades[1].metadata.trusted is False


async def test_ota_trusted_provider_missing_sha3_256_checksum(
    query_cmd, caplog
) -> None:
    """Trusted images without SHA3-256 checksum should be removed with warning."""
    device = make_device(model="device model", manufacturer_id=0x1234)

    # Trusted image with sha256 checksum instead of sha3-256
    index = [
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            checksum="sha256:abc123",  # Wrong algorithm
            test_data=b"",  # Won't be fetched anyway
        ),
    ]

    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    ota.register_provider(TrustedSelfContainedProvider(index))

    images = await ota.get_ota_images(device, query_cmd)

    # Image should be removed due to missing SHA3-256 checksum
    assert len(images.upgrades) == 0
    assert "does not have SHA3-256 checksum" in caplog.text
