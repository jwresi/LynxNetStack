# Tikfig Installer (MVP)

A lightweight, cross-platform local web UI that pulls device context from NetBox, renders your Jinja2 RouterOS templates, and guides technicians through a simple install flow.

## What it does

- Live device discovery via TCP check to the default MikroTik API address.
- NetBox lookup to hydrate config context and device metadata.
- Jinja2 rendering of your switch/router templates.
- Downloadable RouterOS `.rsc` output.

## Quick start

1. Copy `config.example.yml` to `config.yml` and update:
   - `netbox.url`
   - `netbox.token`
2. Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Run the server:

```bash
python app.py
```

Open `http://localhost:8080` in your browser.

## Notes

- The templates expect a populated NetBox config context (`device.get_config_context()`).
- Optional overrides are provided in the UI for CGNAT/DIGI fields or model overrides.
- If a model interface map is missing from NetBox, `config.yml` can provide a fallback.
