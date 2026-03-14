# Property Intelligence API (Web + Console Interfaces)

This application provides two interfaces for querying property intelligence:

1. **Web interface** for standard submissions with map validation and service selection.
2. **Console interface** for advanced query controls and super-user administration.

## Web interface

Open `GET /` to access a form with:

- Address search bar.
- Google Maps embedded frame to visually validate the submitted address.
- Service toggles (Census, USPS, Regrid, Official county/territory).

Submit via `/evaluate-web` and receive a rendered result payload.

## Console interface

Run:

```bash
python -m app.console --help
```

### Query command

```bash
python -m app.console query "1600 Pennsylvania Ave NW, Washington, DC" \
  --no-usps --disable-records --min-confidence 0.7 --max-severity warning
```

Options include:

- Enabling/disabling data categories (`--disable-records`, `--disable-pricing`, etc.).
- Toggling source connectors (`--no-census`, `--no-usps`, `--no-regrid`, `--no-official`).
- Provenance/confidence controls (`--min-confidence`, `--max-severity`).

### Super-user/admin console commands

- Create accounts (including AI/system accounts):

```bash
python -m app.console create-account analyst_admin superuser --account-type ai
```

- Audit searches over a time window:

```bash
python -m app.console audit 2026-01-01T00:00:00 2026-12-31T23:59:59
```

- Configure defaults:

```bash
python -m app.console set-defaults --min-confidence 0.65 --max-severity warning
```

## API endpoints

- `GET /` web interface
- `POST /evaluate-web` web submission endpoint
- `GET /health`
- `GET /coverage/{jurisdiction}`
- `POST /evaluate`
- `POST /admin/accounts`
- `GET /admin/audit`
- `GET /admin/audit/today`
- `POST /admin/defaults`
- `GET /admin/defaults`

## Data connectors

- Census geocoder (live)
- USPS connector (live with `USPS_USER_ID`, fallback mode without credentials)
- Regrid connector (live with `REGRID_API_TOKEN`, fallback mode without credentials)
- Official county/territory connector registry (currently demo official connector wiring)

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Environment variables

- `USPS_USER_ID`
- `REGRID_API_TOKEN`
