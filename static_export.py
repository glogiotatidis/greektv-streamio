import json, os, shutil
from greektv.app import app
from fastapi.testclient import TestClient

client = TestClient(app)
out = "site"
if os.path.exists(out):
    shutil.rmtree(out)
os.makedirs(out + "/catalog/series", exist_ok=True)
os.makedirs(out + "/meta/series", exist_ok=True)
os.makedirs(out + "/stream/series", exist_ok=True)

manifest = client.get("/manifest.json").json()
with open(out + "/manifest.json", "w") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

catalog = client.get("/catalog/series/greek_tv.json").json()
with open(out + "/catalog/series/greek_tv.json", "w") as f:
    json.dump(catalog, f, ensure_ascii=False, indent=2)

for m in catalog["metas"]:
    sid = m["id"]
    meta = client.get(f"/meta/series/{sid}.json").json()
    with open(out + f"/meta/series/{sid}.json", "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    vid0 = meta["meta"]["videos"][0]["id"]
    # export first episode stream for each video
    for v in meta["meta"]["videos"]:
        st = client.get(f"/stream/series/{v['id']}.json").json()
        with open(out + f"/stream/series/{v['id']}.json", "w") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)

print("exported to", out)
