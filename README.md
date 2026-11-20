# Smart Campus Facility Platform - CO4 testing and DevOps pipeline

Representative service (Flask + SQLite) used for Software Engineering Assignment 4:
facility booking, restricted-lab approval, sensor alerts, maintenance tickets, audit log,
and an outbox for calendar / issue-tracker synchronisation. All data is synthetic.

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest                       # 100 tests (unit, integration, regression, security)
./scripts/gate.sh                      # release gate: tests + coverage>=90% + Bandit + secret scan
CAMPUS_DB_PATH=./campus.db APP_VERSION=local gunicorn --preload -w 2 -b 127.0.0.1:8000 app.__main__:app
python scripts/smoke.py http://127.0.0.1:8000 local
python scripts/load_test.py http://127.0.0.1:8000 ./campus.db load.json
python scripts/rollback_rehearsal.py   # failed-deployment + rollback drill
python scripts/authz_matrix.py         # role x endpoint authorization probe
```

## Container and staging
```bash
docker build --build-arg APP_VERSION=v2.0.0-$(git rev-parse --short HEAD) -t campus-platform:v2.0.0-$(git rev-parse --short HEAD) .
IMAGE_TAG=v2.0.0-$(git rev-parse --short HEAD) APP_VERSION=$IMAGE_TAG docker compose -f docker-compose.staging.yml up -d
python scripts/smoke.py http://localhost:18000 v2.0.0-$(git rev-parse --short HEAD)
```

## Layout
`app/` service code - `migrations/` SQL (001 initial, 002 campus policy + rollback) - `tests/` unit, integration, regression -
`scripts/` gate, smoke, load, rollback, authz probe - `.github/workflows/ci.yml` and `Jenkinsfile` pipelines - `evidence/` logs referenced by the report.

## Releases (git tags)
v1.0.0 baseline - v1.0.1 start-up race fix - v1.1.0 after defect drill (D1-D3 reverted) - v2.0.0 campus policies + migration 002.
Secrets are never committed: copy `.env.example` to `.env` locally; CI uses repository secrets.
