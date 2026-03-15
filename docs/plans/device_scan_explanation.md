# Successful Device Scan: 00:17:88:01:0b:4b:51:fc

## Source

- Source log: `/Users/davidmulcahey/.homeassistant/home-assistant.log`
- Source line range: `107962-114796`
- Extracted transaction log: `/Users/davidmulcahey/zha_refactor/device_scan.log`

The extracted log keeps the scan service events, outbound Zigbee requests, decoded ZDO/ZCL responses, and scanner warnings for this transaction. It intentionally omits repetitive EZSP bookkeeping, raw ASH serial frames, and unrelated Home Assistant noise.

## Summary

- Device IEEE: `00:17:88:01:0b:4b:51:fc`
- Device NWK: `0x40d1`
- Scan window: `2026-03-15 19:04:33.046000` to `2026-03-15 19:04:52.844000`
- Duration: `0:00:19.798000`
- Outcome: `success`
- `used_resume`: `False`
- `force_full`: `True`
- `descriptor_refresh_performed`: `True`
- Standard-scope targets scanned: `11`
- Manufacturer-scope targets scanned: `11`

## Descriptor Refresh

- Node descriptor: `NodeDescriptor(logical_type=<LogicalType.Router: 1>, complex_descriptor_available=0, user_descriptor_available=0, reserved=0, aps_flags=0, frequency_band=<FrequencyBand.Freq2400MHz: 8>, mac_capability_flags=<MACCapabilityFlags.FullFunctionDevice|MainsPowered|RxOnWhenIdle|AllocateAddress: 142>, manufacturer_code=4107, maximum_buffer_size=82, maximum_incoming_transfer_size=128, server_mask=11264, maximum_outgoing_transfer_size=128, descriptor_capability_field=<DescriptorCapability.NONE: 0>, *allocate_address=True, *is_alternate_pan_coordinator=False, *is_coordinator=False, *is_end_device=False, *is_full_function_device=True, *is_mains_powered=True, *is_receiver_on_when_idle=True, *is_router=True, *is_security_capable=False)`
- Active endpoints: `[11, 242]`
- SizePrefixedSimpleDescriptor(endpoint=11, profile=260, device_type=269, device_version=1, input_clusters=[0, 3, 4, 5, 6, 8, 4096, 64515, 768, 64513], output_clusters=[25])
- SizePrefixedSimpleDescriptor(endpoint=242, profile=41440, device_type=97, device_version=0, input_clusters=[], output_clusters=[33])

Endpoint `11` is the application endpoint that was scanned in raw detail. Endpoint `242` is present in the descriptor refresh result as a Green Power proxy endpoint, but it is not part of the raw inventory loop.

## Coverage

- Standard scope targets:
  - Endpoint `11` cluster `0x0000` `Basic` (server)
  - Endpoint `11` cluster `0x0003` `Identify` (server)
  - Endpoint `11` cluster `0x0004` `Groups` (server)
  - Endpoint `11` cluster `0x0005` `Scenes` (server)
  - Endpoint `11` cluster `0x0006` `OnOff` (server)
  - Endpoint `11` cluster `0x0008` `LevelControl` (server)
  - Endpoint `11` cluster `0x0300` `Color` (server)
  - Endpoint `11` cluster `0x1000` `LightLink` (server)
  - Endpoint `11` cluster `0xfc01` `ManufacturerSpecificCluster` (server)
  - Endpoint `11` cluster `0xfc03` `PhilipsHueLightCluster` (server)
  - Endpoint `11` cluster `0x0019` `Ota` (client)
- Manufacturer scope targets:
  - Endpoint `11` cluster `0x0000` `Basic` (server), manufacturer code `4107`
  - Endpoint `11` cluster `0x0003` `Identify` (server), manufacturer code `4107`
  - Endpoint `11` cluster `0x0004` `Groups` (server), manufacturer code `4107`
  - Endpoint `11` cluster `0x0005` `Scenes` (server), manufacturer code `4107`
  - Endpoint `11` cluster `0x0006` `OnOff` (server), manufacturer code `4107`
  - Endpoint `11` cluster `0x0008` `LevelControl` (server), manufacturer code `4107`
  - Endpoint `11` cluster `0x0300` `Color` (server), manufacturer code `4107`
  - Endpoint `11` cluster `0x1000` `LightLink` (server), manufacturer code `4107`
  - Endpoint `11` cluster `0xfc01` `ManufacturerSpecificCluster` (server), manufacturer code `4107`
  - Endpoint `11` cluster `0xfc03` `PhilipsHueLightCluster` (server), manufacturer code `4107`
  - Endpoint `11` cluster `0x0019` `Ota` (client), manufacturer code `4107`

