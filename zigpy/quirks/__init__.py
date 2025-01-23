"""Zigpy quirks module."""

from __future__ import annotations

import logging
import typing

from zigpy.const import (  # noqa: F401
    SIG_ENDPOINTS,
    SIG_EP_INPUT,
    SIG_EP_OUTPUT,
    SIG_EP_PROFILE,
    SIG_EP_TYPE,
    SIG_MANUFACTURER,
    SIG_MODEL,
    SIG_MODELS_INFO,
    SIG_NODE_DESC,
    SIG_SKIP_CONFIG,
)
import zigpy.device
import zigpy.endpoint
from zigpy.quirks.registry import DeviceRegistry
import zigpy.types as t
from zigpy.types.basic import uint16_t
import zigpy.zcl
from zigpy.zcl import foundation
from zigpy.zdo import ZDO

if typing.TYPE_CHECKING:
    from zigpy.application import ControllerApplication

_LOGGER = logging.getLogger(__name__)

DEVICE_REGISTRY = _DEVICE_REGISTRY = DeviceRegistry()
_uninitialized_device_message_handlers = []


def get_device(
    device: zigpy.device.Device, registry: DeviceRegistry | None = None
) -> zigpy.device.Device:
    """Get a CustomDevice object, if one is available"""
    if registry is None:
        return _DEVICE_REGISTRY.get_device(device)

    return registry.get_device(device)


def get_quirk_list(
    manufacturer: str, model: str, registry: DeviceRegistry | None = None
):
    """Get the Quirk list for a given manufacturer and model."""
    if registry is None:
        return _DEVICE_REGISTRY.registry_v1[manufacturer][model]

    return registry.registry_v1[manufacturer][model]


def register_uninitialized_device_message_handler(handler: typing.Callable) -> None:
    """Register an handler for messages received by uninitialized devices.

    each handler is passed same parameters as
    zigpy.application.ControllerApplication.handle_message
    """
    if handler not in _uninitialized_device_message_handlers:
        _uninitialized_device_message_handlers.append(handler)


class BaseCustomDevice(zigpy.device.Device):
    """Base class for custom devices."""

    _copy_cluster_attr_cache = False
    replacement: dict[str, typing.Any] = {}

    def __init__(
        self,
        application: ControllerApplication,
        ieee: t.EUI64,
        nwk: t.NWK,
        replaces: zigpy.device.Device,
    ) -> None:
        super().__init__(application, ieee, nwk)

        def set_device_attr(attr):
            if attr in self.replacement:
                setattr(self, attr, self.replacement[attr])
            else:
                setattr(self, attr, getattr(replaces, attr))

        for attr in ("lqi", "rssi", "last_seen", "relays"):
            setattr(self, attr, getattr(replaces, attr))

        set_device_attr("status")
        set_device_attr(SIG_NODE_DESC)
        set_device_attr(SIG_MANUFACTURER)
        set_device_attr(SIG_MODEL)
        set_device_attr(SIG_SKIP_CONFIG)
        for endpoint_id in self.replacement.get(SIG_ENDPOINTS, {}):
            self.add_endpoint(endpoint_id, replace_device=replaces)

    def add_endpoint(
        self, endpoint_id: int, replace_device: zigpy.device.Device | None = None
    ) -> zigpy.endpoint.Endpoint:
        if endpoint_id not in self.replacement.get(SIG_ENDPOINTS, {}):
            return super().add_endpoint(endpoint_id)

        endpoints = self.replacement[SIG_ENDPOINTS]

        if isinstance(endpoints[endpoint_id], tuple):
            custom_ep_type = endpoints[endpoint_id][0]
            replacement_data = endpoints[endpoint_id][1]
        else:
            custom_ep_type = CustomEndpoint
            replacement_data = endpoints[endpoint_id]

        ep = custom_ep_type(self, endpoint_id, replacement_data, replace_device)
        self.endpoints[endpoint_id] = ep
        return ep

    async def apply_custom_configuration(self, *args, **kwargs):
        """Hook for applications to instruct instances to apply custom configuration."""
        for endpoint in self.endpoints.values():
            if isinstance(endpoint, ZDO):
                continue
            for cluster in endpoint.in_clusters.values():
                if (
                    isinstance(cluster, CustomCluster)
                    and cluster.apply_custom_configuration
                    != CustomCluster.apply_custom_configuration
                ):
                    await cluster.apply_custom_configuration(*args, **kwargs)
            for cluster in endpoint.out_clusters.values():
                if (
                    isinstance(cluster, CustomCluster)
                    and cluster.apply_custom_configuration
                    != CustomCluster.apply_custom_configuration
                ):
                    await cluster.apply_custom_configuration(*args, **kwargs)


