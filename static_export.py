import json
import logging
import argparse
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

from greektv import catalog

OUT = "site"
TMP = "site.tmp"
STREAM_WORKERS = int(os.environ.get("GREEKTV_STREAM_WORKERS", "10"))


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Greek TV Streamio</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         max-width: 760px; margin: 40px auto; padding: 0 20px; color: #222; line-height: 1.6; }
  h1 { border-bottom: 2px solid #eee; padding-bottom: 8px; }
  code { background: #f4f4f4; padding: 2px 6px; border-radius: 4px; }
  a { color: #0366d6; }
  .stations { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
  .station { background: #f0f0f0; padding: 4px 10px; border-radius: 12px; font-size: 14px; }
  .manifest { background: #f9f9f9; border: 1px solid #ddd; padding: 12px; border-radius: 6px;
              word-break: break-all; font-family: monospace; font-size: 13px; }
</style>
</head>
<body>
<h1>Greek TV Streamio</h1>
<p>A Stremio / Nuvio addon that streams on-demand shows from Greek television stations.
Catalog browsing, series, season and episode navigation, plus stream resolution.</p>

<h2>Supported stations</h2>
<div class="stations">
  <span class="station">Mega TV</span>
  <span class="station">Skai</span>
  <span class="station">Star Channel</span>
  <span class="station">Alpha TV</span>
  <span class="station">ERT</span>
  <span class="station">ANT1</span>
</div>

<h2>Install</h2>
<p>Add this manifest URL to your Stremio / Nuvio addon list:</p>
<div class="manifest">__MANIFEST_URL__</div>
<p>Or open <a href="manifest.json">manifest.json</a> directly.</p>

<h2>Endpoints</h2>
<ul>
  <li><code>GET /manifest.json</code></li>
  <li><code>GET /catalog/series/{id}.json</code></li>
  <li><code>GET /meta/series/{id}.json</code></li>
  <li><code>GET /stream/series/{id}.json</code></li>
</ul>

<p><a href="https://github.com/glogiotatidis/greektv-streamio">Source on GitHub</a></p>
</body>
</html>
"""


def write_index(path, manifest_url):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(INDEX_HTML.replace("__MANIFEST_URL__", manifest_url))


def main(full=False):
    if full:
        os.environ["GREEKTV_FULL"] = "1"
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    log = logging.getLogger("static_export")

    if os.path.exists(TMP):
        shutil.rmtree(TMP)
    os.makedirs(os.path.join(TMP, "catalog", "series"))
    os.makedirs(os.path.join(TMP, "meta", "series"))
    os.makedirs(os.path.join(TMP, "stream", "series"))

    manifest = catalog.manifest()
    write_json(os.path.join(TMP, "manifest.json"), manifest)
    manifest_url = "https://glogiotatidis.github.io/greektv-streamio/manifest.json"
    write_index(os.path.join(TMP, "index.html"), manifest_url)

    entries = catalog.all_entries()
    log.info("Loaded %d shows with episodes", len(entries))

    for definition in manifest["catalogs"]:
        catalog_id = definition["id"]
        payload = catalog.catalog(catalog_id)
        write_json(
            os.path.join(TMP, "catalog", "series", f"{catalog_id}.json"), payload
        )

    stream_jobs = []
    total_videos = 0
    for entry in entries:
        sid = entry["sid"]
        meta = catalog.get_meta(sid)
        write_json(os.path.join(TMP, "meta", "series", f"{sid}.json"), {"meta": meta})
        for video in meta["videos"]:
            total_videos += 1
            stream_jobs.append(video["id"])

    log.info("Exporting %d streams", total_videos)

    def existing_stream(item_id):
        # Incremental: reuse a previously resolved stream file when possible.
        if full:
            return None
        path = os.path.join(OUT, "stream", "series", f"{item_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return None
        streams = payload.get("streams") or []
        if not streams:
            return None
        return streams

    def export_stream(item_id):
        cached = existing_stream(item_id)
        if cached is not None:
            write_json(
                os.path.join(TMP, "stream", "series", f"{item_id}.json"),
                {"streams": cached},
            )
            return True
        streams = catalog.get_streams(item_id)
        write_json(
            os.path.join(TMP, "stream", "series", f"{item_id}.json"),
            {"streams": streams},
        )
        return bool(streams)

    resolved = 0
    failed = 0
    cached_count = 0
    with ThreadPoolExecutor(max_workers=max(1, STREAM_WORKERS)) as pool:
        futures = {pool.submit(export_stream, item_id): item_id for item_id in stream_jobs}
        for index, future in enumerate(as_completed(futures), start=1):
            try:
                if future.result():
                    resolved += 1
                else:
                    failed += 1
            except Exception:  # noqa: BLE001
                failed += 1
                log.exception("Stream export crashed for %s", futures[future])
            if index % 100 == 0 or index == total_videos:
                log.info("Streams %d/%d", index, total_videos)

    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.replace(TMP, OUT)

    log.info(
        "Exported %d shows, %d streams (%d resolved, %d empty) to %s",
        len(entries),
        total_videos,
        resolved,
        failed,
        OUT,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Re-fetch every stream")
    args = parser.parse_args()
    full = args.full or os.environ.get("GREEKTV_FULL", "").lower() in ("1", "true", "yes")
    main(full=full)
