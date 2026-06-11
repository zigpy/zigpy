from __future__ import annotations

import asyncio
import datetime
import hashlib
import typing
from unittest.mock import AsyncMock, patch

import aiohttp
import attrs
import pytest

from tests.conftest import add_initialized_device, make_app
from tests.ota.test_ota_providers import SelfContainedOtaImageMetadata, make_device
from zigpy import config
import zigpy.device
import zigpy.ota
from zigpy.ota.image import FieldControl
from zigpy.ota.providers import (
    AdvancedFileProvider,
    BaseOtaImageMetadata,
    BaseOtaProvider,
    LocalZ2MProvider,
    LocalZigpyProvider,
)
import zigpy.types
from zigpy.zcl import ClusterType, OtaImageAvailableEvent
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


@pytest.mark.parametrize("checksum", [None, "sha256:abc123"])
async def test_ota_trusted_provider_missing_sha3_256_checksum(
    query_cmd, checksum, caplog
) -> None:
    """Trusted images without SHA3-256 checksum should be removed with warning."""
    device = make_device(model="device model", manufacturer_id=0x1234)

    index = [
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            checksum=checksum,
            test_data=b"",  # Won't be fetched anyway
        ),
    ]

    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    ota.register_provider(TrustedSelfContainedProvider(index))

    images = await ota.get_ota_images(device, query_cmd)

    # Image should be removed due to missing SHA3-256 checksum
    assert len(images.upgrades) == 0
    assert "does not have SHA3-256 checksum" in caplog.text


def _make_device_with_ota_cluster(
    query_cmd,
    *,
    endpoint_id: int = 1,
    cluster_type: ClusterType = ClusterType.Client,
) -> tuple[zigpy.device.Device, Ota]:
    """Create a device with an OTA cluster and a cached query command."""
    device = make_device(model="device model", manufacturer_id=0x1234)

    ep = device.add_endpoint(endpoint_id)

    if cluster_type == ClusterType.Client:
        cluster = ep.add_output_cluster(Ota.cluster_id)
    else:
        cluster = ep.add_input_cluster(Ota.cluster_id)

    cluster.last_query_cmd = query_cmd

    return device, cluster


async def test_check_cluster_for_ota_emits_event(query_cmd) -> None:
    """check_cluster_for_ota calls get_ota_images and emits OtaImageAvailableEvent."""
    device, cluster = _make_device_with_ota_cluster(query_cmd)

    images_result = zigpy.ota.OtaImagesResult(upgrades=(), downgrades=())
    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    ota.get_ota_images = AsyncMock(return_value=images_result)

    events = []
    cluster.on_event(OtaImageAvailableEvent.event_type, events.append)

    await ota.check_cluster_for_ota(cluster)

    assert len(events) == 1
    assert isinstance(events[0], OtaImageAvailableEvent)
    assert events[0].device_ieee == str(device.ieee)
    assert events[0].endpoint_id == 1
    assert events[0].images_result is images_result
    assert events[0].query_cmd is query_cmd
    ota.get_ota_images.assert_called_once_with(device, query_cmd)


async def test_check_cluster_for_ota_no_query_cmd(query_cmd) -> None:
    """check_cluster_for_ota is a no-op when last_query_cmd is None."""
    _device, cluster = _make_device_with_ota_cluster(query_cmd)
    cluster.last_query_cmd = None

    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    ota.get_ota_images = AsyncMock()

    events = []
    cluster.on_event(OtaImageAvailableEvent.event_type, events.append)

    await ota.check_cluster_for_ota(cluster)

    assert len(events) == 0
    ota.get_ota_images.assert_not_called()


async def test_check_device_for_ota_finds_clusters(query_cmd) -> None:
    """check_device_for_ota iterates endpoints and checks each OTA cluster."""
    device, cluster1 = _make_device_with_ota_cluster(query_cmd, endpoint_id=1)
    # Add a second endpoint with an OTA cluster
    ep2 = device.add_endpoint(2)
    cluster2 = ep2.add_output_cluster(Ota.cluster_id)
    cluster2.last_query_cmd = query_cmd

    images_result = zigpy.ota.OtaImagesResult(upgrades=(), downgrades=())
    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    ota.get_ota_images = AsyncMock(return_value=images_result)

    events1 = []
    events2 = []
    cluster1.on_event(OtaImageAvailableEvent.event_type, events1.append)
    cluster2.on_event(OtaImageAvailableEvent.event_type, events2.append)

    await ota.check_device_for_ota(device)

    # Both clusters should have received events
    assert len(events1) == 1
    assert events1[0].endpoint_id == 1
    assert len(events2) == 1
    assert events2[0].endpoint_id == 2


