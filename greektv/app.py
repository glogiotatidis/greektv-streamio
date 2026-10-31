from fastapi import FastAPI
from fastapi.responses import JSONResponse

from greektv import catalog

app = FastAPI()


@app.get("/manifest.json")
def manifest():
    return catalog.manifest()


@app.get("/catalog/series/{catalog_id}.json")
def catalog_route(catalog_id: str):
    payload = catalog.catalog(catalog_id)
    if payload is None:
        return JSONResponse({"metas": []}, status_code=404)
    return payload


@app.get("/meta/series/{sid}.json")
def meta_route(sid: str):
    payload = catalog.get_meta(sid)
    if payload is None:
        return JSONResponse({"meta": None}, status_code=404)
    return {"meta": payload}


@app.get("/stream/series/{item_id}.json")
def stream_route(item_id: str):
    return {"streams": catalog.get_streams(item_id)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
