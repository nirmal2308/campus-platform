"""Bounded load experiment against a running instance.
Usage: python scripts/load_test.py BASE_URL DB_PATH OUT_JSON"""
import json
import sqlite3
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests

BASE, DB, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
H = {"X-User-Id": "u-stu"}
lat = []


def timed(fn, *a):
    t = time.perf_counter()
    r = fn(*a)
    lat.append((time.perf_counter() - t) * 1000)
    return r


def book(i):
    # distinct 1-hour slots over days/facilities -> no intentional conflicts
    day = datetime(2027, 1, 1) + timedelta(days=i // 40)
    start = day + timedelta(hours=8 + (i % 10))
    fid = 1 + (i // 10) % 4 if (1 + (i // 10) % 4) != 3 else 1
    body = {"facility_id": fid, "start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat()}
    return timed(lambda: requests.post(f"{BASE}/api/bookings", json=body, headers=H, timeout=30)).status_code


def read(_):
    return timed(lambda: requests.get(f"{BASE}/api/facilities", headers=H, timeout=30)).status_code


def contested(_):
    body = {"facility_id": 4, "start": "2027-03-01T09:00", "end": "2027-03-01T10:00"}
    return timed(lambda: requests.post(f"{BASE}/api/bookings", json=body, headers=H, timeout=30)).status_code


t0 = time.perf_counter()
with ThreadPoolExecutor(max_workers=10) as ex:
    # phase A: mixed workload 10 concurrent clients
    book_codes = list(ex.map(book, range(150)))
    read_codes = list(ex.map(read, range(150)))
with ThreadPoolExecutor(max_workers=20) as ex:
    # phase B: 20 clients race for the SAME slot - exactly one may win
    race_codes = list(ex.map(contested, range(20)))
wall = time.perf_counter() - t0

con = sqlite3.connect(DB)
rows = con.execute("SELECT facility_id,start_time,end_time FROM bookings ORDER BY facility_id,start_time").fetchall()
overlaps = sum(1 for a, b in zip(rows, rows[1:]) if a[0] == b[0] and b[1] < a[2])
lat.sort()
pct = lambda p: lat[min(len(lat) - 1, int(len(lat) * p))]
res = {
    "requests_total": len(lat), "wall_seconds": round(wall, 2),
    "throughput_rps": round(len(lat) / wall, 1),
    "phaseA_book_201": book_codes.count(201), "phaseA_book_other": len(book_codes) - book_codes.count(201),
    "phaseA_read_200": read_codes.count(200),
    "phaseB_race_201": race_codes.count(201), "phaseB_race_409": race_codes.count(409),
    "phaseB_race_other": len(race_codes) - race_codes.count(201) - race_codes.count(409),
    "latency_ms": {"min": round(lat[0], 1), "p50": round(statistics.median(lat), 1), "p95": round(pct(.95), 1),
                   "p99": round(pct(.99), 1), "max": round(lat[-1], 1)},
    "stored_bookings": len(rows), "overlapping_pairs_in_db": overlaps,
    "latencies_ms": [round(x, 2) for x in lat],
}
json.dump(res, open(OUT, "w"))
print(json.dumps({k: v for k, v in res.items() if k != "latencies_ms"}, indent=2))
