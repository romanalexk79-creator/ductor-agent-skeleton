#!/usr/bin/env python3
"""Weather provider for demand analysis (Open-Meteo, no key).

Two roles:
  * historical(dfrom, dto) — daily aggregates per date, for correlating past
    weather with past sales ("rain -> hot dishes +X%"). Cached to disk because
    past weather never changes; only missing/recent days are fetched.
  * current()   — current conditions + hourly forecast for the live layer
    (Phase 3 forecasting). Never cached.

City: Astana (51.18, 71.45), timezone Asia/Almaty (KZ, UTC+5).
All temperatures °C, precip mm, snow cm, wind km/h, humidity %.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

LAT, LON, TZ = 51.18, 71.45, "Asia/Almaty"
_CACHE = Path(__file__).resolve().parent.parent.parent / "cron_tasks" / "sales-analytics-nightly" / "state" / "weather_hist.json"
_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
_FORECAST = "https://api.open-meteo.com/v1/forecast"

_DAILY = ["temperature_2m_max", "temperature_2m_min", "apparent_temperature_max",
          "precipitation_sum", "rain_sum", "snowfall_sum", "wind_speed_10m_max",
          "relative_humidity_2m_mean", "weather_code"]


def _get(url: str, params: dict) -> dict:
    q = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{q}", timeout=30) as r:
        return json.loads(r.read().decode())


def _fetch_archive(dfrom: str, dto: str) -> dict[str, dict]:
    """dfrom/dto = YYYY-MM-DD. -> {date: {tmax,tmin,tapp,precip,rain,snow,wind,hum,code}}."""
    d = _get(_ARCHIVE, {"latitude": LAT, "longitude": LON, "timezone": TZ,
                        "start_date": dfrom, "end_date": dto, "daily": ",".join(_DAILY)})
    daily = d.get("daily", {})
    times = daily.get("time", [])
    out = {}
    for i, day in enumerate(times):
        g = lambda k: (daily.get(k) or [None] * len(times))[i]  # noqa: E731
        out[day] = {
            "tmax": g("temperature_2m_max"), "tmin": g("temperature_2m_min"),
            "tapp": g("apparent_temperature_max"), "precip": g("precipitation_sum"),
            "rain": g("rain_sum"), "snow": g("snowfall_sum"),
            "wind": g("wind_speed_10m_max"), "hum": g("relative_humidity_2m_mean"),
            "code": g("weather_code"),
        }
    return out


def historical(dfrom_ymd: str, dto_ymd: str) -> dict[str, dict]:
    """Cached daily history. Args YYYYMMDD. Fetches only days missing from cache."""
    d0 = dt.date(int(dfrom_ymd[:4]), int(dfrom_ymd[4:6]), int(dfrom_ymd[6:8]))
    d1 = dt.date(int(dto_ymd[:4]), int(dto_ymd[4:6]), int(dto_ymd[6:8]))
    cache: dict[str, dict] = {}
    if _CACHE.is_file():
        try:
            cache = json.loads(_CACHE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            cache = {}
    want = {(d0 + dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)}
    # Archive lags ~2 days; don't demand the very latest from it.
    horizon = (dt.date.today() - dt.timedelta(days=2)).isoformat()
    missing = sorted(d for d in want if d not in cache and d <= horizon)
    if missing:
        # fetch as one contiguous span (archive is cheap, gaps fill with None)
        got = _fetch_archive(missing[0], missing[-1])
        cache.update(got)
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return {d: cache[d] for d in sorted(want) if d in cache}


def current() -> dict:
    """Current conditions + next-24h hourly forecast for the live layer."""
    d = _get(_FORECAST, {
        "latitude": LAT, "longitude": LON, "timezone": TZ, "forecast_days": 2,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,"
                   "rain,snowfall,wind_speed_10m,cloud_cover,surface_pressure,weather_code",
        "hourly": "temperature_2m,apparent_temperature,precipitation,rain,snowfall,"
                  "wind_speed_10m,cloud_cover,weather_code",
    })
    return {"current": d.get("current", {}), "hourly": d.get("hourly", {}),
            "units": d.get("current_units", {})}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["current", "hist"])
    ap.add_argument("--from", dest="dfrom")
    ap.add_argument("--to", dest="dto")
    a = ap.parse_args()
    if a.mode == "current":
        print(json.dumps(current(), ensure_ascii=False, indent=2))
    else:
        h = historical(a.dfrom, a.dto)
        print(json.dumps({"days": len(h), "sample": dict(list(h.items())[-3:])},
                         ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
