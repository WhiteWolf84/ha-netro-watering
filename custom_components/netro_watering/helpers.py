"""Shared helpers for the Netro Watering integration."""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)


def get_int_option(
    sources: tuple,
    default: int,
    minimum: int,
    maximum: int,
    name: str,
) -> int:
    """Pick the first non-None value from ``sources``, coerce to int and clamp.

    Falls back to ``default`` (logging a warning) when the chosen value is
    missing, not an integer, or outside the ``[minimum, maximum]`` range. This
    centralizes the option-parsing pattern shared by every config field.
    """
    value = next((v for v in sources if v is not None), default)
    try:
        result = int(value)
    except TypeError, ValueError:
        _LOGGER.warning(
            "The value provided for '%s' is invalid, defaulting to %d", name, default
        )
        return default
    if not minimum <= result <= maximum:
        _LOGGER.warning(
            "The value provided for '%s' is out of range [%d..%d], defaulting to %d",
            name,
            minimum,
            maximum,
            default,
        )
        return default
    return result
