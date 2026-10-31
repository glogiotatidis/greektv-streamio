import json, urllib.request, urllib.parse, sys, random

BASE = "https://glogiotatidis.github.io/greektv-streamio"
UA = "Stremio/4.4.0 (Linux; Android 10)"
manifest = json.loads(urllib.request.urlopen(BASE + "/manifest.json").read())
stations = [c["id"] for c in manifest["catalogs"] if c["id"].startswith("greek_tv_") and c["id"] != "greek_tv_all"]
print("Stations:", stations)

failures = []
for cat_id in stations:
    slug = cat_id.replace("greek_tv_", "")
    catalog = json.loads(urllib.request.urlopen(f"{BASE}/catalog/series/{cat_id}.json").read())
    metas = catalog.get("metas", [])
    if not metas:
        print(f"[{slug}] no shows")
        failures.append(f"{slug}: no shows")
        continue
    sample_shows = random.sample(metas, min(3, len(metas)))
    ok_streams = 0
    tested = 0
    for show in sample_shows:
        sid = show["id"]
        meta = json.loads(urllib.request.urlopen(f"{BASE}/meta/series/{urllib.parse.quote(sid, safe='')}.json").read())
        videos = meta.get("meta", {}).get("videos", [])
        if not videos:
            continue
        vid = videos[0]["id"]
        stream_resp = json.loads(urllib.request.urlopen(f"{BASE}/stream/series/{urllib.parse.quote(vid, safe='')}.json").read())
        streams = stream_resp.get("streams", [])
        if not streams:
            print(f"[{slug}] {sid}: no stream")
            failures.append(f"{slug}: no stream for {vid}")
            continue
        url = streams[0]["url"]
        if slug == "ert" and "mediaserve.ert.gr" in url:
            print(f"[{slug}] FAIL: unresolved mediaserve URL {url}")
            failures.append(f"{slug}: unresolved mediaserve URL {url}")
            continue
        tested += 1
        def fetch_segment(playlist_url, depth=0):
            if depth > 2:
                return False, "too deep"
            req = urllib.request.Request(playlist_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read(65536).decode("utf-8", "ignore")
                final_url = r.geturl()
                status = r.status
                ctype = r.headers.get("Content-Type", "")
            if status != 200 or "#EXTM3U" not in body:
                return False, f"bad playlist status={status} ctype={ctype}"
            # find first non-comment line
            seg_url = None
            for line in body.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    seg_url = urllib.parse.urljoin(final_url, line)
                    break
            if not seg_url:
                return False, "no segment in playlist"
            # if it's another playlist (master), recurse
            if seg_url.endswith(".m3u8") or "m3u8" in seg_url:
                return fetch_segment(seg_url, depth + 1)
            # fetch the segment
            seg_req = urllib.request.Request(seg_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(seg_req, timeout=30) as sr:
                seg_body = sr.read(64)
                seg_status = sr.status
                seg_ctype = sr.headers.get("Content-Type", "")
            if seg_status != 200 or seg_ctype.startswith("text/html") or b"<html" in seg_body.lower():
                return False, f"bad segment status={seg_status} ctype={seg_ctype}"
            return True, f"seg {seg_status}"

        try:
            ok, msg = fetch_segment(url)
            if ok:
                ok_streams += 1
                print(f"[{slug}] OK: {url[:60]}... ({msg})")
            else:
                print(f"[{slug}] BAD: {msg}")
                failures.append(f"{slug}: {msg} {url}")
        except Exception as e:
            print(f"[{slug}] FAIL: {e}")
            failures.append(f"{slug}: {e}")
    print(f"[{slug}] tested={tested} ok={ok_streams}")

if failures:
    print("\nFAILURES:")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("\nAll smoke tests passed.")
