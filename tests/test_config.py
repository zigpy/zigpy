"""Test configuration."""

import pathlib
import warnings

import pytest
import voluptuous as vol

import zigpy.config
import zigpy.config.validators


@pytest.mark.parametrize(
    ("value", "result"),
    [
        (False, False),
        (True, True),
        ("1", True),
        ("yes", True),
        ("YeS", True),
        ("on", True),
        ("oN", True),
        ("enable", True),
        ("enablE", True),
        (0, False),
        ("no", False),
        ("nO", False),
        ("off", False),
        ("ofF", False),
        ("disable", False),
        ("disablE", False),
    ],
)
def test_config_validation_bool(value, result):
    """Test boolean config validation."""
    assert zigpy.config.validators.cv_boolean(value) is result

    schema = vol.Schema({vol.Required("value"): zigpy.config.validators.cv_boolean})
    validated = schema({"value": value})
    assert validated["value"] is result


@pytest.mark.parametrize("value", ["invalid", "not a bool", "something"])
def test_config_validation_bool_invalid(value):
    """Test boolean config validation."""
    with pytest.raises(vol.Invalid):
        zigpy.config.validators.cv_boolean(value)


def test_config_validation_key_not_16_list():
    """Validate key fails."""
    with pytest.raises(vol.Invalid):
        zigpy.config.validators.cv_key([0x00])

    with pytest.raises(vol.Invalid):
        zigpy.config.validators.cv_key([0x00 for i in range(15)])

    with pytest.raises(vol.Invalid):
        zigpy.config.validators.cv_key([0x00 for i in range(17)])

    with pytest.raises(vol.Invalid):
        zigpy.config.validators.cv_key(None)

    zigpy.config.validators.cv_key([0x00 for i in range(16)])


def test_config_validation_key_not_a_byte():
    """Validate key fails."""

    with pytest.raises(vol.Invalid):
        zigpy.config.validators.cv_key([-1 for i in range(16)])

    with pytest.raises(vol.Invalid):
        zigpy.config.validators.cv_key([256 for i in range(16)])

    with pytest.raises(vol.Invalid):
        zigpy.config.validators.cv_key([0] * 15 + [256])

    with pytest.raises(vol.Invalid):
        zigpy.config.validators.cv_key([0] * 15 + [-1])

    with pytest.raises(vol.Invalid):
        zigpy.config.validators.cv_key([0] * 15 + ["x1"])

    zigpy.config.validators.cv_key([0xFF for i in range(16)])


def test_config_validation_key_success():
    """Validate key success."""

    key = zigpy.config.validators.cv_key(zigpy.config.CONF_NWK_TC_LINK_KEY_DEFAULT)
    assert key.serialize() == b"ZigBeeAlliance09"


@pytest.mark.parametrize(
    ("value", "result"),
    [
        (0x1234, 0x1234),
        ("0x1234", 0x1234),
        (1234, 1234),
        ("1234", 1234),
        ("001234", 1234),
        ("0e1234", vol.Invalid),
        ("1234abcd", vol.Invalid),
        ("0xabGG", vol.Invalid),
        (None, vol.Invalid),
    ],
)
def test_config_validation_hex_number(value, result):
    """Test hex number config validation."""

    if isinstance(result, int):
        assert zigpy.config.validators.cv_hex(value) == result
    else:
        with pytest.raises(vol.Invalid):
            zigpy.config.validators.cv_hex(value)


@pytest.mark.parametrize(
    ("value", "result"),
    [
        (1, vol.Invalid),
        (11, 11),
        (0x11, 17),
        ("26", 26),
        (27, vol.Invalid),
        ("27", vol.Invalid),
    ],
)
def test_schema_network_channel(value, result):
    """Test network schema for channel."""

    config = {zigpy.config.CONF_NWK_CHANNEL: value}

    if isinstance(result, int):
        config = zigpy.config.SCHEMA_NETWORK(config)
        assert config[zigpy.config.CONF_NWK_CHANNEL] == result
    else:
        with pytest.raises(vol.Invalid):
            zigpy.config.SCHEMA_NETWORK(config)


def test_schema_network_pan_id():
    """Test Extended Pan-id."""
    config = zigpy.config.SCHEMA_NETWORK({})
    assert (
        config[zigpy.config.CONF_NWK_EXTENDED_PAN_ID]
        == zigpy.config.CONF_NWK_EXTENDED_PAN_ID_DEFAULT
    )

    config = zigpy.config.SCHEMA_NETWORK(
        {zigpy.config.CONF_NWK_EXTENDED_PAN_ID: "00:11:22:33:44:55:66:77"}
    )
    assert (
        config[zigpy.config.CONF_NWK_EXTENDED_PAN_ID].serialize()
        == b"\x77\x66\x55\x44\x33\x22\x11\x00"
    )


def test_schema_network_short_pan_id():
    """Test Pan-id."""
    config = zigpy.config.SCHEMA_NETWORK({})
    assert config[zigpy.config.CONF_NWK_PAN_ID] is None

    config = zigpy.config.SCHEMA_NETWORK({zigpy.config.CONF_NWK_PAN_ID: 0x1234})
    assert config[zigpy.config.CONF_NWK_PAN_ID].serialize() == b"\x34\x12"


def test_deprecated():
    """Test key deprecation."""

    schema = vol.Schema(
        {
            vol.Optional("value"): vol.All(
                zigpy.config.validators.cv_hex,
                zigpy.config.validators.cv_deprecated("Test message"),
            )
        }
    )

    with pytest.warns(DeprecationWarning, match="Test message"):
        assert schema({"value": 123}) == {"value": 123}

    # No warnings are raised
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert schema({}) == {}


def test_cv_json_file(tmp_path: pathlib.Path) -> None:
    """Test `cv_json_file` validator."""

    path = tmp_path / "file.json"

    # Does not exist
    with pytest.raises(vol.Invalid):
        zigpy.config.validators.cv_json_file(str(path))

    # Not a file
    path.mkdir()

    with pytest.raises(vol.Invalid):
        zigpy.config.validators.cv_json_file(str(path))

    path.rmdir()

    # File exists
    path.write_text("{}")
    assert zigpy.config.validators.cv_json_file(str(path)) == path


def test_cv_folder(tmp_path: pathlib.Path) -> None:
    """Test `cv_folder` validator."""

    folder_path = tmp_path / "folder"
    file_path = tmp_path / "not_folder"

    # Does not exist
    with pytest.raises(vol.Invalid):
        zigpy.config.validators.cv_folder(str(folder_path))

    # Not a folder
    file_path.write_text("")
    with pytest.raises(vol.Invalid):
        zigpy.config.validators.cv_folder(str(file_path))

    # Folder exists
    folder_path.mkdir()
    assert zigpy.config.validators.cv_folder(str(folder_path)) == folder_path
