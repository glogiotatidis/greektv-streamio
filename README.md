# Greek TV Streamio

A Stremio / Nuvio addon that streams on-demand shows from Greek television stations.

## Supported stations

- Mega TV
- Skai
- Star Channel
- Alpha TV
- ERT
- ANT1

## Features

- Catalog browsing, series, season and episode navigation.
- Stream resolution for every offered episode.
- Static export for GitHub Pages deployment (no running server needed).

## Manifest

`https://glogiotatidis.github.io/greektv-streamio/manifest.json`

## Development

```bash
pip install fastapi beautifulsoup4 curl_cffi
GREEKTV_STATIONS=skai python static_export.py   # build a subset
python -m http.server -d site                  # serve locally
```

Environment variables:

- `GREEKTV_STATIONS` — comma-separated station slugs (empty = all).
- `GREEKTV_WORKERS` — discovery/show concurrency (default 10).
- `GREEKTV_STREAM_WORKERS` — stream resolution concurrency (default 10).
- `GREEKTV_MAX_SHOWS` — cap number of shows (0 = no cap).

## Source

https://github.com/glogiotatidis/greektv-streamio
