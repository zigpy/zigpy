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


class LogicalType(t.uint8_t, enum.Enum):
    Coordinator = 0b000
    Router = 0b001
    EndDevice = 0b010
    Reserved3 = 0b011
    Reserved4 = 0b100
    Reserved5 = 0b101
    Reserved6 = 0b110
    Reserved7 = 0b111


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

    def __init__(self, *args, **kwargs):
        if len(args) == 1 and isinstance(args[0], self.__class__):
            # copy constructor
            for field in self._fields:
                setattr(self, field[0], getattr(args[0], field[0]))
            self._valid = True
        elif len(args) == len(self._fields):
            for field, val in zip(self._fields, args):
                setattr(self, field[0], field[1](val))
        else:
            for field in self._fields:
                setattr(self, field[0], None)

    @property
    def is_valid(self):
        """Return True if all fields were initialized."""
        non_empty_fields = [
            getattr(self, field[0]) is not None for field in self._fields
        ]
        return all(non_empty_fields)

    @property
    def logical_type(self):
        """Return logical type of the device"""
        if self.byte1 is None:
            return None
        return LogicalType(self.byte1 & 0x07)

    @property
    def is_coordinator(self):
        """Return True whether this is a coordinator."""
        if self.logical_type is None:
            return None
        return self.logical_type == LogicalType.Coordinator

    @property
    def is_end_device(self):
        """Return True whether this is an end device."""
        if self.logical_type is None:
            return None
        return self.logical_type == LogicalType.EndDevice

    @property
    def is_router(self):
        """Return True whether this is a router."""
        if self.logical_type is None:
            return None
        return self.logical_type == LogicalType.Router

    @property
    def complex_descriptor_available(self):
        if self.byte1 is None:
            return None
        return bool(self.byte1 & 0b00001000)

    @property
    def user_descriptor_available(self):
        if self.byte1 is None:
            return None
        return bool(self.byte1 & 0b00010000)

    @property
    def is_alternate_pan_coordinator(self):
        if self.mac_capability_flags is None:
            return None
        return bool(self.mac_capability_flags & 0b00000001)

    @property
    def is_full_function_device(self):
        if self.mac_capability_flags is None:
            return None
        return bool(self.mac_capability_flags & 0b00000010)

    @property
    def is_mains_powered(self):
        if self.mac_capability_flags is None:
            return None
        return bool(self.mac_capability_flags & 0b00000100)

    @property
    def is_receiver_on_when_idle(self):
        if self.mac_capability_flags is None:
            return None
        return bool(self.mac_capability_flags & 0b00001000)

    @property
    def is_security_capable(self):
        if self.mac_capability_flags is None:
            return None
        return bool(self.mac_capability_flags & 0b01000000)

    @property
    def allocate_address(self):
        if self.mac_capability_flags is None:
            return None
        return bool(self.mac_capability_flags & 0b10000000)


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


class Neighbor(t.Struct):
    """Neighbor Descriptor"""
    _fields = [
        ('PanId', t.EUI64),
        ('IEEEAddr', t.EUI64),
        ('NWKAddr', t.uint16_t),
        ('NeighborType', t.uint8_t),
        ('PermitJoining', t.uint8_t),
        ('Depth', t.uint8_t),
        ('LQI', t.uint8_t)
    ]


class Neighbors(t.Struct):
    """Mgmt_Lqi_rsp"""
    _fields = [
        ('Entries', t.uint8_t),
        ('StartIndex', t.uint8_t),
        ('NeighborTableList', t.LVList(Neighbor))
    ]


class Route(t.Struct):
    """Route Descriptor"""
    _fields = [
        ('DstNWK', t.uint16_t),
        ('RouteStatus', t.uint8_t),
        ('NextHop', t.uint16_t)
    ]


class Routes(t.Struct):
    _fields = [
        ('Entries', t.uint8_t),
        ('StartIndex', t.uint8_t),
        ('RoutingTableList', t.LVList(Route))
    ]


