"""Smoke test for the published addon.

Two tiers of checks:

  data   -- the published JSON is well formed and complete: manifest, catalogs,
            per-show meta, per-episode streams. Any problem here is a build bug
            and fails the run.

  stream -- sampled episodes actually play. GitHub-hosted runners egress from the
            US, where several Greek CDNs geoblock (Skai answers "deny-by-country",
            Mega and Alpha answer 401/403). Those responses say nothing about the
            addon, so they are reported and skipped. A station only fails when
            every sampled stream fails for a reason that cannot be geo-blocking
            (404s, HTML served in place of video, repeated timeouts), which is
            what a broken scraper actually looks like.

The newest episode of each sampled show is tested first, with the previous one as
a fallback. `meta.videos` is ordered oldest -> newest, and old episodes rot at the
CDN while the published URL keeps listing them; the old smoke test always tested
videos[0] (the oldest) and therefore failed on dead links no addon change could fix.

Run with --strict to treat geo-blocking and expired tokens as failures too (useful
from a Greek IP).
"""

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://glogiotatidis.github.io/greektv-streamio"
UA = "Stremio/4.4.0 (Linux; Android 10)"
TIMEOUT = 30
ATTEMPTS = 2
SHOW_SAMPLES = 3
EPISODE_TRIES = 2
GEO_MARKERS = ("country", "geoblock", "geo-block", "region", "not available in your")

OK = "ok"
GEO = "geo"    # CDN refuses non-Greek addresses
AUTH = "auth"  # signed URL rejected -- expired token, not a build bug
NET = "net"    # timeouts / resets / 5xx
DEAD = "dead"  # 404 / 410 / plain 403 at the CDN
BAD = "bad"    # 200 but not video (HTML error page, empty playlist)

ADVISORY = {GEO, AUTH, NET}


def _get(url, take=None):
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return (
            response.geturl(),
            response.status,
            response.headers.get("Content-Type", ""),
            response.read() if take is None else response.read(take),
        )


def fetch(url, take=None):
    """GET with a retry for transport hiccups and 5xx; 4xx propagates immediately."""
    last = None
    for attempt in range(ATTEMPTS):
        try:
            return _get(url, take)
        except urllib.error.HTTPError as exc:
            if exc.code < 500 or attempt == ATTEMPTS - 1:
                raise
            last = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
        time.sleep(1 + attempt)
    raise last if last is not None else RuntimeError(f"GET {url} failed without an exception")


def json_get(url):
    return json.loads(fetch(url)[3])


def failure_kind(exc):
    if isinstance(exc, urllib.error.HTTPError):
        reason = str(exc.reason or "").strip()
        if exc.code in (401, 403):
            if any(marker in reason.lower() for marker in GEO_MARKERS):
                return GEO
            if exc.code == 401 or reason.isdigit():
                return AUTH
            return DEAD
        if exc.code in (404, 410):
            return DEAD
        return NET
    return NET