class CustomDevice(BaseCustomDevice):
    """Implementation of a quirks v1 custom device."""

    signature = None

    def __init_subclass__(cls) -> None:
        if getattr(cls, "signature", None) is not None:
            _DEVICE_REGISTRY.add_to_registry(cls)


class CustomEndpoint(zigpy.endpoint.Endpoint):
    """Custom endpoint implementation for quirks."""

    def __init__(
        self,
        device: BaseCustomDevice,
        endpoint_id: int,
        replacement_data: dict[str, typing.Any],
        replace_device: zigpy.device.Device,
    ) -> None:
        super().__init__(device, endpoint_id)

        def set_device_attr(attr):
            if attr in replacement_data:
                setattr(self, attr, replacement_data[attr])
            else:
                setattr(self, attr, getattr(replace_device[endpoint_id], attr))

        set_device_attr(SIG_EP_PROFILE)
        set_device_attr(SIG_EP_TYPE)
        self.status = zigpy.endpoint.Status.ZDO_INIT

        for c in replacement_data.get(SIG_EP_INPUT, []):
            if isinstance(c, int):
                cluster = None
                cluster_id = c
            else:
                cluster = c(self, is_server=True)
                cluster_id = cluster.cluster_id
            cluster = self.add_input_cluster(cluster_id, cluster)
            if self.device._copy_cluster_attr_cache:
                if (
                    endpoint_id in replace_device.endpoints
                    and cluster_id in replace_device.endpoints[endpoint_id].in_clusters
                ):
                    cluster._attr_cache = (
                        replace_device[endpoint_id]
                        .in_clusters[cluster_id]
                        ._attr_cache.copy()
                    )

        for c in replacement_data.get(SIG_EP_OUTPUT, []):
            if isinstance(c, int):
                cluster = None
                cluster_id = c
            else:
                cluster = c(self, is_server=False)
                cluster_id = cluster.cluster_id
            cluster = self.add_output_cluster(cluster_id, cluster)
            if self.device._copy_cluster_attr_cache:
                if (
                    endpoint_id in replace_device.endpoints
                    and cluster_id in replace_device.endpoints[endpoint_id].out_clusters
                ):
                    cluster._attr_cache = (
                        replace_device[endpoint_id]
                        .out_clusters[cluster_id]
                        ._attr_cache.copy()
                    )


