"""End-to-end tests for the options flow.

The `config-flow-test-coverage` quality-scale rule asks for full coverage of
config_flow.py; the options flow is the half that was previously untested, and it
is also where the slowdown defaults are reconstructed from three different
generations of stored settings.
"""

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.netro_watering.const import (
    CONF_CTRL_REFRESH_INTERVAL,
    CONF_DELAY_BEFORE_REFRESH,
    CONF_DEVICE_HW_VERSION,
    CONF_DEVICE_NAME,
    CONF_DEVICE_SW_VERSION,
    CONF_DEVICE_TYPE,
    CONF_SENS_REFRESH_INTERVAL,
    CONF_SENSOR_VALUE_DAYS_BEFORE_TODAY,
    CONF_SERIAL_NUMBER,
    CONF_SLOWDOWN_END_TIME,
    CONF_SLOWDOWN_FACTORS,
    CONF_SLOWDOWN_MULTIPLIER,
    CONF_SLOWDOWN_START_TIME,
    CONTROLLER_DEVICE_TYPE,
    DOMAIN,
    GLOBAL_PARAMETERS,
    SENSOR_DEVICE_TYPE,
)


def _entry(device_type: str, *, options: dict | None = None) -> MockConfigEntry:
    """Build a config entry of the given device type, already set up."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DEVICE_TYPE: device_type,
            CONF_SERIAL_NUMBER: "ABC123",
            CONF_DEVICE_NAME: f"Test {device_type}",
            CONF_DEVICE_HW_VERSION: "1.0.0",
            CONF_DEVICE_SW_VERSION: "1.0.0",
        },
        options=options or {},
        unique_id=f"unique_{device_type}",
    )


async def _start_options_flow(hass: HomeAssistant, entry: MockConfigEntry):
    """Add the entry to hass without setting it up, then open its options flow."""
    entry.add_to_hass(hass)
    # The options flow only reads entry.data/options, but HA refuses to start a
    # flow on an entry it considers unusable, so mark it loaded.
    entry.mock_state(hass, ConfigEntryState.LOADED)
    return await hass.config_entries.options.async_init(entry.entry_id)


@pytest.fixture(autouse=True)
def _no_reload():
    """OptionsFlowWithReload reloads the entry on save; the entry here is a stub."""
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_schedule_reload"
    ) as reload:
        yield reload


class TestControllerOptionsFlow:
    """The controller variant of the options form."""

    async def test_form_is_shown(self, hass: HomeAssistant) -> None:
        """Opening the options of a controller shows the init form."""
        result = await _start_options_flow(hass, _entry(CONTROLLER_DEVICE_TYPE))

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"

    async def test_saving_flattens_the_advanced_section(
        self, hass: HomeAssistant
    ) -> None:
        """Values nested under `advanced` are stored flat in the entry options."""
        entry = _entry(CONTROLLER_DEVICE_TYPE)
        result = await _start_options_flow(hass, entry)

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_CTRL_REFRESH_INTERVAL: 20,
                "advanced": {
                    CONF_DELAY_BEFORE_REFRESH: 7,
                    CONF_SLOWDOWN_START_TIME: "23:00",
                    CONF_SLOWDOWN_END_TIME: "05:00",
                    CONF_SLOWDOWN_MULTIPLIER: 3,
                },
            },
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_CTRL_REFRESH_INTERVAL] == 20
        # "advanced" must not survive as a nested key
        assert "advanced" not in result["data"]
        assert result["data"][CONF_DELAY_BEFORE_REFRESH] == 7
        assert result["data"][CONF_SLOWDOWN_START_TIME] == "23:00"
        assert result["data"][CONF_SLOWDOWN_END_TIME] == "05:00"
        assert result["data"][CONF_SLOWDOWN_MULTIPLIER] == 3

    async def test_saving_preserves_untouched_options(
        self, hass: HomeAssistant
    ) -> None:
        """Options absent from the submitted form are carried over, not dropped."""
        entry = _entry(
            CONTROLLER_DEVICE_TYPE, options={"some_legacy_option": "keep me"}
        )
        result = await _start_options_flow(hass, entry)

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={CONF_CTRL_REFRESH_INTERVAL: 10, "advanced": {}},
        )

        assert result["data"]["some_legacy_option"] == "keep me"

    async def test_slowdown_defaults_from_legacy_yaml_list(
        self, hass: HomeAssistant
    ) -> None:
        """The legacy YAML `slowdown_factors` list seeds the three flat defaults."""
        hass.data.setdefault(DOMAIN, {})[GLOBAL_PARAMETERS] = {
            CONF_SLOWDOWN_FACTORS: [{"from": "21:30", "to": "07:15", "sdf": 6}]
        }

        result = await _start_options_flow(hass, _entry(CONTROLLER_DEVICE_TYPE))

        defaults = _section_defaults(result, "advanced")
        assert defaults[CONF_SLOWDOWN_START_TIME] == "21:30"
        assert defaults[CONF_SLOWDOWN_END_TIME] == "07:15"
        assert defaults[CONF_SLOWDOWN_MULTIPLIER] == 6

    async def test_flat_options_override_legacy_list(self, hass: HomeAssistant) -> None:
        """Modern flat values win over a legacy list left in the options."""
        entry = _entry(
            CONTROLLER_DEVICE_TYPE,
            options={
                CONF_SLOWDOWN_FACTORS: [{"from": "21:30", "to": "07:15", "sdf": 6}],
                CONF_SLOWDOWN_START_TIME: "00:30",
                CONF_SLOWDOWN_END_TIME: "04:45",
                CONF_SLOWDOWN_MULTIPLIER: 2,
            },
        )

        result = await _start_options_flow(hass, entry)

        defaults = _section_defaults(result, "advanced")
        assert defaults[CONF_SLOWDOWN_START_TIME] == "00:30"
        assert defaults[CONF_SLOWDOWN_END_TIME] == "04:45"
        assert defaults[CONF_SLOWDOWN_MULTIPLIER] == 2

    async def test_slowdown_defaults_without_any_stored_value(
        self, hass: HomeAssistant
    ) -> None:
        """With nothing stored anywhere, the built-in night-time window is offered."""
        result = await _start_options_flow(hass, _entry(CONTROLLER_DEVICE_TYPE))

        defaults = _section_defaults(result, "advanced")
        assert defaults[CONF_SLOWDOWN_START_TIME] == "22:00"
        assert defaults[CONF_SLOWDOWN_END_TIME] == "06:00"
        assert defaults[CONF_SLOWDOWN_MULTIPLIER] == 1


class TestSensorOptionsFlow:
    """The sensor variant exposes a smaller form."""

    async def test_form_is_shown(self, hass: HomeAssistant) -> None:
        """Opening the options of a sensor shows the init form."""
        result = await _start_options_flow(hass, _entry(SENSOR_DEVICE_TYPE))

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"

    async def test_saving_sensor_options(self, hass: HomeAssistant) -> None:
        """The sensor form stores its refresh interval and history depth."""
        result = await _start_options_flow(hass, _entry(SENSOR_DEVICE_TYPE))

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_SENS_REFRESH_INTERVAL: 45,
                "advanced": {CONF_SENSOR_VALUE_DAYS_BEFORE_TODAY: 4},
            },
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_SENS_REFRESH_INTERVAL] == 45
        assert result["data"][CONF_SENSOR_VALUE_DAYS_BEFORE_TODAY] == 4

    async def test_stored_options_become_defaults(self, hass: HomeAssistant) -> None:
        """Previously saved options are pre-filled in the form."""
        entry = _entry(SENSOR_DEVICE_TYPE, options={CONF_SENS_REFRESH_INTERVAL: 55})

        result = await _start_options_flow(hass, entry)

        assert _schema_defaults(result)[CONF_SENS_REFRESH_INTERVAL] == 55


class TestUnknownDeviceType:
    """An entry of an unrecognised type cannot be configured."""

    async def test_flow_aborts(self, hass: HomeAssistant) -> None:
        """The flow aborts rather than showing an empty form."""
        result = await _start_options_flow(hass, _entry("something_else"))

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "unknown_device_type"


def _schema_defaults(result) -> dict:
    """Return {key: default} for the top level of a shown form's schema."""
    return {
        marker.schema: marker.default()
        for marker in result["data_schema"].schema
        if callable(getattr(marker, "default", None))
    }


def _section_defaults(result, section_key: str) -> dict:
    """Return {key: default} for the fields nested inside a form section."""
    for marker, value in result["data_schema"].schema.items():
        if marker.schema != section_key:
            continue
        return {
            inner.schema: inner.default()
            for inner in value.schema.schema
            if getattr(inner, "default", None) is not None
        }
    raise AssertionError(f"section '{section_key}' not found in schema")
