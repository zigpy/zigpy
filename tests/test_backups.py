from datetime import datetime, timedelta, timezone
import json

import pytest

from tests.async_mock import AsyncMock
from tests.conftest import app  # noqa: F401
import zigpy.backups
import zigpy.state as app_state
import zigpy.types as t
import zigpy.zdo.types as zdo_t


@pytest.fixture
def backup_factory():
    def inner():
        return zigpy.backups.NetworkBackup(
            backup_time=datetime(2021, 2, 8, 19, 35, 24, 761000, tzinfo=timezone.utc),
            node_info=app_state.NodeInfo(
                nwk=t.NWK(0x0000),
                ieee=t.EUI64.convert("93:2C:A9:34:D9:D0:5D:12"),
                logical_type=zdo_t.LogicalType.Coordinator,
                model="Coordinator Model",
                manufacturer="Coordinator Manufacturer",
                version="1.2.3.4",
            ),
            network_info=app_state.NetworkInfo(
                extended_pan_id=t.ExtendedPanId.convert("0D:49:91:99:AE:CD:3C:35"),
                pan_id=t.PanId(0x9BB0),
                nwk_update_id=0x12,
                nwk_manager_id=t.NWK(0x0000),
                channel=t.uint8_t(15),
                channel_mask=t.Channels.from_channel_list([15, 20, 25]),
                security_level=t.uint8_t(5),
                network_key=app_state.Key(
                    key=t.KeyData.convert(
                        "9A:79:D6:9A:DA:EC:45:C6:F2:EF:EB:AF:DA:A3:07:B6"
                    ),
                    seq=108,
                    tx_counter=39009277,
                ),
                tc_link_key=app_state.Key(
                    key=t.KeyData(b"ZigBeeAlliance09"),
                    partner_ieee=t.EUI64.convert("93:2C:A9:34:D9:D0:5D:12"),
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
                    # Random device with no NWK address or key
                    t.EUI64.convert("A4:02:A0:DC:17:D8:17:DF"),
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
                stack_specific={
                    "zstack": {"tclk_seed": "71e31105bb92a2d15747a0d0a042dbfd"}
                },
                metadata={"zstack": {"version": "20220102"}},
            ),
        )

    return inner


@pytest.fixture
def backup(backup_factory):
    return backup_factory()


@pytest.fixture
def z2m_backup_json():
    return {
        "metadata": {
            "format": "zigpy/open-coordinator-backup",
            "version": 1,
            "source": "zigbee-herdsman@0.13.65",
            "internal": {"date": "2021-02-08T19:35:24.761Z", "znpVersion": 2},
        },
        "stack_specific": {"zstack": {"tclk_seed": "71e31105bb92a2d15747a0d0a042dbfd"}},
        "coordinator_ieee": "932ca934d9d05d12",
        "pan_id": "9bb0",
        "extended_pan_id": "0d499199aecd3c35",
        "nwk_update_id": 18,
        "security_level": 5,
        "channel": 15,
        "channel_mask": [15, 20, 25],
        "network_key": {
            "key": "9a79d69adaec45c6f2efebafdaa307b6",
            "sequence_number": 108,
            "frame_counter": 39009277,
        },
        "devices": [
            {
                "nwk_address": "2c59",
                "ieee_address": "a31af68e199523be",
                "link_key": {
                    "key": "ca02e8bb757c94f89339d39cb3cda7be",
                    "tx_counter": 2597245184,
                    "rx_counter": 824424412,
                },
                # "is_child": True, #  Implicitly a child device
            },
            {
                "nwk_address": None,
                "ieee_address": "690c0752aad77d71",
                "link_key": {
                    "key": "857c05003e761af9689a49416a605c76",
                    "tx_counter": 3792973670,
                    "rx_counter": 1083290572,
                },
                "is_child": False,
            },
            {
                "nwk_address": None,
                "ieee_address": "a402a0dc17d817df",
                "is_child": True,
            },
            {
                "nwk_address": "1ca0",
                "ieee_address": "c6df28f96033db03",
                "is_child": True,
            },
            {
                "nwk_address": "16b5",
                "ieee_address": "7abf38a95921a07a",
                "is_child": False,
            },
            {
                "nwk_address": "bfb9",
                "ieee_address": "1055fe6724ea96d3",
                "is_child": False,
            },
            {
                "nwk_address": "1af6",
                "ieee_address": "9a0e1050001b1a5f",
                "is_child": False,
            },
        ],
    }


@pytest.fixture
def zigate_backup_json():
    return {
        "backup_time": "2022-07-20T17:58:16.694438+00:00",
        "network_info": {
            "extended_pan_id": "9d:ff:72:2d:19:2c:d1:01",
            "pan_id": "D08A",
            "nwk_update_id": 0,  # missing
            "nwk_manager_id": "0000",
            "channel": 15,
            "channel_mask": [15],
            "security_level": 5,
            "network_key": {
                # missing
                "key": "ff:ff:ff:ff:ff:ff:ff:ff:ff:ff:ff:ff:ff:ff:ff:ff",
                "tx_counter": 0,
                "rx_counter": 0,
                "seq": 0,
                "partner_ieee": "ff:ff:ff:ff:ff:ff:ff:ff",
            },
            "tc_link_key": {
                # missing
                "key": "5a:69:67:42:65:65:41:6c:6c:69:61:6e:63:65:30:39",
                "tx_counter": 0,
                "rx_counter": 0,
                "seq": 0,
                "partner_ieee": "00:15:8d:00:06:a3:fd:fe",
            },
            "key_table": [],
            "children": [],
            "nwk_addresses": {},
            "stack_specific": {},
            "metadata": {"zigate": {"version": "3.21"}},
            "source": "zigpy-zigate@0.9.0",
        },
        "node_info": {
            "nwk": "0000",
            "ieee": "00:15:8d:00:06:a3:fd:fe",
            "logical_type": "coordinator",
        },
    }


def test_state_backup_as_dict(backup):
    obj = json.loads(json.dumps(backup.as_dict()))
    restored_backup = type(backup).from_dict(obj)
    assert backup == restored_backup


def test_state_backup_as_open_coordinator(backup):
    obj = json.loads(json.dumps(backup.as_open_coordinator_json()))
    backup2 = zigpy.backups.NetworkBackup.from_open_coordinator_json(obj)

    assert backup == backup2


def test_z2m_backup_parsing(z2m_backup_json, backup):
    backup.network_info.metadata = None
    backup.network_info.source = None
    backup.node_info.manufacturer = None
    backup.node_info.model = None
    backup.node_info.version = None
    backup.network_info.tc_link_key.tx_counter = 0

    for key in backup.network_info.key_table:
        key.seq = 0

    backup2 = zigpy.backups.NetworkBackup.from_open_coordinator_json(z2m_backup_json)
    backup2.network_info.metadata = None
    backup2.network_info.source = None

    # Key order may be different
    backup.network_info.key_table.sort(key=lambda k: k.key)
    backup2.network_info.key_table.sort(key=lambda k: k.key)

    assert backup == backup2


def test_from_dict_automatic(z2m_backup_json):
    backup1 = zigpy.backups.NetworkBackup.from_open_coordinator_json(z2m_backup_json)
    backup2 = zigpy.backups.NetworkBackup.from_dict(z2m_backup_json)

    assert backup1 == backup2


def test_from_dict_failure():
    with pytest.raises(ValueError):
        zigpy.backups.NetworkBackup.from_dict({"some": "json"})


def test_backup_compatibility(backup_factory):
    backup1 = backup_factory()
    assert backup1.is_compatible_with(backup1)

    # Incompatible due to different coordinator IEEE
    backup2 = backup_factory()
    backup2.node_info.ieee = t.EUI64.convert("AA:AA:AA:AA:AA:AA:AA:AA")
    assert not backup2.supersedes(backup1)
    assert not backup1.supersedes(backup2)
    assert not backup1.is_compatible_with(backup2)

    # NWK frame counter must always be greater
    backup3 = backup_factory()
    backup3.network_info.network_key.tx_counter -= 1
    assert backup3.is_compatible_with(backup1)
    assert not backup3.supersedes(backup1)

    backup4 = backup_factory()
    backup4.network_info.network_key.tx_counter += 1
    assert backup4.is_compatible_with(backup1)
    assert backup4.supersedes(backup1)


async def test_backup_completeness(backup, zigate_backup_json):
    assert backup.is_complete()

    zigate_backup = zigpy.backups.NetworkBackup.from_dict(zigate_backup_json)
    assert not zigate_backup.is_complete()

    backups = zigpy.backups.BackupManager(None)

    with pytest.raises(ValueError):
        await backups.restore_backup(zigate_backup)


async def test_add_backup(backup_factory):
    backups = zigpy.backups.BackupManager(None)

    # First backup
    backup1 = backup_factory()
    backups.add_backup(backup1)
    assert backups.backups == [backup1]

    # Adding the same backup twice will do nothing
    backups.add_backup(backup1)
    assert backups.backups == [backup1]

    # Adding an identical backup that is newer replaces the old one
    backup2 = backup_factory()
    backup2.backup_time += timedelta(hours=1)
    backups.add_backup(backup2)
    assert backups.backups == [backup2]

    # An even more recent one with a rolled back frame counter is appended
    backup3 = backup_factory()
    backup3.backup_time += timedelta(hours=2)
    backup3.network_info.network_key.tx_counter -= 1000
    backups.add_backup(backup3)
    assert backups.backups == [backup2, backup3]

    # A final one replacing them both is added
    backup4 = backup_factory()
    backup4.backup_time += timedelta(hours=3)
    backup4.network_info.network_key.tx_counter += 1000
    backups.add_backup(backup4)
    assert backups.backups == [backup4]

    # An incompatible backup will be added to the list. Nothing will be replaced.
    backup5 = backup_factory()
    backup5.network_info.pan_id += 1
    backups.add_backup(backup5)
    assert backups.backups == [backup4, backup5]


async def test_restore_backup_create_new(app, backup):
    backups = zigpy.backups.BackupManager(app)
    backups.create_backup = AsyncMock()

    await backups.restore_backup(backup)
    app.write_network_info.assert_called_once()
    backups.create_backup.assert_called_once()

    app.write_network_info.reset_mock()
    backups.create_backup.reset_mock()

    await backups.restore_backup(backup, create_new=False)
    app.write_network_info.assert_called_once()
    backups.create_backup.assert_not_called()  # Won't be called
