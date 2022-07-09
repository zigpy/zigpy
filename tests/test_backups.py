import pytest

import zigpy.backup
import zigpy.state as app_state
import zigpy.types as t
import zigpy.zdo.types as zdo_t


@pytest.fixture
def node_info():
    return app_state.NodeInfo(
        nwk=t.NWK(0x0000),
        ieee=t.EUI64.convert("93:2C:A9:34:D9:D0:5D:12"),
        logical_type=zdo_t.LogicalType.Coordinator,
    )


@pytest.fixture
def network_info(node_info):
    return app_state.NetworkInfo(
        extended_pan_id=t.ExtendedPanId.convert("0D:49:91:99:AE:CD:3C:35"),
        pan_id=t.PanId(0x9BB0),
        nwk_update_id=0x12,
        nwk_manager_id=t.NWK(0x0000),
        channel=t.uint8_t(15),
        channel_mask=t.Channels.from_channel_list([15, 20, 25]),
        security_level=t.uint8_t(5),
        network_key=app_state.Key(
            key=t.KeyData.convert("9A:79:D6:9A:DA:EC:45:C6:F2:EF:EB:AF:DA:A3:07:B6"),
            seq=108,
            tx_counter=39009277,
        ),
        tc_link_key=app_state.Key(
            key=t.KeyData(b"ZigBeeAlliance09"),
            partner_ieee=node_info.ieee,
            tx_counter=8712428,
        ),
        key_table=[
            app_state.Key(
                key=t.KeyData.convert(
                    "85:7C:05:00:3E:76:1A:F9:68:9A:49:41:6A:60:5C:76"
                ),
                tx_counter=3792973670,
                rx_counter=1083290572,
                seq=147,
                partner_ieee=t.EUI64.convert("69:0C:07:52:AA:D7:7D:71"),
            ),
            app_state.Key(
                key=t.KeyData.convert(
                    "CA:02:E8:BB:75:7C:94:F8:93:39:D3:9C:B3:CD:A7:BE"
                ),
                tx_counter=2597245184,
                rx_counter=824424412,
                seq=19,
                partner_ieee=t.EUI64.convert("A3:1A:F6:8E:19:95:23:BE"),
            ),
        ],
        children=[
            # Has a key
            t.EUI64.convert("A3:1A:F6:8E:19:95:23:BE"),
            # Does not have a key
            t.EUI64.convert("C6:DF:28:F9:60:33:DB:03"),
        ],
        # If exposed by the stack, NWK addresses of other connected devices on the network
        nwk_addresses={
            # Two children above
            t.EUI64.convert("A3:1A:F6:8E:19:95:23:BE"): t.NWK(0x2C59),
            t.EUI64.convert("C6:DF:28:F9:60:33:DB:03"): t.NWK(0x1CA0),
            # Random devices on the network
            t.EUI64.convert("7A:BF:38:A9:59:21:A0:7A"): t.NWK(0x16B5),
            t.EUI64.convert("10:55:FE:67:24:EA:96:D3"): t.NWK(0xBFB9),
            t.EUI64.convert("9A:0E:10:50:00:1B:1A:5F"): t.NWK(0x1AF6),
        },
        stack_specific={"zstack": {"tclk_seed": "71e31105bb92a2d15747a0d0a042dbfd"}},
        metadata={"zstack": {"version": "20220102"}},
    )


@pytest.fixture
def backup(network_info, node_info):
    return zigpy.backup.NetworkBackup(network_info=network_info, node_info=node_info)


def test_state_backup_restore_unchanged(backup):
    obj = backup.as_dict()
    backup2 = zigpy.backup.NetworkBackup.from_dict(obj)

    assert backup == backup2
