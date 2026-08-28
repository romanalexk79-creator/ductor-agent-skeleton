#!/usr/bin/env python3
"""Kazakhstan calendar & economic features for demand analysis.

For any date returns the temporal/economic flags the spec asks the model to
use: weekday, weekend, public holiday, pre-holiday, long weekend, month part
(start/mid/end), and salary-window heuristics. These are FEATURES (extra
signals), not absolute rules.

Public-holiday set covers 2025-2026 (KZ official days). Islamic Kurban Ait is
approximate (moves yearly). Salary windows are a KZ heuristic (~10th and ~25th).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

# KZ public holidays 2025-2026 (month, day) with a label. Kurban Ait approx.
_HOLIDAYS: dict[str, str] = {}
for y in (2025, 2026):
    _HOLIDAYS.update({
        f"{y}-01-01": "Новый год", f"{y}-01-02": "Новый год",
        f"{y}-01-07": "Рождество",
        f"{y}-03-08": "Международный женский день",
        f"{y}-03-21": "Наурыз", f"{y}-03-22": "Наурыз", f"{y}-03-23": "Наурыз",
        f"{y}-05-01": "Праздник единства народа Казахстана",
        f"{y}-05-07": "День защитника Отечества",
        f"{y}-05-09": "День Победы",
        f"{y}-07-06": "День столицы",
        f"{y}-08-30": "День Конституции",
        f"{y}-10-25": "День Республики",
        f"{y}-12-16": "День Независимости", f"{y}-12-17": "День Независимости",
    })
_HOLIDAYS["2025-06-06"] = "Курбан айт"   # approx
_HOLIDAYS["2026-05-27"] = "Курбан айт"   # approx

_HOLIDAY_DATES = set(_HOLIDAYS)


def _is_weekend(d: dt.date) -> bool:
    return d.weekday() >= 5


def _is_dayoff(d: dt.date) -> bool:
    return _is_weekend(d) or d.isoformat() in _HOLIDAY_DATES


def features(d: dt.date) -> dict:
    iso = d.isoformat()
    is_hol = iso in _HOLIDAY_DATES
    tomorrow = d + dt.timedelta(days=1)
    is_pre = (not _is_dayoff(d)) and _is_dayoff(tomorrow)  # last working day before day(s) off
    # long weekend: this day is a day off AND the off-stretch it belongs to is >=3 days
    long_weekend = False
    if _is_dayoff(d):
        length, cur = 1, d - dt.timedelta(days=1)
        while _is_dayoff(cur):
            length += 1; cur -= dt.timedelta(days=1)
        cur = d + dt.timedelta(days=1)
        while _is_dayoff(cur):
            length += 1; cur += dt.timedelta(days=1)
        long_weekend = length >= 3
    dom = d.day
    month_part = "start" if dom <= 10 else ("end" if dom >= 21 else "mid")
    # KZ salary heuristic: advance ~10th, main ~25th; flag +-1 day windows
    payday = any(abs(dom - p) <= 1 for p in (10, 25))
    return {
        "date": iso,
        "weekday": d.weekday(),                 # 0=Mon
        "weekday_name": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][d.weekday()],
        "is_weekend": _is_weekend(d),
        "is_workday": not _is_dayoff(d),
        "is_holiday": is_hol,
        "holiday_name": _HOLIDAYS.get(iso),
        "is_preholiday": is_pre,
        "long_weekend": long_weekend,
        "month_part": month_part,               # start | mid | end
        "payday_window": payday,
        "month": d.month,
        "quarter": (d.month - 1) // 3 + 1,
        "season": ["зима", "весна", "лето", "осень"][(d.month % 12) // 3],
    }


def range_features(dfrom_ymd: str, dto_ymd: str) -> dict[str, dict]:
    d0 = dt.date(int(dfrom_ymd[:4]), int(dfrom_ymd[4:6]), int(dfrom_ymd[6:8]))
    d1 = dt.date(int(dto_ymd[:4]), int(dto_ymd[4:6]), int(dto_ymd[6:8]))
    return {(d0 + dt.timedelta(days=i)).isoformat(): features(d0 + dt.timedelta(days=i))
            for i in range((d1 - d0).days + 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (default today)")
    ap.add_argument("--from", dest="dfrom")
    ap.add_argument("--to", dest="dto")
    a = ap.parse_args()
    if a.dfrom and a.dto:
        r = range_features(a.dfrom, a.dto)
        print(json.dumps({"days": len(r), "holidays": [v["holiday_name"] for v in r.values() if v["is_holiday"]]},
                         ensure_ascii=False, indent=2))
    else:
        d = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
        print(json.dumps(features(d), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
