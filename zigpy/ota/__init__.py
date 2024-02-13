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
    CONF_OTA_ENABLED,
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

    query_next_image = Ota.ServerCommandDefs.query_next_image.schema

_LOGGER = logging.getLogger(__name__)

TIMEDELTA_0 = datetime.timedelta()
DELAY_EXPIRATION = datetime.timedelta(hours=2)
OTA_FETCH_TIMEOUT = 20
MAXIMUM_DATA_SIZE = 40


@dataclasses.dataclass(frozen=True)
class OtaImageWithMetadata(t.BaseDataclassMixin):
    metadata: zigpy.ota.provider.BaseOtaImageMetadata
    firmware: BaseOTAImage | None

    @property
    def version(self) -> int:
        return self.metadata.file_version

    def get_image_block(
        self,
        offset: t.uint32_t,
        size: t.uint8_t,
        *,
        maximum_data_size=MAXIMUM_DATA_SIZE,
    ) -> bytes:
        assert self.firmware is not None
        data = self.firmware.serialize()

        if offset > len(data):
            raise ValueError("Offset exceeds image size")

        return data[offset : offset + min(self.MAXIMUM_DATA_SIZE, size)]

    @property
    def _min_hardware_version(self) -> int | None:
        if self.metadata.min_hardware_version is not None:
            return self.metadata.min_hardware_version
        elif (
            self.firmware is not None
            and self.firmware.header.minimum_hardware_version is not None
        ):
            return self.firmware.header.minimum_hardware_version
        else:
            return None

    @property
    def _max_hardware_version(self) -> int | None:
        if self.metadata.max_hardware_version is not None:
            return self.metadata.max_hardware_version
        elif (
            self.firmware is not None
            and self.firmware.header.maximum_hardware_version is not None
        ):
            return self.firmware.header.maximum_hardware_version
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

        if self._min_hardware_version is not None:
            total += 1

        if self._max_hardware_version is not None:
            total += 1

        return total

    def check_compatibility(
        self,
        device: zigpy.device.Device,
        query_cmd: query_next_image,
    ) -> bool:
        """Check if an OTA image and its metadata is compatible with a device."""
        if self.metadata.file_version <= query_cmd.current_file_version:
            return False

        if self.metadata.manufacturer_id != query_cmd.manufacturer_code:
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

        if self._min_hardware_version is not None and (
            query_cmd.hardware_version is None
            or query_cmd.hardware_version < self._min_hardware_version
        ):
            return False

        if self._max_hardware_version is not None and (
            query_cmd.hardware_version is None
            or query_cmd.hardware_version > self._max_hardware_version
        ):
            return False

        return True

    async def fetch(self) -> OtaImageWithMetadata:
        firmware = await zigpy.util.timeout(self.metadata.fetch(), OTA_FETCH_TIMEOUT)

        return self.replace(
            metadata=self.metadata,
            firmware=firmware,
        )


