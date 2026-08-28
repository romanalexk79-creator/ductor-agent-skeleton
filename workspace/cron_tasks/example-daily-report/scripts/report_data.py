#!/usr/bin/env python3
"""Example report-data collector for the skeleton.

Returns DEMO data. Replace the body of collect() with a real call into your
own connector under tools/integrations/ (e.g. a POS client, a sheet, an API).
"""
import json


def collect() -> dict:
    # TODO: replace with a real integration call.
    return {
        "date": "YYYY-MM-DD",
        "metric_a": 0,
        "metric_b": 0,
        "note": "demo data — wire this to tools/integrations/",
    }


def main() -> int:
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
