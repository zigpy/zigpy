"""Green Power Data Frame (GPDF) parsing and construction.

Reference: ZGP specification, section A.1.4 (GPDF format).
"""

from __future__ import annotations

from typing import Self

import zigpy.types as t
from zigpy.zgp.types import SecurityKeyType, SecurityLevel


# Figure 109
class GPCommissioningOptions(t.IntStruct, t.uint8_t):
    """Options byte from the GP Commissioning command (0xE0) payload."""

    mac_seq_num_capability: t.uint1_t
    rx_on_capability: t.uint1_t
    app_info_present: t.uint1_t
    _reserved: t.uint1_t
    pan_id_request: t.uint1_t
    security_key_request: t.uint1_t
    fixed_location: t.uint1_t
    extended_options_present: t.uint1_t


# Figure 110
class GPCommissioningExtendedOptions(t.IntStruct, t.uint8_t):
    """Extended options byte from the GP Commissioning command payload."""

    security_level: SecurityLevel
    key_type: SecurityKeyType
    key_present: t.uint1_t
    key_encrypted: t.uint1_t
    outgoing_counter_present: t.uint1_t


# Figure 111
class GPCommissioningAppInfo(t.IntStruct, t.uint8_t):
    """Application Information byte from the GP Commissioning command payload."""

    manufacturer_id_present: t.uint1_t
    model_id_present: t.uint1_t
    gpd_commands_present: t.uint1_t
    cluster_list_present: t.uint1_t
    # The Switch information field (Figure 114) that switch_info_present gates
    # is not modeled yet: when set, its bytes are left in the deserialization
    # remainder. app_description_follows announces a subsequent GPD
    # Application Description command (0xE4).
    switch_info_present: t.uint1_t
    app_description_follows: t.uint1_t
    _reserved: t.uint2_t


# Figure 113 — the cluster-list length byte packs both counts into one nibble each
class GPClusterListCount(t.IntStruct, t.uint8_t):
    num_server: t.uint4_t
    num_client: t.uint4_t


class GPCommissioningPayload(t.Struct):
    """GP Commissioning command (0xE0) payload."""

    device_id: t.uint8_t
    options: GPCommissioningOptions

    extended_options: GPCommissioningExtendedOptions = t.StructField(
        requires=lambda s: s.options.extended_options_present, optional=True
    )
    security_key: t.KeyData = t.StructField(
        requires=lambda s: (
            s.extended_options is not None and s.extended_options.key_present
        ),
        optional=True,
    )
    # None means the field is absent; 0 is a valid MIC and must not be confused with it.
    key_mic: t.uint32_t = t.StructField(
        requires=lambda s: (
            s.extended_options is not None
            and s.extended_options.key_present
            and s.extended_options.key_encrypted
        ),
        optional=True,
    )
    # None means absent; 0 is a valid initial counter value.
    outgoing_counter: t.uint32_t = t.StructField(
        requires=lambda s: (
            s.extended_options is not None
            and s.extended_options.outgoing_counter_present
        ),
        optional=True,
    )

    app_info: GPCommissioningAppInfo = t.StructField(
        requires=lambda s: s.options.app_info_present, optional=True
    )
    manufacturer_id: t.uint16_t = t.StructField(
        requires=lambda s: s.app_info is not None
        and s.app_info.manufacturer_id_present,
        optional=True,
    )
    model_id: t.uint16_t = t.StructField(
        requires=lambda s: s.app_info is not None and s.app_info.model_id_present,
        optional=True,
    )
    gpd_commands: t.LVList[t.uint8_t, t.uint8_t] = t.StructField(
        requires=lambda s: s.app_info is not None and s.app_info.gpd_commands_present,
        optional=True,
    )
    cluster_counts: GPClusterListCount = t.StructField(
        requires=lambda s: s.app_info is not None and s.app_info.cluster_list_present,
        optional=True,
    )
    server_clusters: t.List[t.uint16_t] = t.StructField(
        requires=lambda s: s.app_info is not None and s.app_info.cluster_list_present,
        length=lambda s: s.cluster_counts.num_server,
    )
    client_clusters: t.List[t.uint16_t] = t.StructField(
        requires=lambda s: s.app_info is not None and s.app_info.cluster_list_present,
        length=lambda s: s.cluster_counts.num_client,
    )

    def __new__(cls, *args, **kwargs) -> Self:
        instance = super().__new__(cls, *args, **kwargs)

        # Derive the packed cluster-list count byte from the actual list lengths so
        # callers don't have to keep it in sync by hand.
        if instance.cluster_counts is None and (
            instance.server_clusters is not None or instance.client_clusters is not None
        ):
            instance.cluster_counts = GPClusterListCount(
                num_server=len(instance.server_clusters or []),
                num_client=len(instance.client_clusters or []),
            )

        return instance


# Figure 119 — one byte carrying two channel nibbles (IEEE 802.15.4 channel == nibble + 11)
class GPChannelRequestPayload(t.IntStruct, t.uint8_t):
    """GP Channel Request command (0xE3) payload."""

    next_channel: t.uint4_t
    second_next_channel: t.uint4_t