class OTA:
    """OTA Manager."""

    def __init__(
        self,
        config: dict[str, typing.Any],
        application: zigpy.application.ControllerApplication,
    ) -> None:
        self._config = config
        self._application = application

        self._providers: list[zigpy.ota.provider.BaseOtaProvider] = []
        self._image_cache: dict[
            zigpy.ota.provider.BaseOtaImageMetadata, OtaImageWithMetadata
        ] = {}

        if config[CONF_OTA_ENABLED]:
            self._register_providers(self._config)

    def _register_providers(self, config: dict[str, typing.Any]) -> None:
        if config[CONF_OTA_ALLOW_ADVANCED_DIR]:
            self.register_provider(
                zigpy.ota.provider.AdvancedFileProvider(config[CONF_OTA_ADVANCED_DIR])
            )

        if config[CONF_OTA_IKEA]:
            self.register_provider(zigpy.ota.provider.Trådfri())

        if config[CONF_OTA_INOVELLI]:
            self.register_provider(zigpy.ota.provider.Inovelli())

        if config[CONF_OTA_LEDVANCE]:
            self.register_provider(zigpy.ota.provider.Ledvance())

        if config[CONF_OTA_SALUS]:
            self.register_provider(zigpy.ota.provider.Salus())

        if config[CONF_OTA_SONOFF]:
            self.register_provider(zigpy.ota.provider.Sonoff())

        if config[CONF_OTA_THIRDREALITY]:
            self.register_provider(zigpy.ota.provider.ThirdReality())

        for provider_config in config[CONF_OTA_REMOTE_PROVIDERS]:
            self.register_provider(
                zigpy.ota.provider.RemoteProvider(
                    url=provider_config[CONF_OTA_PROVIDER_URL],
                    manufacturer_ids=provider_config[CONF_OTA_PROVIDER_MANUF_IDS],
                )
            )

        if config[CONF_OTA_Z2M_LOCAL_INDEX]:
            self.register_provider(
                zigpy.ota.provider.LocalZ2MProvider(config[CONF_OTA_Z2M_LOCAL_INDEX])
            )

        if config[CONF_OTA_Z2M_REMOTE_INDEX]:
            self.register_provider(
                zigpy.ota.provider.RemoteZ2MProvider(config[CONF_OTA_Z2M_REMOTE_INDEX])
            )

    def register_provider(self, provider: zigpy.ota.provider.BaseOtaProvider) -> None:
        """Register a new OTA provider."""
        _LOGGER.debug("Registering new OTA provider: %s", provider)
        self._providers.append(provider)

    @zigpy.util.combine_concurrent_calls
    async def _load_provider_index(
        self, provider: zigpy.ota.provider.BaseOtaProvider
    ) -> list[zigpy.ota.provider.BaseOtaImageMetadata]:
        """Load the index of a provider."""

        return await zigpy.util.timeout(provider.load_index(), OTA_FETCH_TIMEOUT)

    @zigpy.util.combine_concurrent_calls
    async def _fetch_image(
        self, image: OtaImageWithMetadata
    ) -> list[OtaImageWithMetadata]:
        """Load the index of a provider."""

        return await zigpy.util.timeout(image.fetch(), OTA_FETCH_TIMEOUT)

    async def get_ota_image(
        self,
        device: zigpy.device.Device,
        query_cmd: query_next_image,
    ) -> OtaImageWithMetadata | None:
        # Only consider providers that are compatible with the device
        compatible_providers = [
            p for p in self._providers if p.compatible_with_device(device)
        ]

        # Load the index of every provider
        for provider in compatible_providers:
            try:
                index = await self._load_provider_index(provider)
            except Exception as exc:
                _LOGGER.debug("Failed to load provider %s", provider, exc_info=exc)
                continue

            if index is None:
                _LOGGER.debug(
                    "Provider %s was recently contacted, ignoring for now", provider
                )
                continue

            _LOGGER.debug("Loaded %d images from provider", len(index))

            # Cache its images. If the concurrent call's result was shared, the first
            # caller will cache these images
            for meta in index:
                if meta not in self._image_cache:
                    self._image_cache[meta] = OtaImageWithMetadata(
                        metadata=meta, firmware=None
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
            [
                self._fetch_image(img)
                for img in pre_candidates.values()
                if img.firmware is None
            ]
        ):
            try:
                img = await result_coro
            except Exception as exc:
                _LOGGER.debug("Failed to download image", exc_info=exc)
                continue

            # Cache the image if it isn't already cached
            if self._image_cache[img.metadata].firmware is None:
                _LOGGER.debug("Caching image %s", img)
                self._image_cache[img.metadata] = img

            pre_candidates[img.metadata] = img

        # Now we have all of the necessary metadata to fully vet the candidates and
        # pick the best image
        highest_version = (-1, -1)
        highest_version_images: list[OtaImageWithMetadata] = []

        for img in pre_candidates.values():
            if img.check_compatibility(device, query_cmd):
                assert img.firmware is not None
                key = (img.firmware.header.file_version, img.specificity)

                if key < highest_version:
                    continue
                elif key > highest_version:
                    highest_version_images = []
                    highest_version = key

                highest_version_images.append(img)

        if not highest_version_images:
            # If no image is actually compatible with the device (i.e. the metadata is
            # incomplete and after an image download we exclude the file), we are done
            _LOGGER.debug("No firmware is compatible with the device")
            return None

        # If there are multiple candidates with the same specificity and version but
        # having different contents, bail out
        first_fw = highest_version_images[0].firmware

        if any(img.firmware != first_fw for img in highest_version_images[1:]):
            _LOGGER.warning(
                "Multiple compatible OTA images for device %s exist, not picking",
                device,
            )
            return None

        _LOGGER.debug("Picking firmware %s", highest_version_images[0])

        return highest_version_images[0]
