"""OTA support for Zigbee devices."""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import logging
import typing

from zigpy.config import (
    CONF_OTA_ADVANCED_DIR,
    CONF_OTA_ALLOW_ADVANCED_DIR,
    CONF_OTA_IKEA,
    CONF_OTA_INOVELLI,
    CONF_OTA_LEDVANCE,
    CONF_OTA_PROVIDER_MANUF_IDS,
    CONF_OTA_PROVIDER_URL,
    CONF_OTA_REMOTE_PROVIDERS,
    CONF_OTA_SALUS,
    CONF_OTA_SONOFF,
    CONF_OTA_THIRDREALITY,
    CONF_OTA_Z2M_LOCAL_INDEX,
    CONF_OTA_Z2M_REMOTE_INDEX,
)
from zigpy.ota.image import BaseOTAImage
import zigpy.ota.provider
import zigpy.types as t
import zigpy.util

if typing.TYPE_CHECKING:
    import zigpy.application
    from zigpy.zcl.clusters.general import Ota

_LOGGER = logging.getLogger(__name__)

TIMEDELTA_0 = datetime.timedelta()
DELAY_EXPIRATION = datetime.timedelta(hours=2)
OTA_FETCH_TIMEOUT = 20
MAXIMUM_DATA_SIZE = 40


@dataclasses.dataclass(frozen=True)
class OtaImageWithMetadata(t.BaseDataclassMixin):
    metadata: zigpy.ota.provider.BaseOtaImageMetadata
    image: BaseOTAImage | None

    def get_image_block(
        self,
        offset: t.uint32_t,
        size: t.uint8_t,
        *,
        maximum_data_size=MAXIMUM_DATA_SIZE,
    ) -> bytes:
        assert self.image is not None
        data = self.image.serialize()

        if offset > len(data):
            raise ValueError("Offset exceeds image size")

        return data[offset : offset + min(self.MAXIMUM_DATA_SIZE, size)]

    @property
    def _min_hardware_version(self) -> int | None:
        if self.metadata.min_hardware_version is not None:
            return self.metadata.min_hardware_version
        elif (
            self.img is not None
            and self.img.header.minimum_hardware_version is not None
        ):
            return self.img.header.minimum_hardware_version
        else:
            return None

    @property
    def _max_hardware_version(self) -> int | None:
        if self.metadata.max_hardware_version is not None:
            return self.metadata.max_hardware_version
        elif (
            self.img is not None
            and self.img.header.maximum_hardware_version is not None
        ):
            return self.img.header.maximum_hardware_version
        else:
            return None

    @property
    def specificity(self) -> int:
        """Return a numerical representation of the metadata specificity.
        Higher specificity is preferred to lower when picking a final OTA image."""
        total = 0

        if self.metadata.manufacturer_names:
            total += 100

        if self.metadata.model_names:
            total += 100

        if self.metadata.min_current_file_version is not None:
            total += 10

        if self.metadata.max_current_file_version is not None:
            total += 10

        if self.min_hardware_version is not None:
            total += 1

        if self.max_hardware_version is not None:
            total += 1

        return total

    def check_compatibility(
        self,
        device: zigpy.device.Device,
        query_cmd: Ota.ServerCommands.query_next_image,
    ) -> bool:
        """Check if an OTA image and its metadata is compatible with a device."""
        if self.metadata.file_version <= query_cmd.current_file_version:
            return False

        if self.metadata.manufacturer_id != query_cmd.manufacturer_id:
            return False

        if self.metadata.image_type != query_cmd.image_type:
            return False

        if self.metadata.model_names and device.model not in self.metadata.model_names:
            return False

        if (
            self.metadata.manufacturer_names
            and device.manufacturer not in self.metadata.manufacturer_names
        ):
            return False

        if (
            self.metadata.min_current_file_version is not None
            and query_cmd.current_file_version < self.metadata.min_current_file_version
        ):
            return False

        if (
            self.metadata.max_current_file_version is not None
            and query_cmd.current_file_version > self.metadata.max_current_file_version
        ):
            return False

        if (
            self._min_hardware_version is not None
            and query_cmd.hardware_version < self._min_hardware_version
        ):
            return False

        if (
            self._max_hardware_version is not None
            and query_cmd.hardware_version > self._max_hardware_version
        ):
            return False

        return True

    async def fetch(self) -> OtaImageWithMetadata:
        image = await zigpy.util.timeout(self.metadata.fetch(), OTA_FETCH_TIMEOUT)

        return self.replace(
            metadata=self.metadata,
            image=image,
        )


