"""GPD command payloads and their mapping to GPD CommandIDs.

Reference: ZGP specification, sections A.4.1 (Tables 54-56) and A.4.2.
"""

from __future__ import annotations

from typing import Self

import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zgp.types import (
    DeviceID,
    GPDCommandID,
    SecurityKeyType,
    SecurityLevel,
    SwitchType,
)


class GPNoPayload(t.Struct):
    """Payload of a GPD command that carries no payload at all."""


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
    switch_info_present: t.uint1_t
    # Announces a subsequent GPD Application Description command (0xE4)
    app_description_follows: t.uint1_t
    _reserved: t.uint2_t


# Figure 113 — the cluster-list length byte packs both counts into one nibble each
class GPClusterListCount(t.IntStruct, t.uint8_t):
    num_server: t.uint4_t
    num_client: t.uint4_t


# Figure 115
class GPGenericSwitchConfiguration(t.IntStruct, t.uint8_t):
    num_contacts: t.uint4_t
    switch_type: SwitchType
    _reserved: t.uint2_t


# Figure 114
class GPSwitchInformation(t.Struct):
    """Switch information field of the GP Commissioning command payload."""

    # Length of the two fields below, i.e. 0x02 in the current specification
    length: t.uint8_t
    configuration: GPGenericSwitchConfiguration
    contact_status: t.bitmap8

    def __new__(cls, *args, **kwargs) -> Self:
        instance = super().__new__(cls, *args, **kwargs)

        if instance.length is None and instance.configuration is not None:
            instance.length = t.uint8_t(2)

        return instance