class Status(t.uint8_t, enum.Enum):
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


NWK = ('NWKAddr', t.NWK)
NWKI = ('NWKAddrOfInterest', t.NWK)
IEEE = ('IEEEAddr', t.EUI64)
STATUS = ('Status', Status)


class _CommandID(t.HexRepr, t.uint16_t):
    _hex_len = 4


class ZDOCmd(_CommandID, enum.Enum):
    # Device and Service Discovery Server Requests
    NWK_addr_req = 0x0000
    IEEE_addr_req = 0x0001
    Node_Desc_req = 0x0002
    Power_Desc_req = 0x0003
    Simple_Desc_req = 0x0004
    Active_EP_req = 0x0005
    Match_Desc_req = 0x0006
    Complex_Desc_req = 0x0010
    User_Desc_req = 0x0011
    Discovery_Cache_req = 0x0012
    Device_annce = 0x0013
    User_Desc_set = 0x0014
    System_Server_Discovery_req = 0x0015
    Discovery_store_req = 0x0016
    Node_Desc_store_req = 0x0017
    Active_EP_store_req = 0x0019
    Simple_Desc_store_req = 0x001a
    Remove_node_cache_req = 0x001b
    Find_node_cache_req = 0x001c
    Extended_Simple_Desc_req = 0x001d
    Extended_Active_EP_req = 0x001e
    #  Bind Management Server Services Responses
    End_Device_Bind_req = 0x0020
    Bind_req = 0x0021
    Unbind_req = 0x0022
    # Network Management Server Services Requests
    # ... TODO optional stuff ...
    Mgmt_Lqi_req = 0x0031
    Mgmt_Rtg_req = 0x0032
    # ... TODO optional stuff ...
    Mgmt_Leave_req = 0x0034
    Mgmt_Permit_Joining_req = 0x0036
    # ... TODO optional stuff ...

    # Responses
    # Device and Service Discovery Server Responses
    NWK_addr_rsp = 0x8000
    IEEE_addr_rsp = 0x8001
    Node_Desc_rsp = 0x8002
    Power_Desc_rsp = 0x8003
    Simple_Desc_rsp = 0x8004
    Active_EP_rsp = 0x8005
    Match_Desc_rsp = 0x8006
    Complex_Desc_rsp = 0x8010
    User_Desc_rsp = 0x8011
    Discovery_Cache_rsp = 0x8012
    User_Desc_conf = 0x8014
    System_Server_Discovery_rsp = 0x8015
    Discovery_Store_rsp = 0x8016
    Node_Desc_store_rsp = 0x8017
    Power_Desc_store_rsp = 0x8018
    Active_EP_store_rsp = 0x8019
    Simple_Desc_store_rsp = 0x801a
    Remove_node_cache_rsp = 0x801b
    Find_node_cache_rsp = 0x801c
    Extended_Simple_Desc_rsp = 0x801d
    Extended_Active_EP_rsp = 0x801e
    #  Bind Management Server Services Responses
    End_Device_Bind_rsp = 0x8020
    Bind_rsp = 0x8021
    Unbind_rsp = 0x8022
    # ... TODO optional stuff ...
    # Network Management Server Services Responses
    Mgmt_Lqi_rsp = 0x8031
    Mgmt_Rtg_rsp = 0x8032
    # ... TODO optional stuff ...
    Mgmt_Leave_rsp = 0x8034
    Mgmt_Permit_Joining_rsp = 0x8036
    # ... TODO optional stuff ...