## Detailed Results

Each section below reflects one scanned target. Attribute IDs and command IDs are taken from the decoded discovery responses in the log. Raw read payloads remain in `device_scan.log` for exact value inspection.

### Endpoint 11 / 0x0000 / Basic / server / standard

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Discovered attribute IDs: `0`, `1`, `2`, `3`, `4`, `5`, `6`, `7`, `8`, `9`, `10`, `11`, `16384`, `65533`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0000 (server): UNSUP_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- Transport retries during `attribute_reads`: `2`
- Requests issued for `attribute_reads`: `Read_Attributes(attribute_ids=[0, 1, 2])`, `Read_Attributes(attribute_ids=[3, 4, 5])`, `Read_Attributes(attribute_ids=[6, 7, 8])`, `Read_Attributes(attribute_ids=[6, 7, 8])`, `Read_Attributes(attribute_ids=[9, 10, 11])`, `Read_Attributes(attribute_ids=[16384, 65533])`
- Read results: `0:SUCCESS`, `1:SUCCESS`, `2:SUCCESS`, `3:SUCCESS`, `4:SUCCESS`, `5:SUCCESS`, `6:SUCCESS`, `7:SUCCESS`, `8:SUCCESS`, `9:SUCCESS`, `10:SUCCESS`, `11:SUCCESS`, `16384:SUCCESS`, `65533:SUCCESS`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0000 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0000 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`

### Endpoint 11 / 0x0003 / Identify / server / standard

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Discovered attribute IDs: `0`, `65533`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0003 (server): UNSUP_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- Requests issued for `attribute_reads`: `Read_Attributes(attribute_ids=[0, 65533])`
- Read results: `0:SUCCESS`, `65533:SUCCESS`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0003 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0003 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`

### Endpoint 11 / 0x0004 / Groups / server / standard

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Discovered attribute IDs: `0`, `65533`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0004 (server): UNSUP_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- Requests issued for `attribute_reads`: `Read_Attributes(attribute_ids=[0, 65533])`
- Read results: `0:SUCCESS`, `65533:SUCCESS`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0004 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0004 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`

### Endpoint 11 / 0x0005 / Scenes / server / standard

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Discovered attribute IDs: `0`, `1`, `2`, `3`, `4`, `65533`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0005 (server): UNSUP_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- Requests issued for `attribute_reads`: `Read_Attributes(attribute_ids=[0, 1, 2])`, `Read_Attributes(attribute_ids=[3, 4, 65533])`
- Read results: `0:SUCCESS`, `1:SUCCESS`, `2:SUCCESS`, `3:SUCCESS`, `4:SUCCESS`, `65533:SUCCESS`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0005 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0005 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`

### Endpoint 11 / 0x0006 / OnOff / server / standard

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Discovered attribute IDs: `0`, `16384`, `16385`, `16386`, `16387`, `65533`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0006 (server): UNSUP_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- Requests issued for `attribute_reads`: `Read_Attributes(attribute_ids=[0, 16384, 16385])`, `Read_Attributes(attribute_ids=[16386, 16387, 65533])`
- Read results: `0:SUCCESS`, `16384:SUCCESS`, `16385:SUCCESS`, `16386:SUCCESS`, `16387:SUCCESS`, `65533:SUCCESS`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0006 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0006 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`

### Endpoint 11 / 0x0008 / LevelControl / server / standard

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Discovered attribute IDs: `0`, `1`, `15`, `16384`, `65533`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0008 (server): UNSUP_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- Requests issued for `attribute_reads`: `Read_Attributes(attribute_ids=[0, 1, 15])`, `Read_Attributes(attribute_ids=[16384, 65533])`
- Read results: `0:SUCCESS`, `1:SUCCESS`, `15:SUCCESS`, `16384:SUCCESS`, `65533:SUCCESS`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0008 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0008 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`

