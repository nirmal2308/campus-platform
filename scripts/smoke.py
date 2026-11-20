"""Post-deployment smoke checks. Usage: python scripts/smoke.py BASE_URL EXPECTED_VERSION"""
import json
import sys
import urllib.request


def call(url, user=None):
    req = urllib.request.Request(url, headers={"X-User-Id": user} if user else {})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read())


def main(base, expected):
    checks = []
    st, body = call(f"{base}/health")
    checks.append(("health endpoint returns ok", st == 200 and body["status"] == "ok"))
    checks.append((f"deployed version == {expected}", body["version"] == expected))
    st, facilities = call(f"{base}/api/facilities", "u-stu")
    checks.append(("authenticated catalogue read", st == 200 and len(facilities) >= 1))
    checks.append(("restricted facility hidden from student", all(not f["restricted"] for f in facilities)))
    try:
        call(f"{base}/api/facilities")
        checks.append(("anonymous request rejected", False))
    except urllib.error.HTTPError as e:
        checks.append(("anonymous request rejected", e.code == 401))
    ok = True
    for name, passed in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
        ok &= passed
    print("SMOKE", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