CLUSTERS = {
    # Device and Service Discovery Server Requests
    ZDOCmd.NWK_addr_req: (IEEE, ('RequestType', t.uint8_t), ('StartIndex', t.uint8_t)),
    ZDOCmd.IEEE_addr_req: (NWKI, ('RequestType', t.uint8_t), ('StartIndex', t.uint8_t)),
    ZDOCmd.Node_Desc_req: (NWKI,),
    ZDOCmd.Power_Desc_req: (NWKI,),
    ZDOCmd.Simple_Desc_req: (NWKI, ('EndPoint', t.uint8_t)),
    ZDOCmd.Active_EP_req: (NWKI,),
    ZDOCmd.Match_Desc_req: (NWKI, ('ProfileID', t.uint16_t), ('InClusterList', t.LVList(t.uint16_t)), ('OutClusterList', t.LVList(t.uint16_t))),
    # ZDO.Complex_Desc_req: (NWKI, ),
    ZDOCmd.User_Desc_req: (NWKI,),
    ZDOCmd.Discovery_Cache_req: (NWK, IEEE),
    ZDOCmd.Device_annce: (NWK, IEEE, ('Capability', t.uint8_t)),
    ZDOCmd.User_Desc_set: (NWKI, ('UserDescriptor', t.fixed_list(16, t.uint8_t))),  # Really a string
    ZDOCmd.System_Server_Discovery_req: (('ServerMask', t.uint16_t),),
    ZDOCmd.Discovery_store_req: (NWK, IEEE, ('NodeDescSize', t.uint8_t), ('PowerDescSize', t.uint8_t), ('ActiveEPSize', t.uint8_t), ('SimpleDescSizeList', t.LVList(t.uint8_t))),
    ZDOCmd.Node_Desc_store_req: (NWK, IEEE, ('NodeDescriptor', NodeDescriptor)),
    ZDOCmd.Active_EP_store_req: (NWK, IEEE, ('ActiveEPList', t.LVList(t.uint8_t))),
    ZDOCmd.Simple_Desc_store_req: (NWK, IEEE, ('SimpleDescriptor', SizePrefixedSimpleDescriptor)),
    ZDOCmd.Remove_node_cache_req: (NWK, IEEE),
    ZDOCmd.Find_node_cache_req: (NWK, IEEE),
    ZDOCmd.Extended_Simple_Desc_req: (NWKI, ('EndPoint', t.uint8_t), ('StartIndex', t.uint8_t)),
    ZDOCmd.Extended_Active_EP_req: (NWKI, ('StartIndex', t.uint8_t)),
    #  Bind Management Server Services Responses
    ZDOCmd.End_Device_Bind_req: (('BindingTarget', t.uint16_t), ('SrcAddress', t.EUI64), ('SrcEndpoint', t.uint8_t), ('ProfileID', t.uint8_t), ('InClusterList', t.LVList(t.uint8_t)), ('OutClusterList', t.LVList(t.uint8_t))),
    ZDOCmd.Bind_req: (('SrcAddress', t.EUI64), ('SrcEndpoint', t.uint8_t), ('ClusterID', t.uint16_t), ('DstAddress', MultiAddress)),
    ZDOCmd.Unbind_req: (('SrcAddress', t.EUI64), ('SrcEndpoint', t.uint8_t), ('ClusterID', t.uint16_t), ('DstAddress', MultiAddress)),
    # Network Management Server Services Requests
    # ... TODO optional stuff ...
    ZDOCmd.Mgmt_Lqi_req: (('StartIndex', t.uint8_t),),
    ZDOCmd.Mgmt_Rtg_req: (('StartIndex', t.uint8_t),),
    # ... TODO optional stuff ...
    ZDOCmd.Mgmt_Leave_req: (('DeviceAddress', t.EUI64), ('Options', t.bitmap8)),
    ZDOCmd.Mgmt_Permit_Joining_req: (('PermitDuration', t.uint8_t), ('TC_Significant', t.Bool)),
    # ... TODO optional stuff ...

    # Responses
    # Device and Service Discovery Server Responses
    ZDOCmd.NWK_addr_rsp: (STATUS, IEEE, NWK, ('NumAssocDev', t.uint8_t), ('StartIndex', t.uint8_t), ('NWKAddressAssocDevList', t.List(t.uint16_t))),
    ZDOCmd.IEEE_addr_rsp: (STATUS, IEEE, NWK, ('NumAssocDev', t.uint8_t), ('StartIndex', t.uint8_t), ('NWKAddrAssocDevList', t.List(t.uint16_t))),
    ZDOCmd.Node_Desc_rsp: (STATUS, NWKI, ('NodeDescriptor', NodeDescriptor)),
    ZDOCmd.Power_Desc_rsp: (STATUS, NWKI, ('PowerDescriptor', PowerDescriptor)),
    ZDOCmd.Simple_Desc_rsp: (STATUS, NWKI, ('SimpleDescriptor', SizePrefixedSimpleDescriptor)),
    ZDOCmd.Active_EP_rsp: (STATUS, NWKI, ('ActiveEPList', t.LVList(t.uint8_t))),
    ZDOCmd.Match_Desc_rsp: (STATUS, NWKI, ('MatchList', t.LVList(t.uint8_t))),
    # ZDO.Complex_Desc_rsp: (STATUS, NWKI, ('Length', t.uint8_t), ('ComplexDescriptor', ComplexDescriptor)),
    ZDOCmd.User_Desc_rsp: (STATUS, NWKI, ('Length', t.uint8_t), ('UserDescriptor', t.fixed_list(16, t.uint8_t))),
    ZDOCmd.Discovery_Cache_rsp: (STATUS,),
    ZDOCmd.User_Desc_conf: (STATUS, NWKI),
    ZDOCmd.System_Server_Discovery_rsp: (STATUS, ('ServerMask', t.uint16_t)),
    ZDOCmd.Discovery_Store_rsp: (STATUS,),
    ZDOCmd.Node_Desc_store_rsp: (STATUS,),
    ZDOCmd.Power_Desc_store_rsp: (STATUS, IEEE, ('PowerDescriptor', PowerDescriptor)),
    ZDOCmd.Active_EP_store_rsp: (STATUS,),
    ZDOCmd.Simple_Desc_store_rsp: (STATUS,),
    ZDOCmd.Remove_node_cache_rsp: (STATUS,),
    ZDOCmd.Find_node_cache_rsp: (('CacheNWKAddr', t.EUI64), NWK, IEEE),
    ZDOCmd.Extended_Simple_Desc_rsp: (STATUS, NWK, ('Endpoint', t.uint8_t), ('AppInputClusterCount', t.uint8_t), ('AppOutputClusterCount', t.uint8_t), ('StartIndex', t.uint8_t), ('AppClusterList', t.List(t.uint16_t))),
    ZDOCmd.Extended_Active_EP_rsp: (STATUS, NWKI, ('ActiveEPCount', t.uint8_t), ('StartIndex', t.uint8_t), ('ActiveEPList', t.List(t.uint8_t))),
    #  Bind Management Server Services Responses
    ZDOCmd.End_Device_Bind_rsp: (STATUS,),
    ZDOCmd.Bind_rsp: (STATUS,),
    ZDOCmd.Unbind_rsp: (STATUS,),
    # ... TODO optional stuff ...
    # Network Management Server Services Responses
    ZDOCmd.Mgmt_Lqi_rsp: (STATUS, ('Neighbors', Neighbors)),
    ZDOCmd.Mgmt_Rtg_rsp: (STATUS, ('Routes', Routes)),
    # ... TODO optional stuff ...
    ZDOCmd.Mgmt_Leave_rsp: (STATUS,),
    ZDOCmd.Mgmt_Permit_Joining_rsp: (STATUS,),
    # ... TODO optional stuff ...
}


# Rewrite to (name, param_names, param_types)
for command_id, schema in CLUSTERS.items():
    param_names = [p[0] for p in schema]
    param_types = [p[1] for p in schema]
    CLUSTERS[command_id] = (param_names, param_types)