### Endpoint 11 / 0x0300 / Color / server / standard

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=26, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=16387, max_attribute_ids=16)`
- Discovered attribute IDs: `0`, `1`, `2`, `3`, `4`, `7`, `8`, `15`, `16`, `17`, `18`, `19`, `21`, `22`, `23`, `25`, `26`, `27`, `48`, `49`, `50`, `51`, `52`, `54`, `55`, `56`, `58`, `59`, `60`, `16384`, `16385`, `16386`, `16387`, `16388`, `16389`, `16390`, `16394`, `16395`, `16396`, `16397`, `16400`, `65533`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0300 (server): UNSUP_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- Requests issued for `attribute_reads`: `Read_Attributes(attribute_ids=[0, 1, 2])`, `Read_Attributes(attribute_ids=[3, 4, 7])`, `Read_Attributes(attribute_ids=[8, 15, 16])`, `Read_Attributes(attribute_ids=[17, 18, 19])`, `Read_Attributes(attribute_ids=[21, 22, 23])`, `Read_Attributes(attribute_ids=[25, 26, 27])`, `Read_Attributes(attribute_ids=[48, 49, 50])`, `Read_Attributes(attribute_ids=[51, 52, 54])`, `Read_Attributes(attribute_ids=[55, 56, 58])`, `Read_Attributes(attribute_ids=[59, 60, 16384])`, `Read_Attributes(attribute_ids=[16385, 16386, 16387])`, `Read_Attributes(attribute_ids=[16388, 16389, 16390])`, `Read_Attributes(attribute_ids=[16394, 16395, 16396])`, `Read_Attributes(attribute_ids=[16397, 16400, 65533])`
- Read results: `0:SUCCESS`, `1:SUCCESS`, `2:SUCCESS`, `3:SUCCESS`, `4:SUCCESS`, `7:SUCCESS`, `8:SUCCESS`, `15:SUCCESS`, `16:SUCCESS`, `17:SUCCESS`, `18:SUCCESS`, `19:SUCCESS`, `21:SUCCESS`, `22:SUCCESS`, `23:SUCCESS`, `25:SUCCESS`, `26:SUCCESS`, `27:SUCCESS`, `48:SUCCESS`, `49:SUCCESS`, `50:SUCCESS`, `51:SUCCESS`, `52:SUCCESS`, `54:SUCCESS`, `55:SUCCESS`, `56:SUCCESS`, `58:SUCCESS`, `59:SUCCESS`, `60:SUCCESS`, `16384:SUCCESS`, `16385:SUCCESS`, `16386:SUCCESS`, `16387:SUCCESS`, `16388:SUCCESS`, `16389:SUCCESS`, `16390:SUCCESS`, `16394:SUCCESS`, `16395:SUCCESS`, `16396:SUCCESS`, `16397:SUCCESS`, `16400:SUCCESS`, `65533:SUCCESS`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0300 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0300 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`

### Endpoint 11 / 0x1000 / LightLink / server / standard

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Discovered attribute IDs: `65533`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x1000 (server): UNSUP_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- Requests issued for `attribute_reads`: `Read_Attributes(attribute_ids=[65533])`
- Read results: `65533:SUCCESS`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x1000 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x1000 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`

### Endpoint 11 / 0xfc01 / ManufacturerSpecificCluster / server / standard

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0xfc01 (server): UNSUP_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0xfc01 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0xfc01 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`

