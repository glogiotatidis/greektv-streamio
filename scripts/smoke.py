import json, urllib.request, urllib.parse, sys, random

BASE = "https://glogiotatidis.github.io/greektv-streamio"
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
        tested += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read(200).decode("utf-8", "ignore")
            if r.status == 200 and "#EXTM3U" in body:
                ok_streams += 1
                print(f"[{slug}] OK: {url[:60]}...")
            else:
                print(f"[{slug}] BAD status/content: {r.status}")
                failures.append(f"{slug}: bad stream {url}")
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
PY