async def test_check_device_for_ota_prefers_out_clusters(query_cmd) -> None:
    """check_device_for_ota prefers out_clusters over in_clusters on same endpoint."""
    device, in_cluster = _make_device_with_ota_cluster(
        query_cmd, endpoint_id=1, cluster_type=ClusterType.Server
    )
    ep = device.endpoints[1]

    # Also add as out_cluster on the same endpoint
    out_cluster = ep.add_output_cluster(Ota.cluster_id)
    out_cluster.last_query_cmd = query_cmd

    images_result = zigpy.ota.OtaImagesResult(upgrades=(), downgrades=())
    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    ota.get_ota_images = AsyncMock(return_value=images_result)

    in_events = []
    out_events = []
    in_cluster.on_event(OtaImageAvailableEvent.event_type, in_events.append)
    out_cluster.on_event(OtaImageAvailableEvent.event_type, out_events.append)

    await ota.check_device_for_ota(device)

    # Only out_cluster should receive the event (preferred)
    assert len(out_events) == 1
    assert len(in_events) == 0


async def test_check_device_for_ota_ignores_stale_in_cluster(query_cmd) -> None:
    """check_device_for_ota ignores in_cluster when out_cluster exists on same endpoint."""
    device, in_cluster = _make_device_with_ota_cluster(
        query_cmd, endpoint_id=1, cluster_type=ClusterType.Server
    )
    ep = device.endpoints[1]

    # Add out_cluster on same endpoint without a cached query
    out_cluster = ep.add_output_cluster(Ota.cluster_id)
    assert out_cluster.last_query_cmd is None

    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    ota.get_ota_images = AsyncMock()

    in_events = []
    in_cluster.on_event(OtaImageAvailableEvent.event_type, in_events.append)

    await ota.check_device_for_ota(device)

    # in_cluster has a cached query but should be ignored because the
    # out_cluster takes precedence (in_cluster's cache is stale)
    assert len(in_events) == 0
    ota.get_ota_images.assert_not_called()


async def test_check_device_for_ota_skips_no_query_cmd(query_cmd) -> None:
    """check_device_for_ota skips clusters without last_query_cmd."""
    device, cluster = _make_device_with_ota_cluster(query_cmd)
    cluster.last_query_cmd = None

    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    ota.get_ota_images = AsyncMock()

    await ota.check_device_for_ota(device)

    ota.get_ota_images.assert_not_called()


async def test_check_all_devices_for_ota(query_cmd) -> None:
    """check_all_devices_for_ota checks all devices, skipping those without OTA."""
    app = make_app({})

    dev1 = add_initialized_device(
        app, nwk=0x1234, ieee=zigpy.types.EUI64.convert("00:11:22:33:44:55:66:77")
    )
    cluster1 = dev1.endpoints[1].add_output_cluster(Ota.cluster_id)
    cluster1.last_query_cmd = query_cmd

    # device2 has no OTA cluster — should be skipped
    add_initialized_device(
        app, nwk=0x5678, ieee=zigpy.types.EUI64.convert("AA:BB:CC:DD:EE:FF:00:11")
    )

    images_result = zigpy.ota.OtaImagesResult(upgrades=(), downgrades=())
    app.ota.get_ota_images = AsyncMock(return_value=images_result)

    events = []
    cluster1.on_event(OtaImageAvailableEvent.event_type, events.append)

    await app.ota.check_all_devices_for_ota()

    assert len(events) == 1
    assert events[0].device_ieee == str(dev1.ieee)


