"""Test configuration."""

import pytest
import voluptuous as vol
import zigpy.config
import zigpy.config.validators


@pytest.mark.parametrize(
    "value, result",
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

    zigpy.config.validators.cv_key([0x00 for i in range(16)])


def test_config_validation_key_not_a_byte():
    """Validate key fails."""

    with pytest.raises(vol.Invalid):
        zigpy.config.validators.cv_key([-1 for i in range(16)])

    with pytest.raises(vol.Invalid):
        zigpy.config.validators.cv_key([256 for i in range(16)])

    zigpy.config.validators.cv_key([0xFF for i in range(16)])


def test_config_validation_key_success():
    """Validate key success."""

    key = zigpy.config.validators.cv_key(zigpy.config.CONF_NWK_TC_LINK_KEY_DEFAULT)
    assert key.serialize() == b"ZigBeeAlliance09"
