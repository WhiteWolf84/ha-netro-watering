# Netro Weather Sync Blueprint

A Home Assistant **script blueprint** that pushes weather data from any HA `weather` entity (plus optional local station sensors) to a Netro controller through the `netro_watering.report_weather` service. Netro uses the reported data instead of its own weather provider, so smart schedules are computed from *your* local weather.

Blueprint file: [netro_weather_sync.yaml](netro_weather_sync.yaml)

## How it works

Each run performs:

1. **`weather.get_forecasts` (daily)** on the selected weather entity. If the entity returns no daily forecast, the script stops silently (nothing is reported).
2. **One `report_weather` call for today**, built from the first forecast item, the current state/attributes of the weather entity and — when configured — your local station sensors (see [Override logic](#override-logic-for-today)).
3. **One `report_weather` call per future day**, up to `number_of_days_forecast` days (capped by how many days the weather entity actually provides).

Fields that cannot be determined (missing forecast attribute, unavailable sensor) are reported as `null` and **omitted from the Netro API request** — no fabricated values. This requires integration version > 2.1.0 (the service schema accepts `null` for all optional fields).

## Inputs (configured once, when creating the script from the blueprint)

| Input | Required | Description |
|---|---|---|
| `netro_controller` | yes | The Netro controller **config entry** to report weather to. |
| `weather_entity` | yes | Source `weather.*` entity. Must support **daily** forecasts. |
| `rain_probability_entity` | no | Sensor with today's rain probability (%). Overrides the forecast value for today. |
| `rain_today_entity` | no | Sensor with today's **accumulated rainfall in mm** (e.g. from a local rain gauge). |
| `temp_min_entity` | no | Sensor with today's **measured minimum** temperature (°C). |
| `temp_max_entity` | no | Sensor with today's **measured maximum** temperature (°C). |

## Fields (passed on every call of the script)

| Field | Default | Description |
|---|---|---|
| `number_of_days_forecast` | 4 | Days to sync **in addition to today** (0–7). Effective count is `min(field, days available from the weather entity − 1)`. |

## Override logic for today

When a local station sensor is configured *and has a valid value*, it competes with the forecast:

- **Rain**: the sensor wins if it measured *more* rain than forecast, or after **20:00** (by then the daily accumulation is considered authoritative). Otherwise the forecast wins. An unavailable sensor falls back to the forecast.
- **t_min**: the sensor wins if *lower* than forecast, or after **10:00** (daily minimum normally occurs in the early morning).
- **t_max**: the sensor wins if *higher* than forecast, or after **20:00**.
- **temp** (average): computed as `(final_min + final_max) / 2` from the same resolved values; omitted if either bound is unknown.
- **rain_prob**: the sensor always wins when available; otherwise forecast `precipitation_probability`; otherwise omitted.
- **humidity / dew point / wind / pressure**: taken from the weather entity attributes; omitted when the attribute is missing.

## Unit handling

The Netro API expects **mm, °C, m/s, hPa**. The blueprint converts automatically based on the weather entity's unit attributes:

- Wind: `m/s` as-is, `mph`, `ft/s`, `kn` converted; anything else treated as `km/h`.
- Pressure: `hPa`/`mbar` as-is, `inHg`, `mmHg`, `kPa`, `psi` converted.
- HA weather conditions are mapped onto Netro's 5 conditions (clear / cloudy / rain / snow / wind); unknown conditions are omitted rather than guessed.

Temperature sensors are assumed to be in **°C** and the rain sensor in **mm** — convert in a template sensor first if yours differ.

## Netro API constraints to keep in mind

From the [Netro Public API documentation](https://www.netrohome.com/en/shop/user_guides/7):

- `report_weather` accepts dates **no earlier than yesterday**; future dates are allowed (this blueprint sends today + up to 7 days ahead).
- Each run consumes **1 + number_of_days_forecast** API tokens out of your daily per-device quota (the `token_remaining` sensor of the integration shows what is left). Running the script hourly with 4 forecast days = 120 calls/day — keep an eye on the quota shared with the integration's polling.
- Reported values **override** Netro's own weather provider for the given dates.

## Example: run it twice a day

```yaml
automation:
  - alias: "Netro weather sync"
    triggers:
      - trigger: time
        at:
          - "06:30:00"
          - "20:30:00"
    actions:
      - action: script.netro_weather_sync   # the script you created from the blueprint
        data:
          number_of_days_forecast: 4
```

A late-evening run is recommended: after 20:00 the measured rain/t_max from your station are considered final and replace the forecast for today.

## Troubleshooting

- **Script does nothing**: the weather entity returned no daily forecast — test `weather.get_forecasts` with `type: daily` in Developer Tools.
- **Service validation errors on pressure/humidity**: you are running an integration version whose `report_weather` schema does not accept `null` (≤ 2.1.0). Update the integration.
- **Wrong wind/pressure magnitude**: check the `wind_speed_unit` / `pressure_unit` attributes of your weather entity; unsupported units fall back to `km/h` / `hPa`.
- The script runs in `mode: single`: overlapping runs are skipped with a warning.