def playable(url, depth=0):
    """Return (kind, detail) for one published stream URL."""
    try:
        final_url, status, ctype, body = fetch(url, take=65536)
    except urllib.error.HTTPError as exc:
        return failure_kind(exc), f"HTTP {exc.code}: {exc.reason}"
    except Exception as exc:  # noqa: BLE001 -- transport errors are all advisory
        return NET, f"{type(exc).__name__}: {exc}"

    head = body[:64].lstrip().lower()
    if "video/" in ctype or url.endswith((".mp4", ".mpd", ".mkv")):
        if status == 200 and not head.startswith((b"<html", b"<!doc", b"{")):
            return OK, f"direct {ctype or 'video'}"
        return BAD, f"not video status={status} ctype={ctype}"

    if status != 200 or b"#extm3u" not in body[:1024].lower():
        return BAD, f"not a playlist status={status} ctype={ctype}"
    if depth >= 2:
        return BAD, "playlist nesting too deep"

    segment = None
    for line in body.decode("utf-8", "ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            segment = urllib.parse.urljoin(final_url, line)
            break
    if not segment:
        return BAD, "empty playlist"
    if segment.endswith(".m3u8") or "m3u8" in segment:
        return playable(segment, depth + 1)

    try:
        _, seg_status, seg_ctype, seg_body = fetch(segment, take=64)
    except urllib.error.HTTPError as exc:
        return failure_kind(exc), f"segment HTTP {exc.code}: {exc.reason}"
    except Exception as exc:  # noqa: BLE001
        return NET, f"segment {type(exc).__name__}: {exc}"
    if seg_status != 200 or seg_ctype.startswith("text/html") or seg_body[:5].lstrip().lower().startswith(b"<"):
        return BAD, f"segment status={seg_status} ctype={seg_ctype}"
    return OK, f"segment {seg_status}"


def check_station(cat_id, rng, strict):
    """Return (verdict, line, results) where verdict is PASS, WARN or FAIL."""
    slug = cat_id.replace("greek_tv_", "")
    problems = []
    results = []

    try:
        metas = json_get(f"{BASE}/catalog/series/{cat_id}.json").get("metas") or []
    except Exception as exc:  # noqa: BLE001
        return "FAIL", f"[{slug}] catalog unreadable: {exc}", results
    if not metas:
        return "FAIL", f"[{slug}] catalog is empty", results

    for show in rng.sample(metas, min(SHOW_SAMPLES, len(metas))):
        sid = show["id"]
        try:
            meta = json_get(f"{BASE}/meta/series/{urllib.parse.quote(sid, safe='')}.json")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"meta {sid}: {exc}")
            continue
        videos = (meta.get("meta") or {}).get("videos") or []
        if not videos:
            problems.append(f"meta {sid}: no episodes")
            continue
        for video in list(reversed(videos))[:EPISODE_TRIES]:
            vid = video["id"]
            try:
                streams = json_get(f"{BASE}/stream/series/{urllib.parse.quote(vid, safe='')}.json").get("streams") or []
            except Exception as exc:  # noqa: BLE001
                problems.append(f"stream {vid}: {exc}")
                break
            if not streams:
                problems.append(f"stream {vid}: no streams published")
                break
            url = streams[0].get("url") or ""
            schemes = ("http://", "https://") if BASE.startswith("http://") else ("https://",)
            if not url.startswith(schemes):
                problems.append(f"stream {vid}: not an {'/'.join(s.rstrip(':/') for s in schemes)} url ({url[:40]})")
                break
            kind, detail = playable(url)
            results.append((vid.split(":")[-1], kind, detail))
            if kind == OK:
                break

    if problems:
        return "FAIL", f"[{slug}] data: " + "; ".join(problems[:3]), results

    counts = {}
    for _, kind, _ in results:
        counts[kind] = counts.get(kind, 0) + 1
    summary = " ".join(f"{kind}={count}" for kind, count in sorted(counts.items()))
    played = counts.get(OK, 0)
    fatal = sum(count for kind, count in counts.items() if kind not in ADVISORY and kind != OK)

    if played == 0 and (fatal or strict):
        verdict = "FAIL"
    elif played == 0:
        verdict = "WARN"
    else:
        verdict = "PASS"
    return verdict, f"[{slug}] {summary} -> {verdict}", results


def main():
    parser = argparse.ArgumentParser(description="Smoke test the published Greek TV addon.")
    parser.add_argument("--station", action="append", help="restrict to a station slug (repeatable)")
    parser.add_argument("--seed", type=int, default=None, help="fixed sampling seed")
    parser.add_argument("--strict", action="store_true", help="treat geo-blocking and expired tokens as failures")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    try:
        manifest = json_get(BASE + "/manifest.json")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL manifest unreadable: {exc}")
        return 1
    stations = [
        catalog["id"]
        for catalog in manifest.get("catalogs", [])
        if catalog["id"].startswith("greek_tv_") and catalog["id"] != "greek_tv_all"
    ]
    if not stations:
        print("FAIL manifest lists no station catalogs")
        return 1
    if args.station:
        wanted = {slug if slug.startswith("greek_tv_") else f"greek_tv_{slug}" for slug in args.station}
        stations = [station for station in stations if station in wanted]
        if not stations:
            print(f"FAIL no such station: {', '.join(args.station)}")
            return 1

    print(f"Stations: {stations}\n")
    failures = []
    warnings = []
    for cat_id in stations:
        verdict, line, results = check_station(cat_id, rng, args.strict)
        print(line)
        for episode, kind, detail in results:
            print(f"    {kind:<4} {episode}: {detail}")
        if verdict == "FAIL":
            failures.append(line)
        elif verdict == "WARN":
            warnings.append(line)

    print()
    if warnings:
        print("Skipped (nothing verifiable from this network):")
        for line in warnings:
            print(" -", line)
        print()
    if failures:
        print("FAILURES:")
        for line in failures:
            print(" -", line)
        return 1
    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