class CustomCluster(zigpy.zcl.Cluster):
    """Custom cluster implementation for quirks."""

    _skip_registry = True
    _CONSTANT_ATTRIBUTES: dict[int, typing.Any] | None = None

    manufacturer_id_override: t.uint16_t | None = None

    @property
    def _is_manuf_specific(self) -> bool:
        """Return True if cluster_id is within manufacturer specific range."""
        return 0xFC00 <= self.cluster_id <= 0xFFFF

    def _has_manuf_attr(self, attrs_to_process: typing.Iterable | list | dict) -> bool:
        """Return True if contains a manufacturer specific attribute."""
        if self._is_manuf_specific:
            return True

        for attr_id in attrs_to_process:
            if (
                attr_id in self.attributes
                and self.attributes[attr_id].is_manufacturer_specific
            ):
                return True

        return False

    @property
    def _manufacturer_id(self) -> int | None:
        """Return manufacturer id, accounting for local overrides."""
        return (
            self.manufacturer_id_override
            if self.manufacturer_id_override is not None
            else self.endpoint.manufacturer_id
        )

    async def command(
        self,
        command_id: foundation.GeneralCommand | int | t.uint8_t,
        *args,
        manufacturer: int | t.uint16_t | None = None,
        expect_reply: bool = True,
        tsn: int | t.uint8_t | None = None,
        **kwargs: typing.Any,
    ) -> typing.Coroutine:
        command = self.server_commands[command_id]

        if manufacturer is None and (
            self._is_manuf_specific or command.is_manufacturer_specific
        ):
            manufacturer = self._manufacturer_id

        return await self.request(
            False,
            command.id,
            command.schema,
            *args,
            manufacturer=manufacturer,
            expect_reply=expect_reply,
            tsn=tsn,
            **kwargs,
        )

    async def client_command(
        self,
        command_id: foundation.GeneralCommand | int | t.uint8_t,
        *args,
        manufacturer: int | t.uint16_t | None = None,
        tsn: int | t.uint8_t | None = None,
        **kwargs: typing.Any,
    ):
        command = self.client_commands[command_id]

        if manufacturer is None and (
            self._is_manuf_specific or command.is_manufacturer_specific
        ):
            manufacturer = self._manufacturer_id

        return await self.reply(
            False,
            command.id,
            command.schema,
            *args,
            manufacturer=manufacturer,
            tsn=tsn,
            **kwargs,
        )

    async def read_attributes_raw(
        self, attributes: list[uint16_t], manufacturer: uint16_t | None = None, **kwargs
    ):
        if not self._CONSTANT_ATTRIBUTES:
            return await super().read_attributes_raw(
                attributes, manufacturer=manufacturer, **kwargs
            )

        succeeded = [
            foundation.ReadAttributeRecord(
                attrid=attr,
                status=foundation.Status.SUCCESS,
                value=foundation.TypeValue(
                    type=None,
                    value=self._CONSTANT_ATTRIBUTES[attr],
                ),
            )
            for attr in attributes
            if attr in self._CONSTANT_ATTRIBUTES
        ]

        attrs_to_read = [
            attr for attr in attributes if attr not in self._CONSTANT_ATTRIBUTES
        ]

        if not attrs_to_read:
            return [succeeded]

        results = await super().read_attributes_raw(
            attrs_to_read, manufacturer=manufacturer, **kwargs
        )
        if not isinstance(results[0], list):
            for attrid in attrs_to_read:
                succeeded.append(  # noqa: PERF401
                    foundation.ReadAttributeRecord(
                        attrid,
                        results[0],
                        foundation.TypeValue(),
                    )
                )
        else:
            succeeded.extend(results[0])
        return [succeeded]

    async def _configure_reporting(  # type:ignore[override]
        self,
        config_records: list[foundation.AttributeReportingConfig],
        *args,
        manufacturer: int | t.uint16_t | None = None,
        **kwargs,
    ):
        """Configure reporting ZCL foundation command."""
        if manufacturer is None and self._has_manuf_attr(
            [a.attrid for a in config_records]
        ):
            manufacturer = self._manufacturer_id
        return await super()._configure_reporting(
            config_records,
            *args,
            manufacturer=manufacturer,
            **kwargs,
        )

    async def _read_attributes(  # type:ignore[override]
        self,
        attribute_ids: list[t.uint16_t],
        *args,
        manufacturer: int | t.uint16_t | None = None,
        **kwargs,
    ):
        """Read attributes ZCL foundation command."""
        if manufacturer is None and self._has_manuf_attr(attribute_ids):
            manufacturer = self._manufacturer_id
        return await super()._read_attributes(
            attribute_ids, *args, manufacturer=manufacturer, **kwargs
        )

    async def _write_attributes(  # type:ignore[override]
        self,
        attributes: list[foundation.Attribute],
        *args,
        manufacturer: int | t.uint16_t | None = None,
        **kwargs,
    ):
        """Write attribute ZCL foundation command."""
        if manufacturer is None and self._has_manuf_attr(
            [a.attrid for a in attributes]
        ):
            manufacturer = self._manufacturer_id
        return await super()._write_attributes(
            attributes, *args, manufacturer=manufacturer, **kwargs
        )

    async def _write_attributes_undivided(  # type:ignore[override]
        self,
        attributes: list[foundation.Attribute],
        *args,
        manufacturer: int | t.uint16_t | None = None,
        **kwargs,
    ):
        """Write attribute undivided ZCL foundation command."""
        if manufacturer is None and self._has_manuf_attr(
            [a.attrid for a in attributes]
        ):
            manufacturer = self._manufacturer_id
        return await super()._write_attributes_undivided(
            attributes, *args, manufacturer=manufacturer, **kwargs
        )

    def get(self, key: int | str, default: typing.Any | None = None) -> typing.Any:
        """Get cached attribute."""

        try:
            attr_def = self.find_attribute(key)
        except KeyError:
            return super().get(key, default)

        # Ensure we check the constant attributes dictionary first, since their values
        # will not be in the attribute cache but can be read immediately.
        if (
            self._CONSTANT_ATTRIBUTES is not None
            and attr_def.id in self._CONSTANT_ATTRIBUTES
        ):
            return self._CONSTANT_ATTRIBUTES[attr_def.id]

        return super().get(key, default)

    async def apply_custom_configuration(self, *args, **kwargs):
        """Hook for applications to instruct instances to apply custom configuration."""


