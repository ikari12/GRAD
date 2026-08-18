#!/usr/bin/env python3
"""Count how many included workouts used Haversine-derived speed."""
import csv
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(ROOT, "data", "meixner_4d_indices.csv")
JSON_PATH = os.path.join(ROOT, "data", "endomondoHR.json")

ids = set()
with open(CSV_PATH) as f:
    for row in csv.DictReader(f):
        ids.add(str(row["id"]))

n_recorded = 0
n_haversine = 0
n_seen = 0

with open(JSON_PATH) as f:
    for line in f:
        if n_seen >= len(ids):
            break
        line = line.strip()
        if not line or line in ("[", "]"):
            continue
        if line.endswith(","):
            line = line[:-1]
        if line.startswith(","):
            line = line[1:]
        try:
            rec = json.loads(
                line.replace("'", '"')
                .replace("True", "true")
                .replace("False", "false")
                .replace("None", "null")
            )
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(rec, dict):
            continue
        wid = str(rec.get("id", ""))
        if wid not in ids:
            continue
        n_seen += 1
        spd = rec.get("speed", [])
        if isinstance(spd, list) and len(spd) >= 10:
            n_recorded += 1
        else:
            n_haversine += 1
        if n_seen % 2000 == 0:
            print(f"  matched {n_seen}/{len(ids)}")

print(f"[KEY] n_included = {len(ids)}")
print(f"[KEY] n_matched = {n_seen}")
print(f"[KEY] n_recorded_speed = {n_recorded}")
print(f"[KEY] n_haversine_speed = {n_haversine}")
print(f"[KEY] pct_haversine = {100.0 * n_haversine / max(n_seen, 1):.2f}")
