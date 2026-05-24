"""Pluggable geo-IP lookup.

Backends:
  * `private`  — classifies private/loopback/link-local ranges as "LAN" or
                 "LOOPBACK"; everything else returns None. Default, no
                 external dependencies.
  * `mmdb`     — uses a MaxMind GeoLite2-Country database if `GEOIP_DB_PATH`
                 points to a `.mmdb` file. Requires the `maxminddb` package,
                 which is loaded lazily so it stays an opt-in install.

The dashboard treats `None` as "unknown" and skips country display, so it's
safe to deploy without a DB.
"""

from __future__ import annotations

import ipaddress
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_reader: Any | None = None
_initialized = False


def _try_init_mmdb() -> Any | None:
    """Open the MaxMind reader if GEOIP_DB_PATH is set and the lib is available."""
    path = os.environ.get("GEOIP_DB_PATH")
    if not path or not os.path.exists(path):
        return None
    try:
        import maxminddb  # type: ignore[import-not-found]
    except ImportError:
        logger.warning(
            "GEOIP_DB_PATH set but `maxminddb` package not installed; "
            "country lookup disabled. Install with `pip install maxminddb`."
        )
        return None
    try:
        reader = maxminddb.open_database(path)
        logger.info("Geo-IP backend: mmdb (%s)", path)
        return reader
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to open GEOIP_DB_PATH=%s: %s", path, exc)
        return None


def lookup_country(addr: str | None) -> str | None:
    """Return ISO 3166-1 alpha-2 country code, or a synthetic label for
    private ranges, or None when the lookup is impossible.
    """
    global _reader, _initialized
    if not _initialized:
        _reader = _try_init_mmdb()
        _initialized = True

    if not addr:
        return None
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return None

    if ip.is_loopback:
        return "LO"
    if ip.is_private or ip.is_link_local:
        return "LAN"

    if _reader is None:
        return None

    try:
        record = _reader.get(str(ip))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(record, dict):
        return None
    country = record.get("country") or record.get("registered_country") or {}
    iso = country.get("iso_code") if isinstance(country, dict) else None
    return iso if isinstance(iso, str) else None
