import enum

import zigpy.types as t


class PowerDescriptor(t.Struct):
    _fields = [
        ('byte_1', 1),  # Current power mode 4, Available power sources 4
        ('byte_2', 1),  # Current power source 4, Current power source level 4
    ]


class SimpleDescriptor(t.Struct):
    _fields = [
        ('endpoint', t.uint8_t),
        ('profile', t.uint16_t),
        ('device_type', t.uint16_t),
        ('device_version', t.uint8_t),
        ('input_clusters', t.LVList(t.uint16_t)),
        ('output_clusters', t.LVList(t.uint16_t)),
    ]


class SizePrefixedSimpleDescriptor(SimpleDescriptor):
    def serialize(self):
        data = super().serialize()
        return len(data).to_bytes(1, 'little') + data

    @classmethod
    def deserialize(cls, data):
        if not data or data[0] == 0:
            return None, data[1:]
        return SimpleDescriptor.deserialize(data[1:])


class NodeDescriptor(t.Struct):
    _fields = [
        ('byte1', t.uint8_t),
        ('byte2', t.uint8_t),
        ('mac_capability_flags', t.uint8_t),
        ('manufacturer_code', t.uint16_t),
        ('maximum_buffer_size', t.uint8_t),
        ('maximum_incoming_transfer_size', t.uint16_t),
        ('server_mask', t.uint16_t),
        ('maximum_outgoing_transfer_size', t.uint16_t),
        ('descriptor_capability_field', t.uint8_t),
    ]


class MultiAddress:
    """Used for binds, represents an IEEE+endpoint or NWK address"""
    def __init__(self, other=None):
        if isinstance(other, self.__class__):
            self.addrmode = other.addrmode
            self.nwk = getattr(other, 'nwk', None)
            self.ieee = getattr(other, 'ieee', None)
            self.endpoint = getattr(other, 'endpoint', None)

    @classmethod
    def deserialize(cls, data):
        r = cls()
        r.addrmode, data = data[0], data[1:]
        if r.addrmode == 0x01:
            r.nwk, data = t.uint16_t.deserialize(data)
        elif r.addrmode == 0x03:
            r.ieee, data = t.EUI64.deserialize(data)
            r.endpoint, data = t.uint8_t.deserialize(data)
        else:
            raise ValueError("Invalid MultiAddress - unknown address mode")

        return r, data

    def serialize(self):
        if self.addrmode == 0x01:
            return (
                self.addrmode.to_bytes(1, 'little') +
                self.nwk.to_bytes(2, 'little')
            )
        elif self.addrmode == 0x03:
            return (
                self.addrmode.to_bytes(1, 'little') +
                self.ieee.serialize() +
                self.endpoint.to_bytes(1, 'little')
            )
        else:
            raise ValueError("Invalid value for addrmode")


NWK = ('NWKAddr', t.uint16_t)
NWKI = ('NWKAddrOfInterest', t.uint16_t)
IEEE = ('IEEEAddr', t.EUI64)
STATUS = ('Status', t.uint8_t)