class GPCommissioningPayload(t.Struct):
    """GP Commissioning command (0xE0) payload."""

    device_id: DeviceID
    options: GPCommissioningOptions

    extended_options: GPCommissioningExtendedOptions = t.StructField(
        requires=lambda s: s.options.extended_options_present
    )
    security_key: t.KeyData = t.StructField(
        requires=lambda s: (
            s.extended_options is not None and s.extended_options.key_present
        ),
    )
    # None means the field is absent; 0 is a valid MIC and must not be confused with it.
    key_mic: t.uint32_t = t.StructField(
        requires=lambda s: (
            s.extended_options is not None
            and s.extended_options.key_present
            and s.extended_options.key_encrypted
        ),
    )
    # None means absent; 0 is a valid initial counter value.
    outgoing_counter: t.uint32_t = t.StructField(
        requires=lambda s: (
            s.extended_options is not None
            and s.extended_options.outgoing_counter_present
        ),
    )

    app_info: GPCommissioningAppInfo = t.StructField(
        requires=lambda s: s.options.app_info_present
    )
    manufacturer_id: t.uint16_t = t.StructField(
        requires=lambda s: s.app_info is not None
        and s.app_info.manufacturer_id_present,
    )
    model_id: t.uint16_t = t.StructField(
        requires=lambda s: s.app_info is not None and s.app_info.model_id_present,
    )
    gpd_commands: t.LVList[t.uint8_t, t.uint8_t] = t.StructField(
        requires=lambda s: s.app_info is not None and s.app_info.gpd_commands_present,
    )
    cluster_counts: GPClusterListCount = t.StructField(
        requires=lambda s: s.app_info is not None and s.app_info.cluster_list_present,
    )
    server_clusters: t.List[t.uint16_t] = t.StructField(
        requires=lambda s: s.app_info is not None and s.app_info.cluster_list_present,
        length=lambda s: s.cluster_counts.num_server,
    )
    client_clusters: t.List[t.uint16_t] = t.StructField(
        requires=lambda s: s.app_info is not None and s.app_info.cluster_list_present,
        length=lambda s: s.cluster_counts.num_client,
    )
    switch_information: GPSwitchInformation = t.StructField(
        requires=lambda s: s.app_info is not None and s.app_info.switch_info_present,
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


# Figure 117
class GPCommissioningReplyOptions(t.IntStruct, t.uint8_t):
    """Options byte from the GP Commissioning Reply command (0xF0) payload."""

    pan_id_present: t.uint1_t
    security_key_present: t.uint1_t
    key_encrypted: t.uint1_t
    security_level: SecurityLevel
    key_type: SecurityKeyType


# Figure 116
class GPCommissioningReplyPayload(t.Struct):
    """GP Commissioning Reply command (0xF0) payload."""

    options: GPCommissioningReplyOptions
    pan_id: t.PanId = t.StructField(requires=lambda s: s.options.pan_id_present)
    security_key: t.KeyData = t.StructField(
        requires=lambda s: s.options.security_key_present
    )
    key_mic: t.uint32_t = t.StructField(
        requires=lambda s: (s.options.security_key_present and s.options.key_encrypted),
    )
    frame_counter: t.uint32_t = t.StructField(
        requires=lambda s: (
            s.options.security_level
            in (SecurityLevel.FullFrameCounterAndMIC, SecurityLevel.Encrypted)
            and s.options.security_key_present
            and s.options.key_encrypted
        ),
    )


# Figure 119 — one byte carrying two channel nibbles (IEEE 802.15.4 channel == nibble + 11)
class GPChannelRequestPayload(t.IntStruct, t.uint8_t):
    """GP Channel Request command (0xE3) payload."""

    next_channel: t.uint4_t
    second_next_channel: t.uint4_t


# Figure 121 — IEEE 802.15.4 channel == operational_channel + 11
class GPChannelConfigurationPayload(t.IntStruct, t.uint8_t):
    """GP Channel Configuration command (0xF3) payload."""

    operational_channel: t.uint4_t
    basic: t.uint1_t
    _reserved: t.uint3_t


# Figure 129
class GPContactStatusPayload(t.Struct):
    """GPD 8-bit vector press (0x69) and release (0x6A) command payload.

    Only the contacts announced during commissioning are meaningful: a set bit is a
    closed contact.
    """

    contact_status: t.bitmap8


# Figure 139 — shared by Move Up/Down, Move Hue Up/Down and Move Saturation Up/Down
class GPMovePayload(t.Struct):
    """Payload of the GPD Move commands, modelled after the ZCL Move commands."""

    # Absent or 0xFF both mean "unspecified, use an implementation-specific rate"
    rate: t.uint8_t = t.StructField(optional=True)


# Figure 140 — shared by Step Up/Down, Step Hue Up/Down and Step Saturation Up/Down
class GPStepPayload(t.Struct):
    """Payload of the GPD Step commands, modelled after the ZCL Step commands."""

    step_size: t.uint8_t
    # Absent or 0xFFFF both mean "unspecified"
    transition_time: t.uint16_t = t.StructField(optional=True)


# Figure 141
class GPMoveColorPayload(t.Struct):
    """GPD Move Color command (0x4A) payload."""

    rate_x: t.int16s
    rate_y: t.int16s


# Figure 142
class GPStepColorPayload(t.Struct):
    """GPD Step Color command (0x4B) payload."""

    step_x: t.int16s
    step_y: t.int16s
    transition_time: t.uint16_t = t.StructField(optional=True)


# Figure 130. Attribute reports (Figure 131) are identical to ZCL attribute records.
class GPAttributeReportingPayload(t.Struct):
    """GPD Attribute Reporting command (0xA0) payload."""

    cluster_id: t.uint16_t
    attributes: t.List[foundation.Attribute]


# Figure 132
class GPManufacturerSpecificAttributeReportingPayload(t.Struct):
    """GPD Manufacturer-Specific Attribute Reporting command (0xA1) payload."""

    manufacturer_code: t.uint16_t
    cluster_id: t.uint16_t
    attributes: t.List[foundation.Attribute]


# Figure 134
class GPClusterReport(t.Struct):
    cluster_id: t.uint16_t
    attribute: foundation.Attribute


# Figure 133
class GPMultiClusterReportingPayload(t.Struct):
    """GPD Multi-Cluster Reporting command (0xA2) payload."""

    reports: t.List[GPClusterReport]


# Figure 135
class GPManufacturerSpecificMultiClusterReportingPayload(t.Struct):
    """GPD Manufacturer-Specific Multi-Cluster Reporting command (0xA3) payload."""

    manufacturer_code: t.uint16_t
    reports: t.List[GPClusterReport]


# Figure 144 — shared by the Request Attributes, Read Attributes Response, Write
# Attributes and Read Attributes commands
class GPAttributeRequestOptions(t.IntStruct, t.uint8_t):
    multi_record: t.uint1_t
    manufacturer_id_present: t.uint1_t
    _reserved: t.uint6_t


# Figure 145 — the attribute list is delimited by its size in octets, so a length that
# does not cover whole attribute IDs is rejected instead of shifting the records after it
class GPClusterRecordRequest(t.Struct):
    cluster_id: t.uint16_t
    attribute_ids: t.SizePrefixedList[t.uint16_t, t.uint8_t]


# Figure 143
class GPRequestAttributesPayload(t.Struct):
    """GPD Request Attributes (0xA4) and Read Attributes (0xF2) command payload."""

    options: GPAttributeRequestOptions
    manufacturer_id: t.uint16_t = t.StructField(
        requires=lambda s: s.options.manufacturer_id_present
    )
    cluster_records: t.List[GPClusterRecordRequest]


# Figure 137
class GPZCLTunnelingOptions(t.IntStruct, t.uint8_t):
    frame_type: foundation.FrameType
    manufacturer_id_present: t.uint1_t
    direction: foundation.Direction
    _reserved: t.uint4_t


# Figure 136
class GPZCLTunnelingPayload(t.Struct):
    """GPD ZCL Tunneling command (0xA6 from the GPD, 0xF6 to the GPD) payload."""

    options: GPZCLTunnelingOptions
    manufacturer_id: t.uint16_t = t.StructField(
        requires=lambda s: s.options.manufacturer_id_present
    )
    cluster_id: t.uint16_t
    command_id: t.uint8_t
    payload: t.LVBytes


# Figure 152
class GPManufacturerDefinedPayload(t.Struct):
    """Payload of the manufacturer-defined GPD commands (0xB0 - 0xBF).

    Everything past the ManufacturerID is specified per ManufacturerID and CommandID
    combination, so it is left as raw bytes.
    """

    manufacturer_id: t.uint16_t
    data: t.Bytes


# Tables 54, 55 and 56. `GPNoPayload` marks a command that the specification defines
# as payloadless.
GPD_COMMAND_SCHEMAS: dict[GPDCommandID, type[t.Struct]] = {
    # Identify (Table 54)
    GPDCommandID.Identify: GPNoPayload,
    # Scenes (Table 54): the sink fills in the GroupID itself, see sec. A.4.2.7
    GPDCommandID.RecallScene0: GPNoPayload,
    GPDCommandID.RecallScene1: GPNoPayload,
    GPDCommandID.RecallScene2: GPNoPayload,
    GPDCommandID.RecallScene3: GPNoPayload,
    GPDCommandID.RecallScene4: GPNoPayload,
    GPDCommandID.RecallScene5: GPNoPayload,
    GPDCommandID.RecallScene6: GPNoPayload,
    GPDCommandID.RecallScene7: GPNoPayload,
    GPDCommandID.StoreScene0: GPNoPayload,
    GPDCommandID.StoreScene1: GPNoPayload,
    GPDCommandID.StoreScene2: GPNoPayload,
    GPDCommandID.StoreScene3: GPNoPayload,
    GPDCommandID.StoreScene4: GPNoPayload,
    GPDCommandID.StoreScene5: GPNoPayload,
    GPDCommandID.StoreScene6: GPNoPayload,
    GPDCommandID.StoreScene7: GPNoPayload,
    # On/Off (Table 54)
    GPDCommandID.Off: GPNoPayload,
    GPDCommandID.On: GPNoPayload,
    GPDCommandID.Toggle: GPNoPayload,
    GPDCommandID.Release: GPNoPayload,
    # Level Control (sec. A.4.2.4)
    GPDCommandID.MoveUp: GPMovePayload,
    GPDCommandID.MoveDown: GPMovePayload,
    GPDCommandID.StepUp: GPStepPayload,
    GPDCommandID.StepDown: GPStepPayload,
    GPDCommandID.LevelControlStop: GPNoPayload,
    GPDCommandID.MoveUpWithOnOff: GPMovePayload,
    GPDCommandID.MoveDownWithOnOff: GPMovePayload,
    GPDCommandID.StepUpWithOnOff: GPStepPayload,
    GPDCommandID.StepDownWithOnOff: GPStepPayload,
    # Color Control (sec. A.4.2.5)
    GPDCommandID.MoveHueStop: GPNoPayload,
    GPDCommandID.MoveHueUp: GPMovePayload,
    GPDCommandID.MoveHueDown: GPMovePayload,
    GPDCommandID.StepHueUp: GPStepPayload,
    GPDCommandID.StepHueDown: GPStepPayload,
    GPDCommandID.MoveSaturationStop: GPNoPayload,
    GPDCommandID.MoveSaturationUp: GPMovePayload,
    GPDCommandID.MoveSaturationDown: GPMovePayload,
    GPDCommandID.StepSaturationUp: GPStepPayload,
    GPDCommandID.StepSaturationDown: GPStepPayload,
    GPDCommandID.MoveColor: GPMoveColorPayload,
    GPDCommandID.StepColor: GPStepColorPayload,
    # Door Lock (Table 54)
    GPDCommandID.LockDoor: GPNoPayload,
    GPDCommandID.UnlockDoor: GPNoPayload,
    # Generic switch (Table 54)
    GPDCommandID.Press1of1: GPNoPayload,
    GPDCommandID.Release1of1: GPNoPayload,
    GPDCommandID.Press1of2: GPNoPayload,
    GPDCommandID.Release1of2: GPNoPayload,
    GPDCommandID.Press2of2: GPNoPayload,
    GPDCommandID.Release2of2: GPNoPayload,
    GPDCommandID.ShortPress1of1: GPNoPayload,
    GPDCommandID.ShortPress1of2: GPNoPayload,
    GPDCommandID.ShortPress2of2: GPNoPayload,
    # Advanced generic switch (sec. A.4.2.2.1)
    GPDCommandID.Press8BitVector: GPContactStatusPayload,
    GPDCommandID.Release8BitVector: GPContactStatusPayload,
    # Sensor commands (sec. A.4.2.3)
    GPDCommandID.AttributeReporting: GPAttributeReportingPayload,
    GPDCommandID.ManufacturerSpecificReporting: (
        GPManufacturerSpecificAttributeReportingPayload
    ),
    GPDCommandID.MultiClusterReporting: GPMultiClusterReportingPayload,
    GPDCommandID.ManufacturerSpecificMultiClusterReporting: (
        GPManufacturerSpecificMultiClusterReportingPayload
    ),
    # Bidirectional operation (sec. A.4.2.6)
    GPDCommandID.RequestAttributes: GPRequestAttributesPayload,
    # TODO: Figure 147, a `t.SizePrefixedList[foundation.ReadAttributeRecord, t.uint8_t]`
    # per cluster record. No known device implements it.
    # GPDCommandID.ReadAttributesResponse: None,
    GPDCommandID.ZCLTunneling: GPZCLTunnelingPayload,
    # TODO: unparsable on its own, the layout of its data points is announced by the
    # Application Description command (0xE4) during commissioning
    # GPDCommandID.CompactAttributeReporting: None,
    # Manufacturer-defined commands (sec. A.4.2.8)
    **{
        GPDCommandID(command_id): GPManufacturerDefinedPayload
        for command_id in range(0xB0, 0xC0)
    },
    # Commissioning commands (sec. A.4.2.1)
    GPDCommandID.CommissioningRequest: GPCommissioningPayload,
    GPDCommandID.DecommissioningRequest: GPNoPayload,
    GPDCommandID.SuccessReport: GPNoPayload,
    GPDCommandID.ChannelRequest: GPChannelRequestPayload,
    # TODO: Figures 122 - 128, nested `t.SizePrefixedList`s for the data point
    # descriptors of each report descriptor. No known device implements it.
    # GPDCommandID.ApplicationDescription: None,
    GPDCommandID.CommissioningReply: GPCommissioningReplyPayload,
    # TODO: Figure 150, a `t.SizePrefixedList[foundation.Attribute, t.uint8_t]` per
    # cluster record. No known device implements it.
    # GPDCommandID.WriteAttributes: None,
    GPDCommandID.ReadAttributes: GPRequestAttributesPayload,
    GPDCommandID.ChannelConfiguration: GPChannelConfigurationPayload,
    GPDCommandID.ZCLTunnelingToGPD: GPZCLTunnelingPayload,
}
