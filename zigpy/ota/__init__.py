"""OTA support for Zigbee devices."""

from __future__ import annotations

import asyncio
from asyncio import timeout as asyncio_timeout
from collections import defaultdict
import contextlib
import dataclasses
import datetime
import hashlib
import logging
import typing

from zigpy.config import (
    CONF_OTA_ADVANCED_DIR,
    CONF_OTA_ALLOW_ADVANCED_DIR,
    CONF_OTA_DISABLE_DEFAULT_PROVIDERS,
    CONF_OTA_ENABLED,
    CONF_OTA_EXTRA_PROVIDERS,
    CONF_OTA_IKEA,
    CONF_OTA_INOVELLI,
    CONF_OTA_LEDVANCE,
    CONF_OTA_PROVIDER_MANUF_IDS,
    CONF_OTA_PROVIDER_URL,
    CONF_OTA_PROVIDERS,
    CONF_OTA_REMOTE_PROVIDERS,
    CONF_OTA_SALUS,
    CONF_OTA_SONOFF,
    CONF_OTA_THIRDREALITY,
    CONF_OTA_Z2M_LOCAL_INDEX,
    CONF_OTA_Z2M_REMOTE_INDEX,
)
from zigpy.ota.image import BaseOTAImage
import zigpy.ota.providers
import zigpy.profiles.zha
import zigpy.types as t
import zigpy.util
from zigpy.zcl import OtaImageAvailableEvent, foundation
from zigpy.zcl.clusters.general import Ota, QueryNextImageCommand

if typing.TYPE_CHECKING:
    import zigpy.application
    import zigpy.device

_LOGGER = logging.getLogger(__name__)

OTA_FETCH_TIMEOUT = 20
MAX_DEVICES_CHECKING_IN_PER_BROADCAST = 15
BROADCAST_SETTLE_DELAY = 60


@dataclasses.dataclass(frozen=True)
class OtaImagesResult(t.BaseDataclassMixin):
    upgrades: tuple[OtaImageWithMetadata, ...]
    downgrades: tuple[OtaImageWithMetadata, ...]