CLUSTERS = {
    # Device and Service Discovery Server Requests
    0x0000: ('NWK_addr_req', (IEEE, ('RequestType', t.uint8_t), ('StartIndex', t.uint8_t))),
    0x0001: ('IEEE_addr_req', (NWKI, ('RequestType', t.uint8_t), ('StartIndex', t.uint8_t))),
    0x0002: ('Node_Desc_req', (NWKI, )),
    0x0003: ('Power_Desc_req', (NWKI, )),
    0x0004: ('Simple_Desc_req', (NWKI, ('EndPoint', t.uint8_t))),
    0x0005: ('Active_EP_req', (NWKI, )),
    0x0006: ('Match_Desc_req', (NWKI, ('ProfileID', t.uint16_t), ('InClusterList', t.LVList(t.uint16_t)), ('OutClusterList', t.LVList(t.uint16_t)))),
    # 0x0010: ('Complex_Desc_req', (NWKI, )),
    0x0011: ('User_Desc_req', (NWKI, )),
    0x0012: ('Discovery_Cache_req', (NWK, IEEE)),
    0x0013: ('Device_annce', (NWK, IEEE, ('Capability', t.uint8_t))),
    0x0014: ('User_Desc_set', (NWKI, ('UserDescriptor', t.fixed_list(16, t.uint8_t)))),  # Really a string
    0x0015: ('System_Server_Discovery_req', (('ServerMask', t.uint16_t), )),
    0x0016: ('Discovery_store_req', (NWK, IEEE, ('NodeDescSize', t.uint8_t), ('PowerDescSize', t.uint8_t), ('ActiveEPSize', t.uint8_t), ('SimpleDescSizeList', t.LVList(t.uint8_t)))),
    0x0017: ('Node_Desc_store_req', (NWK, IEEE, ('NodeDescriptor', NodeDescriptor))),
    0x0019: ('Active_EP_store_req', (NWK, IEEE, ('ActiveEPList', t.LVList(t.uint8_t)))),
    0x001a: ('Simple_Desc_store_req', (NWK, IEEE, ('SimpleDescriptor', SizePrefixedSimpleDescriptor))),
    0x001b: ('Remove_node_cache_req', (NWK, IEEE)),
    0x001c: ('Find_node_cache_req', (NWK, IEEE)),
    0x001d: ('Extended_Simple_Desc_req', (NWKI, ('EndPoint', t.uint8_t), ('StartIndex', t.uint8_t))),
    0x001e: ('Extended_Active_EP_req', (NWKI, ('StartIndex', t.uint8_t))),
    #  Bind Management Server Services Responses
    0x0020: ('End_Device_Bind_req', (('BindingTarget', t.uint16_t), ('SrcAddress', t.EUI64), ('SrcEndpoint', t.uint8_t), ('ProfileID', t.uint8_t), ('InClusterList', t.LVList(t.uint8_t)), ('OutClusterList', t.LVList(t.uint8_t)))),
    0x0021: ('Bind_req', (('SrcAddress', t.EUI64), ('SrcEndpoint', t.uint8_t), ('ClusterID', t.uint16_t), ('DstAddress', MultiAddress))),
    0x0022: ('Unind_req', (('SrcAddress', t.EUI64), ('SrcEndpoint', t.uint8_t), ('ClusterID', t.uint16_t), ('DstAddress', MultiAddress))),
    # Network Management Server Services Requests
    # ... TODO optional stuff ...
    0x0034: ('Mgmt_Leave_req', (('DeviceAddress', t.EUI64), ('Options', t.uint8_t))),  # bitmap8
    0x0036: ('Mgmt_Permit_Joining_req', (('PermitDuration', t.uint8_t), ('TC_Significant', t.Bool))),
    # ... TODO optional stuff ...

    # Responses
    # Device and Service Discovery Server Responses
    0x8000: ('NWK_addr_rsp', (STATUS, IEEE, NWK, ('NumAssocDev', t.uint8_t), ('StartIndex', t.uint8_t), ('NWKAddressAssocDevList', t.List(t.uint16_t)))),
    0x8001: ('IEEE_addr_rsp', (STATUS, IEEE, NWK, ('NumAssocDev', t.uint8_t), ('StartIndex', t.uint8_t), ('NWKAddrAssocDevList', t.List(t.uint16_t)))),
    0x8002: ('Node_Desc_rsp', (STATUS, NWKI, ('NodeDescriptor', NodeDescriptor))),
    0x8003: ('Power_Desc_rsp', (STATUS, NWKI, ('PowerDescriptor', PowerDescriptor))),
    0x8004: ('Simple_Desc_rsp', (STATUS, NWKI, ('SimpleDescriptor', SizePrefixedSimpleDescriptor))),
    0x8005: ('Active_EP_rsp', (STATUS, NWKI, ('ActiveEPList', t.LVList(t.uint8_t)))),
    0x8006: ('Match_Desc_rsp', (STATUS, NWKI, ('MatchList', t.LVList(t.uint8_t)))),
    # 0x8010: ('Complex_Desc_rsp', (STATUS, NWKI, ('Length', t.uint8_t), ('ComplexDescriptor', ComplexDescriptor))),
    0x8011: ('User_Desc_rsp', (STATUS, NWKI, ('Length', t.uint8_t), ('UserDescriptor', t.fixed_list(16, t.uint8_t)))),
    0x8012: ('Discovery_Cache_rsp', (STATUS, )),
    0x8014: ('User_Desc_conf', (STATUS, NWKI)),
    0x8015: ('System_Server_Discovery_rsp', (STATUS, ('ServerMask', t.uint16_t))),
    0x8016: ('Discovery_Store_rsp', (STATUS, )),
    0x8017: ('Node_Desc_store_rsp', (STATUS, )),
    0x8018: ('Power_Desc_store_rsp', (STATUS, IEEE, ('PowerDescriptor', PowerDescriptor))),
    0x8019: ('Active_EP_store_rsp', (STATUS, )),
    0x801a: ('Simple_Desc_store_rsp', (STATUS, )),
    0x801b: ('Remove_node_cache_rsp', (STATUS, )),
    0x801c: ('Find_node_cache_rsp', (('CacheNWKAddr', t.EUI64), NWK, IEEE)),
    0x801d: ('Extended_Simple_Desc_rsp', (STATUS, NWK, ('Endpoint', t.uint8_t), ('AppInputClusterCount', t.uint8_t), ('AppOutputClusterCount', t.uint8_t), ('StartIndex', t.uint8_t), ('AppClusterList', t.List(t.uint16_t)))),
    0x801e: ('Extended_Active_EP_rsp', (STATUS, NWKI, ('ActiveEPCount', t.uint8_t), ('StartIndex', t.uint8_t), ('ActiveEPList', t.List(t.uint8_t)))),
    #  Bind Management Server Services Responses
    0x8020: ('End_Device_Bind_rsp', (STATUS, )),
    0x8021: ('Bind_rsp', (STATUS, )),
    0x8022: ('Unbind_rsp', (STATUS, )),
    # ... TODO optional stuff ...
    # Network Management Server Services Responses
    # ... TODO optional stuff ...
    0x8034: ('Mgmt_Leave_rsp', (STATUS, )),
    0x8036: ('Mgmt_Permit_Joining_rsp', (STATUS, )),
    # ... TODO optional stuff ...
}