### Endpoint 11 / 0xfc03 / PhilipsHueLightCluster / server / standard

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0xfc03 (server): UNSUP_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0xfc03 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0xfc03 (server): unsupported command discovery response UNSUP_GENERAL_COMMAND`

### Endpoint 11 / 0x0019 / Ota / client / standard

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Discovered attribute IDs: `0`, `1`, `2`, `3`, `4`, `6`, `7`, `8`, `9`, `65533`
- Note: `Cluster 0x0019 on <CustomDeviceV2 model='7602031U7' manuf='Philips' nwk=0x40D1 ieee=00:17:88:01:0b:4b:51:fc is_initialized=True> has incorrect direction (got <Direction.Server_to_Client: 1> for <ClusterType.Client: 1> cluster). Please report this here: https://github.com/zigpy/zigpy/issues/1640`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0019 (client): UNSUP_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- Requests issued for `attribute_reads`: `Read_Attributes(attribute_ids=[0, 1, 2])`, `Read_Attributes(attribute_ids=[3, 4, 6])`, `Read_Attributes(attribute_ids=[7, 8, 9])`, `Read_Attributes(attribute_ids=[65533])`
- Read results: `0:SUCCESS`, `1:SUCCESS`, `2:SUCCESS`, `3:SUCCESS`, `4:SUCCESS`, `6:SUCCESS`, `7:SUCCESS`, `8:SUCCESS`, `9:SUCCESS`, `65533:SUCCESS`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Cluster 0x0019 on <CustomDeviceV2 model='7602031U7' manuf='Philips' nwk=0x40D1 ieee=00:17:88:01:0b:4b:51:fc is_initialized=True> has incorrect direction (got <Direction.Server_to_Client: 1> for <ClusterType.Client: 1> cluster). Please report this here: https://github.com/zigpy/zigpy/issues/1640`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0019 (client): unsupported command discovery response UNSUP_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Cluster 0x0019 on <CustomDeviceV2 model='7602031U7' manuf='Philips' nwk=0x40D1 ieee=00:17:88:01:0b:4b:51:fc is_initialized=True> has incorrect direction (got <Direction.Server_to_Client: 1> for <ClusterType.Client: 1> cluster). Please report this here: https://github.com/zigpy/zigpy/issues/1640`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0019 (client): unsupported command discovery response UNSUP_GENERAL_COMMAND`

### Endpoint 11 / 0x0000 / Basic / server / manufacturer 4107

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=61707, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=61731, max_attribute_ids=16)`
- Discovered attribute IDs: `1`, `32`, `33`, `64`, `65`, `80`, `81`, `82`, `61697`, `61698`, `61700`, `61702`, `61703`, `61704`, `61705`, `61706`, `61707`, `61708`, `61716`, `61717`, `61718`, `61719`, `61720`, `61721`, `61722`, `61724`, `61725`, `61726`, `61727`, `61728`, `61729`, `61730`, `61731`, `61733`, `61734`, `61735`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0000 (server): UNSUP_MANUF_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- Transport retries during `attribute_reads`: `1`
- Requests issued for `attribute_reads`: `Read_Attributes(attribute_ids=[1, 32, 33])`, `Read_Attributes(attribute_ids=[64, 65, 80])`, `Read_Attributes(attribute_ids=[81, 82, 61697])`, `Read_Attributes(attribute_ids=[61698, 61700, 61702])`, `Read_Attributes(attribute_ids=[61703, 61704, 61705])`, `Read_Attributes(attribute_ids=[61706, 61707, 61708])`, `Read_Attributes(attribute_ids=[61716, 61717, 61718])`, `Read_Attributes(attribute_ids=[61719, 61720, 61721])`, `Read_Attributes(attribute_ids=[61721])`, `Read_Attributes(attribute_ids=[61722, 61724, 61725])`, `Read_Attributes(attribute_ids=[61724])`, `Read_Attributes(attribute_ids=[61725])`, `Read_Attributes(attribute_ids=[61726, 61727, 61728])`, `Read_Attributes(attribute_ids=[61729, 61730, 61731])`, `Read_Attributes(attribute_ids=[61733, 61734, 61735])`
- Read results: `1:SUCCESS`, `32:SUCCESS`, `33:SUCCESS`, `64:SUCCESS`, `65:SUCCESS`, `80:SUCCESS`, `81:SUCCESS`, `82:WRITE_ONLY`, `61697:SUCCESS`, `61698:WRITE_ONLY`, `61700:SUCCESS`, `61702:SUCCESS`, `61703:WRITE_ONLY`, `61704:SUCCESS`, `61705:SUCCESS`, `61706:SUCCESS`, `61707:SUCCESS`, `61708:SUCCESS`, `61716:SUCCESS`, `61717:WRITE_ONLY`, `61718:SUCCESS`, `61719:SUCCESS`, `61720:SUCCESS`, `61721:SUCCESS`, `61722:SUCCESS`, `61724:SUCCESS`, `61725:SUCCESS`, `61726:SUCCESS`, `61727:SUCCESS`, `61728:SUCCESS`, `61729:SUCCESS`, `61730:SUCCESS`, `61731:SUCCESS`, `61733:SUCCESS`, `61734:SUCCESS`, `61735:SUCCESS`
- Note: `Read_Attributes response missing status records for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0000 (server) manufacturer 4107: missing 0xf119; response contained 0xf117, 0xf118`
- Note: `Read_Attributes response missing status records for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0000 (server) manufacturer 4107: missing 0xf11c, 0xf11d; response contained 0xf11a`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0000 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0000 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`