async def test_check_all_devices_for_ota_tolerates_failure(query_cmd) -> None:
    """check_all_devices_for_ota continues if one device fails."""
    app = make_app({})

    dev1 = add_initialized_device(
        app, nwk=0x1234, ieee=zigpy.types.EUI64.convert("00:11:22:33:44:55:66:77")
    )
    cluster1 = dev1.endpoints[1].add_output_cluster(Ota.cluster_id)
    cluster1.last_query_cmd = query_cmd

    dev2 = add_initialized_device(
        app, nwk=0x5678, ieee=zigpy.types.EUI64.convert("AA:BB:CC:DD:EE:FF:00:11")
    )
    cluster2 = dev2.endpoints[1].add_output_cluster(Ota.cluster_id)
    cluster2.last_query_cmd = query_cmd

    images_result = zigpy.ota.OtaImagesResult(upgrades=(), downgrades=())
    app.ota.get_ota_images = AsyncMock(
        side_effect=[RuntimeError("provider down"), images_result]
    )

    events2 = []
    cluster2.on_event(OtaImageAvailableEvent.event_type, events2.append)

    await app.ota.check_all_devices_for_ota()

    # device2 should still get checked even though device1 failed
    assert len(events2) == 1


async def test_invalidate_provider_caches(query_cmd) -> None:
    """invalidate_provider_caches resets all provider index timestamps."""
    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    ota.register_provider(SelfContainedProvider([]))
    ota.register_provider(SelfContainedProvider([]))

    # Simulate providers having been recently loaded
    recent = datetime.datetime.now(datetime.UTC)
    for provider in ota._providers:
        provider._index_last_updated = recent

    # Verify caches are populated (load_index returns None = "use cache")
    for provider in ota._providers:
        assert await provider.load_index() is None

    ota.invalidate_provider_caches()

    # After invalidation, timestamps should be reset to epoch
    epoch = datetime.datetime.fromtimestamp(0, tz=datetime.UTC)
    for provider in ota._providers:
        assert provider._index_last_updated == epoch

    # load_index should now return fresh data instead of None
    for provider in ota._providers:
        result = await provider.load_index()
        assert result is not None  # Empty list, not None (which means "cached")


async def test_invalidate_provider_caches_clears_image_cache(
    query_cmd, ota_image
) -> None:
    """invalidate_provider_caches clears the image cache so withdrawn images disappear."""
    device = make_device(model="device model", manufacturer_id=0x1234)

    index_with_image = [
        SelfContainedOtaImageMetadata(
            file_version=query_cmd.current_file_version + 1,
            manufacturer_id=query_cmd.manufacturer_code,
            image_type=query_cmd.image_type,
            test_data=ota_image.serialize(),
        ),
    ]

    ota = zigpy.ota.OTA(config={config.CONF_OTA_ENABLED: False}, application=None)
    provider = SelfContainedProvider(index_with_image)
    ota.register_provider(provider)

    # First check finds the upgrade
    result1 = await ota.get_ota_images(device, query_cmd)
    assert len(result1.upgrades) == 1

    # Provider now returns an empty index (image was withdrawn)
    provider._index = []
    ota.invalidate_provider_caches()

    # Second check should find no upgrades
    result2 = await ota.get_ota_images(device, query_cmd)
    assert len(result2.upgrades) == 0


async def test_ota_provider_equality_requires_exact_type() -> None:
    """Providers of different types with the same URL do not compare equal."""
    untrusted = SelfContainedProvider([])
    trusted = TrustedSelfContainedProvider([])

    assert untrusted == SelfContainedProvider([])
    assert untrusted != trusted
    assert trusted != untrusted

    # Comparing against a non-provider falls back to the reflected comparison
    assert untrusted != "not a provider"

    # Distinct provider types occupy distinct dict keys, equal providers share one
    buckets = {untrusted: 1, trusted: 2}
    assert len(buckets) == 2
    assert buckets[SelfContainedProvider([])] == 1
    assert buckets[TrustedSelfContainedProvider([])] == 2


async def test_ota_provider_hash_includes_type(tmp_path) -> None:
    """Distinct provider types hashing over the same fields do not collide."""
    index_file = tmp_path / "index.json"

    local_zigpy = LocalZigpyProvider(index_file=index_file)
    local_z2m = LocalZ2MProvider(index_file=index_file)
    advanced = AdvancedFileProvider(path=tmp_path)

    buckets = {local_zigpy: 1, local_z2m: 2, advanced: 3}
    assert len(buckets) == 3
    assert buckets[LocalZigpyProvider(index_file=index_file)] == 1
    assert buckets[LocalZ2MProvider(index_file=index_file)] == 2
    assert buckets[AdvancedFileProvider(path=tmp_path)] == 3
