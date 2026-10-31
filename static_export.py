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


def main(full=False):
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
    main(full=args.full)