@dataclasses.dataclass(frozen=True)
class OtaImageWithMetadata(t.BaseDataclassMixin):
    metadata: zigpy.ota.providers.BaseOtaImageMetadata
    firmware: BaseOTAImage | None

    def __repr__(self) -> str:
        if self.firmware is not None:
            firmware_repr = (
                f"<{type(self.firmware).__name__}: "
                f"{self.firmware.header.image_size} bytes>"
            )
        else:
            firmware_repr = "None"

        return (
            f"{type(self).__name__}("
            f"metadata={self.metadata!r}, "
            f"firmware={firmware_repr})"
        )

    @property
    def version(self) -> int:
        return self.metadata.file_version

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
    def _manufacturer_id(self) -> int | None:
        if self.metadata.manufacturer_id is not None:
            return self.metadata.manufacturer_id
        elif self.firmware is not None:
            return self.firmware.header.manufacturer_id
        else:
            return None

    @property
    def _image_type(self) -> int | None:
        if self.metadata.image_type is not None:
            return self.metadata.image_type
        elif self.firmware is not None:
            return self.firmware.header.image_type
        else:
            return None

    @property
    def specificity(self) -> int:
        """Return a numerical representation of the metadata specificity.
        Higher specificity is preferred to lower when picking a final OTA image.
        """

        total = 0

        if self.metadata.manufacturer_names:
            total += 1000

        if self.metadata.model_names:
            total += 1000

        if self._image_type is not None:
            total += 100

        if self._manufacturer_id is not None:
            total += 100

        if self.metadata.min_current_file_version is not None:
            total += 10

        if self.metadata.max_current_file_version is not None:
            total += 10

        if self._min_hardware_version is not None:
            total += 1

        if self._max_hardware_version is not None:
            total += 1

        # Boost the specificity
        if self.metadata.specificity is not None:
            total += self.metadata.specificity

        # Prefer images from trusted providers (e.g. zigpy-ota has richer metadata)
        if self.metadata.trusted:
            total += 10000

        return total

    def check_compatibility(
        self,
        device: zigpy.device.Device,
        query_cmd: QueryNextImageCommand,
    ) -> bool:
        """Check if an OTA image and its metadata is compatible with a device."""
        if (
            self._manufacturer_id is not None
            and self._manufacturer_id != query_cmd.manufacturer_code
        ):
            return False

        if self._image_type is not None and self._image_type != query_cmd.image_type:
            return False

        if self.metadata.model_names and device.model not in self.metadata.model_names:
            return False

        if (
            self.metadata.manufacturer_names
            and device.manufacturer not in self.metadata.manufacturer_names
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

    def check_version(self, current_file_version: int) -> bool:
        """Check if the image is a newer version than the device's current version."""
        if self.version <= current_file_version:
            return False

        if (
            self.metadata.min_current_file_version is not None
            and current_file_version < self.metadata.min_current_file_version
        ):
            return False

        if (
            self.metadata.max_current_file_version is not None
            and current_file_version > self.metadata.max_current_file_version
        ):
            return False

        return True

    async def fetch(self) -> OtaImageWithMetadata:
        firmware = await self.metadata.fetch()

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

        self._providers: list[zigpy.ota.providers.BaseOtaProvider] = []
        self._image_cache: dict[
            zigpy.ota.providers.BaseOtaImageMetadata, OtaImageWithMetadata
        ] = {}

        self._broadcast_loop_task = None

        if config[CONF_OTA_ENABLED]:
            self._register_providers(self._config)

    async def broadcast_loop(self, initial_delay: float, interval: float) -> None:
        """Periodically broadcast an image notification to get devices to check in."""

        await asyncio.sleep(initial_delay)

        while True:
            _LOGGER.debug("Broadcasting OTA notification")

            try:
                await self.broadcast_notify()
            except Exception:  # noqa: BLE001
                _LOGGER.debug("OTA broadcast failed", exc_info=True)

            # Wait for devices to respond with query_next_image before checking
            await asyncio.sleep(BROADCAST_SETTLE_DELAY)

            try:
                await self.check_all_devices_for_ota()
            except Exception:  # noqa: BLE001
                _LOGGER.debug("OTA image check failed", exc_info=True)

            await asyncio.sleep(interval)

    def start_periodic_broadcasts(self, initial_delay: float, interval: float) -> None:
        """Start the periodic OTA broadcasts."""
        self._broadcast_loop_task = asyncio.create_task(
            self.broadcast_loop(
                initial_delay=initial_delay,
                interval=interval,
            )
        )

    def stop_periodic_broadcasts(self) -> None:
        """Stop the periodic OTA broadcasts."""
        if self._broadcast_loop_task is not None:
            self._broadcast_loop_task.cancel()
            self._broadcast_loop_task = None

    def invalidate_provider_caches(self) -> None:
        """Invalidate all provider index caches, forcing a refresh on next check.

        Also clears the image cache so withdrawn images are not returned.
        Downloaded firmware will be re-fetched from untrusted providers on
        the next check, but this is acceptable for a user-initiated action.
        """
        for provider in self._providers:
            provider._index_last_updated = datetime.datetime.fromtimestamp(
                0, tz=datetime.UTC
            )

        self._image_cache.clear()

    async def check_cluster_for_ota(self, cluster: Ota) -> None:
        """Check OTA image availability for a single OTA cluster.

        If the cluster has a cached query command, calls get_ota_images and emits
        OtaImageAvailableEvent on the cluster. Intended to be called by consumers
        (e.g. ZHA) during entity setup after registering their event listener.
        """
        cmd = cluster.last_query_cmd
        if cmd is None:
            return

        device = cluster.endpoint.device
        images_result = await self.get_ota_images(device, cmd)

        cluster.emit(
            OtaImageAvailableEvent.event_type,
            OtaImageAvailableEvent(
                device_ieee=str(device.ieee),
                endpoint_id=cluster.endpoint.endpoint_id,
                cluster_type=cluster.cluster_type,
                cluster_id=cluster.cluster_id,
                images_result=images_result,
                query_cmd=cmd,
            ),
        )

    async def check_device_for_ota(
        self,
        device: zigpy.device.Device,
    ) -> None:
        """Check OTA image availability for a single device.

        Iterates the device's endpoints looking for OTA clusters with cached
        query commands and calls check_cluster_for_ota for each.
        """
        for ep_id, ep in device.endpoints.items():
            if ep_id == 0:
                continue

            # Prefer out_clusters (client) since that's where runtime routing
            # places query_next_image when both cluster types exist. If an
            # out_cluster exists, always use it (the in_cluster's cached query
            # would be stale and never updated again).
            for clusters in (ep.out_clusters, ep.in_clusters):
                cluster = clusters.get(Ota.cluster_id)
                if not isinstance(cluster, Ota):
                    continue

                await self.check_cluster_for_ota(cluster)
                break

    async def check_all_devices_for_ota(self) -> None:
        """Check OTA image availability for all devices with cached query commands.

        Called periodically from the broadcast loop and by consumers (e.g. ZHA)
        for user-initiated "check for updates" after invalidate_provider_caches().
        """
        for device in self._application.devices.values():
            try:
                await self.check_device_for_ota(device)
            except Exception:  # noqa: BLE001
                _LOGGER.debug(
                    "Failed to check OTA images for %s",
                    device.ieee,
                    exc_info=True,
                )

    def _register_providers(self, config: dict[str, typing.Any]) -> None:
        # Config gets a little complicated when you mix deprecated config and the new
        # providers config. We treat every option as an "intent" and merge configs in
        # the end.
        with_providers: list[zigpy.ota.providers.BaseOtaProvider] = [
            *config[CONF_OTA_PROVIDERS],
            *config[CONF_OTA_EXTRA_PROVIDERS],
        ]
        without_providers: set[type[zigpy.ota.providers.BaseOtaProvider]] = set(
            config[CONF_OTA_DISABLE_DEFAULT_PROVIDERS]
        ) - {type(p) for p in config[CONF_OTA_EXTRA_PROVIDERS]}

        def register_deprecated_provider(
            enabled: bool | str | None,
            provider: type[zigpy.ota.providers.BaseOtaProvider],
            config: dict[str, typing.Any] | None = None,
        ) -> None:
            if isinstance(enabled, str) and not config:
                config = {"url": enabled}
                enabled = True

            if not config:
                config = {}

            if enabled is True:
                with_providers.append(provider(**config))

                with contextlib.suppress(KeyError):
                    without_providers.remove(provider)
            elif enabled is False:
                without_providers.add(provider)
            else:
                pass

        register_deprecated_provider(
            enabled=config.get(CONF_OTA_IKEA),
            provider=zigpy.ota.providers.Tradfri,
        )
        register_deprecated_provider(
            enabled=config.get(CONF_OTA_INOVELLI),
            provider=zigpy.ota.providers.Inovelli,
        )
        register_deprecated_provider(
            enabled=config.get(CONF_OTA_LEDVANCE),
            provider=zigpy.ota.providers.Ledvance,
        )
        register_deprecated_provider(
            enabled=config.get(CONF_OTA_SALUS),
            provider=zigpy.ota.providers.Salus,
        )
        register_deprecated_provider(
            enabled=config.get(CONF_OTA_SONOFF),
            provider=zigpy.ota.providers.Sonoff,
        )
        register_deprecated_provider(
            enabled=config.get(CONF_OTA_THIRDREALITY),
            provider=zigpy.ota.providers.ThirdReality,
        )
        register_deprecated_provider(
            enabled=config.get(CONF_OTA_Z2M_REMOTE_INDEX),
            provider=zigpy.ota.providers.RemoteZ2MProvider,
        )
        register_deprecated_provider(
            enabled=config.get(CONF_OTA_ALLOW_ADVANCED_DIR),
            provider=zigpy.ota.providers.AdvancedFileProvider,
            config={"path": config.get(CONF_OTA_ADVANCED_DIR)},
        )
        register_deprecated_provider(
            enabled=None if config.get(CONF_OTA_Z2M_LOCAL_INDEX) is None else True,
            provider=zigpy.ota.providers.LocalZ2MProvider,
            config={"index_file": config.get(CONF_OTA_Z2M_LOCAL_INDEX)},
        )

        for provider_config in config.get(CONF_OTA_REMOTE_PROVIDERS, []):
            register_deprecated_provider(
                enabled=True,
                provider=zigpy.ota.providers.RemoteZigpyProvider,
                config={
                    "url": provider_config[CONF_OTA_PROVIDER_URL],
                    "manufacturer_ids": provider_config[CONF_OTA_PROVIDER_MANUF_IDS],
                },
            )

        replaced_providers: list[zigpy.ota.providers.BaseOtaProvider] = []

        for provider in with_providers:
            if type(provider) in without_providers:
                continue

            if provider.override_previous:
                replaced_providers = [
                    p for p in replaced_providers if type(p) is not type(provider)
                ]

            replaced_providers.append(provider)

        for provider in replaced_providers:
            self.register_provider(provider)

    def register_provider(self, provider: zigpy.ota.providers.BaseOtaProvider) -> None:
        """Register a new OTA provider."""
        _LOGGER.debug("Registering new OTA provider: %s", provider)
        self._providers.append(provider)

    @zigpy.util.combine_concurrent_calls
    async def _load_provider_index(
        self, provider: zigpy.ota.providers.BaseOtaProvider
    ) -> list[zigpy.ota.providers.BaseOtaImageMetadata] | None:
        """Load the index of a provider."""
        async with asyncio_timeout(OTA_FETCH_TIMEOUT):
            return await provider.load_index()

    @zigpy.util.combine_concurrent_calls
    async def _fetch_image(self, image: OtaImageWithMetadata) -> OtaImageWithMetadata:
        """Fetch an OTA image."""

        async with asyncio_timeout(OTA_FETCH_TIMEOUT):
            return await image.fetch()

    async def get_ota_images(
        self,
        device: zigpy.device.Device,
        query_cmd: QueryNextImageCommand,
    ) -> OtaImagesResult:
        """Get OTA images compatible with the device."""
        # Only consider providers that are compatible with the device
        compatible_providers = [
            p for p in self._providers if p.compatible_with_device(device)
        ]

        # Load the index of every provider
        for provider in compatible_providers:
            try:
                index = await self._load_provider_index(provider)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Failed to load provider %s", provider, exc_info=exc)
                continue

            if index is None:
                _LOGGER.debug(
                    "Provider %s was recently contacted, using cached response",
                    provider,
                )
                continue

            _LOGGER.debug("Loaded %d images from provider: %s", len(index), provider)

            # Cache its images. If the concurrent call's result was shared, the first
            # caller will cache these images
            for meta in index:
                if meta not in self._image_cache:
                    # Mark metadata as trusted if it comes from a trusted provider
                    if provider.TRUSTED and not meta.trusted:
                        meta = meta.replace(trusted=True)
                    self._image_cache[meta] = OtaImageWithMetadata(
                        metadata=meta, firmware=None
                    )

        # Find all superficially compatible images. Note that if an image's contents
        # are unknown and its metadata does not describe hardware compatibility, we will
        # still download in the next step to double check, in case the file itself does.
        candidates = sorted(
            [
                img
                for img in self._image_cache.values()
                if img.check_compatibility(device, query_cmd)
            ],
            key=lambda img: img.version,
        )

        upgrades = {
            img.metadata: img
            for img in candidates
            if img.check_version(query_cmd.current_file_version)
        }
        downgrades = {
            img.metadata: img for img in candidates if img.metadata not in upgrades
        }

        # Only download upgrade images from untrusted providers; trusted providers have
        # complete metadata so we can defer the download until install time
        undownloaded_images = [
            img
            for img in upgrades.values()
            if img.firmware is None and not img.metadata.trusted
        ]

        # Fetch all the candidates that are missing from the cache
        results = await asyncio.gather(
            *(self._fetch_image(img) for img in undownloaded_images),
            return_exceptions=True,
        )

        for img, result in zip(undownloaded_images, results, strict=True):
            if isinstance(result, BaseException):
                _LOGGER.debug(
                    "Failed to download image, ignoring: %s", img, exc_info=result
                )
                upgrades.pop(img.metadata)
                continue

            # `img` is the metadata without downloaded firmware. `result` is the same
            # image with downloaded firmware.
            img = result

            # Cache the image if it isn't already cached (or was cleared by
            # invalidate_provider_caches() during the download await)
            cached = self._image_cache.get(img.metadata)
            if cached is None or cached.firmware is None:
                _LOGGER.debug("Caching image %s", img)
                self._image_cache[img.metadata] = img

            if not img.check_compatibility(device, query_cmd):
                # Ignore images that become incompatible once downloaded
                del upgrades[img.metadata]
            else:
                upgrades[img.metadata] = img

        await self._remove_colliding_images(upgrades)

        return OtaImagesResult(
            upgrades=tuple(
                sorted(
                    upgrades.values(),
                    key=lambda img: (img.version, img.specificity),
                    reverse=True,
                )
            ),
            downgrades=tuple(
                sorted(
                    downgrades.values(),
                    key=lambda img: (img.version, img.specificity),
                    reverse=True,
                )
            ),
        )

    async def _remove_colliding_images(
        self,
        upgrades: dict[zigpy.ota.providers.BaseOtaImageMetadata, OtaImageWithMetadata],
    ) -> None:
        """Remove images with identical versions and specificity but differing contents.

        Also removes trusted images that lack a SHA3-256 checksum, since their content
        cannot be verified for collision detection.
        """
        # Structure: {(version, specificity): {content_hash: [images]}}
        collisions: defaultdict[
            tuple[int, int], defaultdict[str, list[OtaImageWithMetadata]]
        ] = defaultdict(lambda: defaultdict(list))

        images_to_remove: list[zigpy.ota.providers.BaseOtaImageMetadata] = []

        for img in upgrades.values():
            # Untrusted images are always downloaded above and ones that failed
            # to download were already removed; this should never happen.
            assert img.firmware is not None or img.metadata.trusted

            # Ignore trusted image without SHA3-256 checksum
            if img.firmware is None and (
                img.metadata.checksum is None
                or not img.metadata.checksum.startswith("sha3-256:")
            ):
                _LOGGER.warning(
                    "Trusted image %s does not have SHA3-256 checksum, ignoring", img
                )
                images_to_remove.append(img.metadata)
                continue

            # Calculate content hash from firmware if available, otherwise use metadata
            if img.firmware is not None:
                hasher = hashlib.sha3_256()
                await asyncio.get_running_loop().run_in_executor(
                    None, hasher.update, img.firmware.serialize()
                )
                content_hash = "sha3-256:" + hasher.hexdigest()
            else:
                assert img.metadata.checksum is not None  # Checked above
                content_hash = img.metadata.checksum

            collisions[img.version, img.specificity][content_hash].append(img)

        for meta in images_to_remove:
            upgrades.pop(meta)

        for (version, specificity), buckets in collisions.items():
            # If there are multiple unique hashes, we have a collision
            if len(buckets) < 2:
                continue

            bad_images = []

            for bucket in buckets.values():
                bad_images.extend(bucket)

            _LOGGER.warning(
                "Multiple unique OTA images for version %08X with specificity %d exist."
                " It is not possible to tell which image is correct so all %d of the"
                " colliding images will be ignored.",
                version,
                specificity,
                len(bad_images),
            )
            _LOGGER.debug("Colliding images: %s", bad_images)

            for img in bad_images:
                upgrades.pop(img.metadata)

    async def broadcast_notify(
        self,
        broadcast_address: t.BroadcastAddress = t.BroadcastAddress.ALL_DEVICES,
        jitter: int | None = None,
    ) -> None:
        tsn = self._application.get_sequence()

        command = Ota.ClientCommandDefs.image_notify

        # To avoid flooding huge networks, set the jitter such that we will probably
        # have a fixed number of devices checking in at once. All devices should
        # eventually check in, just not every time.
        if jitter is None:
            num_devices = len(self._application.devices)
            ratio = MAX_DEVICES_CHECKING_IN_PER_BROADCAST / max(1, num_devices)
            jitter = int(100 * min(max(0.0, ratio), 1.0))

        hdr, request = Ota._create_request(
            self=None,
            general=False,
            command_id=command.id,
            schema=command.schema,
            tsn=tsn,
            disable_default_response=True,
            direction=foundation.Direction.Server_to_Client,
            args=(),
            kwargs={
                "payload_type": Ota.ImageNotifyCommand.PayloadType.QueryJitter,
                "query_jitter": jitter,
            },
        )

        # Broadcast
        await self._application.send_packet(
            t.ZigbeePacket(
                src=t.AddrModeAddress(
                    addr_mode=t.AddrMode.NWK,
                    address=self._application.state.node_info.nwk,
                ),
                src_ep=1,
                dst=t.AddrModeAddress(
                    addr_mode=t.AddrMode.Broadcast,
                    address=broadcast_address,
                ),
                dst_ep=0xFF,
                tsn=tsn,
                profile_id=zigpy.profiles.zha.PROFILE_ID,
                cluster_id=Ota.cluster_id,
                data=t.SerializableBytes(hdr.serialize() + request.serialize()),
                tx_options=t.TransmitOptions.NONE,
                radius=30,
            )
        )