# Rewrite to (name, param_names, param_types)
for command_id, c in CLUSTERS.items():
    param_names = [p[0] for p in c[1]]
    param_types = [p[1] for p in c[1]]
    CLUSTERS[command_id] = (c[0], param_names, param_types)


class Status(enum.Enum):
    # The requested operation or transmission was completed successfully.
    SUCCESS = 0x00
    # The supplied request type was invalid.
    INV_REQUESTTYPE = 0x80
    # The requested device did not exist on a device following a child
    # descriptor request to a parent.
    DEVICE_NOT_FOUND = 0x81
    # The supplied endpoint was equal to = 0x00 or between 0xf1 and 0xff.
    INVALID_EP = 0x82
    # The requested endpoint is not described by a simple descriptor.
    NOT_ACTIVE = 0x83
    # The requested optional feature is not supported on the target device.
    NOT_SUPPORTED = 0x84
    # A timeout has occurred with the requested operation.
    TIMEOUT = 0x85
    # The end device bind request was unsuccessful due to a failure to match
    # any suitable clusters.
    NO_MATCH = 0x86
    # The unbind request was unsuccessful due to the coordinator or source
    # device not having an entry in its binding table to unbind.
    NO_ENTRY = 0x88
    # A child descriptor was not available following a discovery request to a
    # parent.
    NO_DESCRIPTOR = 0x89
    # The device does not have storage space to support the requested
    # operation.
    INSUFFICIENT_SPACE = 0x8a
    # The device is not in the proper state to support the requested operation.
    NOT_PERMITTED = 0x8b
    # The device does not have table space to support the operation.
    TABLE_FULL = 0x8c
    # The permissions configuration table on the target indicates that the
    # request is not authorized from this device.
    NOT_AUTHORIZED = 0x8d