class OTA:
    """OTA Manager."""

    def __init__(
        self,
        config: dict[str, typing.Any],
        application: zigpy.application.ControllerApplication,
    ) -> None:
        self._config = config
        self._providers: list[zigpy.ota.provider.BaseOtaProvider] = []
        self._image_cache: dict[
            zigpy.ota.provider.BaseOtaImageMetadata, OtaImageWithMetadata
        ] = {}

        if self._config[CONF_OTA_ALLOW_ADVANCED_DIR]:
            self.providers.append(
                zigpy.ota.provider.AdvancedFileProvider(
                    self._config[CONF_OTA_ADVANCED_DIR]
                )
            )

        if self._config[CONF_OTA_IKEA]:
            self.providers.append(zigpy.ota.provider.Trådfri())

        if self._config[CONF_OTA_INOVELLI]:
            self.providers.append(zigpy.ota.provider.Inovelli())

        if self._config[CONF_OTA_LEDVANCE]:
            self.providers.append(zigpy.ota.provider.Ledvance())

        if self._config[CONF_OTA_SALUS]:
            self.providers.append(zigpy.ota.provider.Salus())

        if self._config[CONF_OTA_SONOFF]:
            self.providers.append(zigpy.ota.provider.Sonoff())

        if self._config[CONF_OTA_THIRDREALITY]:
            self.providers.append(zigpy.ota.provider.ThirdReality())

        for provider_config in self._config[CONF_OTA_REMOTE_PROVIDERS]:
            self.providers.append(
                zigpy.ota.provider.RemoteProvider(
                    url=provider_config[CONF_OTA_PROVIDER_URL],
                    manufacturer_ids=provider_config[CONF_OTA_PROVIDER_MANUF_IDS],
                )
            )

        if self._config[CONF_OTA_Z2M_LOCAL_INDEX]:
            self.providers.append(
                zigpy.ota.provider.LocalZ2MProvider(
                    self._config[CONF_OTA_Z2M_LOCAL_INDEX]
                )
            )

        if self._config[CONF_OTA_Z2M_REMOTE_INDEX]:
            self.providers.append(
                zigpy.ota.provider.RemoteZ2MProvider(
                    self._config[CONF_OTA_Z2M_REMOTE_INDEX]
                )
            )

    async def get_ota_image(
        self,
        device: zigpy.device.Device,
        query_cmd: Ota.ServerCommands.query_next_image,
    ) -> OtaImageWithMetadata | None:
        # Only consider providers that are compatible with the device
        compatible_providers = [
            p for p in self._providers if p.compatible_with_device(device)
        ]

        # Load the index of every provider
        for provider in compatible_providers:
            try:
                index = await zigpy.util.timeout(
                    provider.load_index(), OTA_FETCH_TIMEOUT
                )
            except Exception as exc:
                _LOGGER.debug(
                    "Failed to load provider %s index", provider, exc_info=exc
                )
                continue

            if index is None:
                continue

            # Cache its images
            for meta in index:
                if meta not in self._image_cache:
                    self._image_cache[meta] = OtaImageWithMetadata(
                        metadata=meta, image=None
                    )

        # Find all superficially compatible images. Note that if an image's contents
        # are unknown and its metadata does not describe hardware compatibility, we will
        # still download in the next step to double check, in case the file itself does.
        pre_candidates = {
            img.metadata: img
            for img in self._image_cache.values()
            if img.check_compatibility(device, query_cmd)
        }

        # Fetch all the candidates that are missing from the cache
        for result_coro in asyncio.as_completed(
            img.fetch() for img in pre_candidates if img.image is None
        ):
            try:
                img = await result_coro
            except Exception as exc:
                _LOGGER.debug("Failed to download image", exc_info=exc)
                continue

            self._image_cache[img.metadata] = img
            pre_candidates[img.metadata] = img

        # Now we have all of the necessary metadata to fully vet the candidates and
        # pick the best image
        highest_version = (-1, -1)
        highest_version_images: list[OtaImageWithMetadata] = []

        for img in pre_candidates.values():
            if img.check_compatibility(device, query_cmd):
                key = (img.header.file_version, img.specificity)

                if key < highest_version:
                    continue
                elif key > highest_version:
                    highest_version_images = []
                    highest_version = key

                highest_version_images.append(img)

        if not highest_version_images:
            # If no image is actually compatible with the device (i.e. the metadata is
            # incomplete and after an image download we exclude the file), we are done
            return None

        # If there are multiple candidates with the same specificity and version but
        # having different contents, bail out
        first_image = highest_version_images[0].image

        if any(img.image != first_image for img in highest_version_images[1:]):
            _LOGGER.warning(
                "Multiple compatible OTA images for device %s exist, not picking",
                device,
            )
            return None

        return highest_version_images[0]