FilterType = typing.Callable[
    [zigpy.device.Device],
    bool,
]


def signature_matches(
    signature: dict[str, typing.Any],
) -> FilterType:
    """Return True if device matches signature."""

    def _match(a: dict | typing.Iterable, b: dict | typing.Iterable) -> bool:
        return set(a) == set(b)

    def _filter(device: zigpy.device.Device) -> bool:
        """Return True if device matches signature."""
        if device.model != signature.get(SIG_MODEL, device.model):
            _LOGGER.debug("Fail, because device model mismatch: '%s'", device.model)
            return False

        if device.manufacturer != signature.get(SIG_MANUFACTURER, device.manufacturer):
            _LOGGER.debug(
                "Fail, because device manufacturer mismatch: '%s'",
                device.manufacturer,
            )
            return False

        dev_ep = set(device.endpoints) - {0}

        sig = signature.get(SIG_ENDPOINTS)
        if sig is None:
            return False

        if not _match(sig, dev_ep):
            _LOGGER.debug(
                "Fail because endpoint list mismatch: %s %s",
                set(sig.keys()),
                dev_ep,
            )
            return False

        if not all(
            device[eid].profile_id
            == sig[eid].get(SIG_EP_PROFILE, device[eid].profile_id)
            for eid in sig
        ):
            _LOGGER.debug("Fail because profile_id mismatch on at least one endpoint")
            return False

        if not all(
            device[eid].device_type
            == sig[eid].get(SIG_EP_TYPE, device[eid].device_type)
            for eid in sig
        ):
            _LOGGER.debug("Fail because device_type mismatch on at least one endpoint")
            return False

        if not all(
            _match(device[eid].in_clusters, ep.get(SIG_EP_INPUT, []))
            for eid, ep in sig.items()
        ):
            _LOGGER.debug(
                "Fail because input cluster mismatch on at least one endpoint"
            )
            return False

        if not all(
            _match(device[eid].out_clusters, ep.get(SIG_EP_OUTPUT, []))
            for eid, ep in sig.items()
        ):
            _LOGGER.debug(
                "Fail because output cluster mismatch on at least one endpoint"
            )
            return False

        _LOGGER.debug(
            "Device matches filter signature - device ieee[%s]: filter signature[%s]",
            device.ieee,
            signature,
        )
        return True

    return _filter


def handle_message_from_uninitialized_sender(
    sender: zigpy.device.Device,
    profile: int,
    cluster: int,
    src_ep: int,
    dst_ep: int,
    message: bytes,
) -> None:
    """Processes message from an uninitialized sender."""
    for handler in _uninitialized_device_message_handlers:
        if handler(sender, profile, cluster, src_ep, dst_ep, message):
            break