### Endpoint 11 / 0x0003 / Identify / server / manufacturer 4107

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0003 (server): UNSUP_MANUF_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0003 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0003 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`

### Endpoint 11 / 0x0004 / Groups / server / manufacturer 4107

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0004 (server): UNSUP_MANUF_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0004 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0004 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`

### Endpoint 11 / 0x0005 / Scenes / server / manufacturer 4107

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Discovered attribute IDs: `1`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0005 (server): UNSUP_MANUF_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- Requests issued for `attribute_reads`: `Read_Attributes(attribute_ids=[1])`
- Read results: `1:SUCCESS`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0005 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0005 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`

### Endpoint 11 / 0x0006 / OnOff / server / manufacturer 4107

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0006 (server): UNSUP_MANUF_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0006 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0006 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`

### Endpoint 11 / 0x0008 / LevelControl / server / manufacturer 4107

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Discovered attribute IDs: `3`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0008 (server): UNSUP_MANUF_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- Requests issued for `attribute_reads`: `Read_Attributes(attribute_ids=[3])`
- Read results: `3:SUCCESS`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0008 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0008 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`

### Endpoint 11 / 0x0300 / Color / server / manufacturer 4107

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Discovered attribute IDs: `3`, `4`, `61440`, `61445`, `61446`, `61447`, `61448`, `61697`, `61953`, `62209`, `62465`, `62721`, `64000`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0300 (server): UNSUP_MANUF_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- Requests issued for `attribute_reads`: `Read_Attributes(attribute_ids=[3, 4, 61440])`, `Read_Attributes(attribute_ids=[61445, 61446, 61447])`, `Read_Attributes(attribute_ids=[61448, 61697, 61953])`, `Read_Attributes(attribute_ids=[62209, 62465, 62721])`, `Read_Attributes(attribute_ids=[64000])`
- Read results: `3:SUCCESS`, `4:SUCCESS`, `61440:SUCCESS`, `61445:WRITE_ONLY`, `61446:SUCCESS`, `61447:SUCCESS`, `61448:SUCCESS`, `61697:SUCCESS`, `61953:SUCCESS`, `62209:SUCCESS`, `62465:SUCCESS`, `62721:SUCCESS`, `64000:SUCCESS`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0300 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0300 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`

### Endpoint 11 / 0x1000 / LightLink / server / manufacturer 4107

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Discovered attribute IDs: `61440`, `61441`, `61442`, `61443`, `61696`, `61697`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x1000 (server): UNSUP_MANUF_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- Requests issued for `attribute_reads`: `Read_Attributes(attribute_ids=[61440, 61441, 61442])`, `Read_Attributes(attribute_ids=[61443, 61696, 61697])`
- Read results: `61440:SUCCESS`, `61441:SUCCESS`, `61442:SUCCESS`, `61443:SUCCESS`, `61696:SUCCESS`, `61697:SUCCESS`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x1000 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x1000 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`

### Endpoint 11 / 0xfc01 / ManufacturerSpecificCluster / server / manufacturer 4107

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Discovered attribute IDs: `0`, `1`, `5`, `53249`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0xfc01 (server): UNSUP_MANUF_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- Requests issued for `attribute_reads`: `Read_Attributes(attribute_ids=[0, 1, 5])`, `Read_Attributes(attribute_ids=[53249])`
- Read results: `0:SUCCESS`, `1:SUCCESS`, `5:SUCCESS`, `53249:SUCCESS`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0xfc01 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Transport retries during `command_discovery_generated`: `1`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0xfc01 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`

