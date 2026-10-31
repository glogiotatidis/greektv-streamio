import json, os
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from greektv.scrapers import *

app = FastAPI()

SHOWS = [
    {"station":"Mega TV","url":"https://www.megatv.com/ekpompes/2427394/kampingk/","scraper":mega_show,"stream":lambda u: mega_episode_stream(u)},
    {"station":"Skai","url":"https://www.skai.gr/tv/episode/seires/tote-vs-tora/2026-04-01-21","scraper":skai_show,"stream":lambda u: skai_stream(u)},
    {"station":"Star Channel","url":"https://www.star.gr/tv/seires/ta-fadasmata/ta-fadasmata-epeisodio-3-2os-kuklos","scraper":lambda u: star_show("https://www.star.gr/tv/seires/ta-fadasmata"),"stream":lambda u: star_stream(u)},
    {"station":"Alpha TV","url":"https://www.alphatv.gr/series/sasmos/episode/277555-s3-epeisodio-152/","scraper":lambda u: alpha_show("https://www.alphatv.gr/series/sasmos", fallback_url=u),"stream":lambda u: alpha_stream(u)},
    {"station":"ERT","url":"https://www.ertflix.gr/series/ser.305756-elektra","scraper":ert_show,"stream":lambda u, ep=None: ert_stream(u)},
]

import hashlib
def show_id(s):
    return "greek_tv:" + s["station"].lower().replace(" ","_") + ":" + hashlib.md5(s["url"].encode()).hexdigest()[:8]

@app.get("/manifest.json")
def manifest():
    return {
        "id":"com.greektv.streamio",
        "version":"1.0.0",
        "name":"Greek TV Streamio",
        "description":"On-demand streams from Greek TV stations",
        "resources":["catalog","meta","stream"],
        "types":["series"],
        "catalogs":[{"type":"series","id":"greek_tv","name":"Greek TV On Demand"}],
        "idPrefixes":["greek_tv:"],
    }

@app.get("/catalog/series/greek_tv.json")
def catalog():
    metas=[]
    for s in SHOWS:
        sid=show_id(s)
        metas.append({"id":sid,"type":"series","name":s["scraper"](s["url"])["title"],"poster":"https://placehold.co/300x450?text="+s["station"]})
    return {"metas":metas}

@app.get("/meta/series/{sid}.json")
def meta(sid):
    for s in SHOWS:
        if show_id(s)==sid:
            data=s["scraper"](s["url"])
            videos=[]
            for ep in data["episodes"]:
                eid=sid+":"+ep["id"]
                videos.append({"id":eid,"title":ep["title"],"season":1,"episode":len(videos)+1})
            return {"meta":{"id":sid,"type":"series","name":data["title"],"videos":videos}}
    return JSONResponse({"meta":None}, status_code=404)

@app.get("/stream/series/{item_id}.json")
def stream_item(item_id):
    if ":" not in item_id or item_id.count(":") < 3:
        return {"streams":[]}
    sid, eid = item_id.rsplit(":", 1)
    for s in SHOWS:
        if show_id(s)==sid:
            data=s["scraper"](s["url"])
            for ep in data["episodes"]:
                if ep["id"]==eid:
                    try:
                        if s["station"]=="ERT":
                            url = ert_stream(s["url"], data["episodes"].index(ep))
                        else:
                            url = s["stream"](ep["url"])
                        return {"streams":[{"title":ep["title"],"url":url}]}
                    except Exception:
                        return {"streams":[]}
    return {"streams":[]}

if __name__=="__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
