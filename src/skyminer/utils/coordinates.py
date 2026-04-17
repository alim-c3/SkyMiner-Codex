"""SkyMiner coordinate utility helpers."""

from __future__ import annotations


def coords_to_str(ra_deg: float, dec_deg: float) -> str:
    """Format an RA/Dec coordinate pair as a human-readable string.

    Args:
        ra_deg: Right ascension in decimal degrees.
        dec_deg: Declination in decimal degrees.

    Returns:
        A string of the form ``"RA=123.456 Dec=-45.678"``.
    """
    return f"RA={ra_deg:.3f} Dec={dec_deg:.3f}"


def parse_coord_pair(ra_str: str, dec_str: str) -> tuple[float, float]:
    """Parse string representations of RA and Dec into floats.

    Args:
        ra_str: String representation of right ascension in decimal degrees.
        dec_str: String representation of declination in decimal degrees.

    Returns:
        ``(ra_deg, dec_deg)`` as a tuple of floats.

    Raises:
        ValueError: If either string cannot be converted to a finite float,
                    or if the values fall outside their valid ranges.
    """
    try:
        ra = float(ra_str)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"Invalid RA value {ra_str!r}: must be a decimal-degree number."
        ) from exc

    try:
        dec = float(dec_str)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"Invalid Dec value {dec_str!r}: must be a decimal-degree number."
        ) from exc

    if not (-360.0 <= ra <= 360.0):
        raise ValueError(f"RA value {ra} is out of expected range [-360, 360].")
    if not (-90.0 <= dec <= 90.0):
        raise ValueError(f"Dec value {dec} is out of expected range [-90, 90].")

    return ra, dec