### Endpoint 11 / 0xfc03 / PhilipsHueLightCluster / server / manufacturer 4107

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Discovered attribute IDs: `1`, `2`, `16`, `17`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0xfc03 (server): UNSUP_MANUF_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- Requests issued for `attribute_reads`: `Read_Attributes(attribute_ids=[1, 2, 16])`, `Read_Attributes(attribute_ids=[17])`
- Read results: `1:SUCCESS`, `2:SUCCESS`, `16:SUCCESS`, `17:SUCCESS`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0xfc03 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0xfc03 (server): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`

### Endpoint 11 / 0x0019 / Ota / client / manufacturer 4107

- `attribute_discovery`: `success`
- Requests issued for `attribute_discovery`: `Discover_Attribute_Extended(start_attribute_id=0, max_attribute_ids=16)`, `Discover_Attributes(start_attribute_id=0, max_attribute_ids=16)`
- Note: `Cluster 0x0019 on <CustomDeviceV2 model='7602031U7' manuf='Philips' nwk=0x40D1 ieee=00:17:88:01:0b:4b:51:fc is_initialized=True> has incorrect direction (got <Direction.Server_to_Client: 1> for <ClusterType.Client: 1> cluster). Please report this here: https://github.com/zigpy/zigpy/issues/1640`
- Note: `Extended attribute discovery unsupported for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0019 (client): UNSUP_MANUF_GENERAL_COMMAND; falling back to discover_attributes`
- `attribute_reads`: `success`
- `command_discovery_received`: `success`
- Requests issued for `command_discovery_received`: `Discover_Commands_Received(start_command_id=0, max_command_ids=16)`
- Note: `Cluster 0x0019 on <CustomDeviceV2 model='7602031U7' manuf='Philips' nwk=0x40D1 ieee=00:17:88:01:0b:4b:51:fc is_initialized=True> has incorrect direction (got <Direction.Server_to_Client: 1> for <ClusterType.Client: 1> cluster). Please report this here: https://github.com/zigpy/zigpy/issues/1640`
- Note: `Skipping received command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0019 (client): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`
- `command_discovery_generated`: `success`
- Requests issued for `command_discovery_generated`: `Discover_Commands_Generated(start_command_id=0, max_command_ids=16)`
- Note: `Cluster 0x0019 on <CustomDeviceV2 model='7602031U7' manuf='Philips' nwk=0x40D1 ieee=00:17:88:01:0b:4b:51:fc is_initialized=True> has incorrect direction (got <Direction.Server_to_Client: 1> for <ClusterType.Client: 1> cluster). Please report this here: https://github.com/zigpy/zigpy/issues/1640`
- Note: `Skipping generated command discovery for 00:17:88:01:0b:4b:51:fc endpoint 11 cluster 0x0019 (client): unsupported command discovery response UNSUP_MANUF_GENERAL_COMMAND`

## Notable Behaviors

- The scan succeeds even when several clusters reject `Discover_Attribute_Extended`; those targets fall back to `Discover_Attributes` and continue.
- Manufacturer-scoped command discovery on some Philips clusters returns `UNSUP_MANUF_GENERAL_COMMAND`; the scanner logs that and treats it as a supported skip, not a scan failure.
- The OTA client cluster (`0x0019`) replies on the manufacturer-specific path with the wrong direction bit for a client cluster. zigpy logs the incorrect direction, but the transaction still completes successfully.
- Descriptor refresh hits a single delivery retry on the initial Node Descriptor request and then succeeds on the retried send with forced route discovery.

## Reference

- Use `device_scan.log` for exact packet payloads, decoded ZCL bodies, and the precise request order.
- Use this markdown file as the human-readable map of what the successful scan covered and what it discovered.

