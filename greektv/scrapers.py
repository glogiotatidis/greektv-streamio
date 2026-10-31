import re, json, urllib.parse
from curl_cffi import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0"}

def fetch(url):
    r = requests.get(url, impersonate="chrome")
    r.raise_for_status()
    return r.text

def mega_episode_stream(url):
    html = fetch(url)
    m = re.search(r'data-kwik_source="([^"]*m3u8[^"]*)"', html)
    if not m:
        m = re.search(r'(https?://[^"\']*playlist\.m3u8[^"\']*)', html)
    if not m:
        raise RuntimeError("mega stream not found")
    return m.group(1)

def mega_show(show_url):
    html = fetch(show_url)
    title = "Mega TV Show"
    m = re.search(r'<title>(.*?)</title>', html, re.S)
    if m:
        title = m.group(1).strip()
    return {"station":"Mega TV","title":title,"episodes":[{"id":"latest","title":title,"url":show_url}]}

def skai_stream(episode_url):
    html = fetch(episode_url)
    i = html.find('"episode"')
    # find var data = { ... } containing episode
    idx = html.find('var data = {"episode"')
    if idx < 0:
        idx = html.find("var data = {\"episode\"")
    brace = html.find('{', idx)
    obj,_ = json.JSONDecoder().raw_decode(html[brace:])
    ep = obj["episode"][0]
    media_file = ep["media_item_file"]
    return f"https://videostream.skai.gr/skaivod/_definst_/mp4:skai/{media_file}/chunklist.m3u8"

def skai_show(show_url):
    # show_url may be an episode URL; keep as one episode
    html = fetch(show_url)
    title = "Skai Show"
    m = re.search(r'<title>(.*?)</title>', html, re.S)
    if m:
        title = m.group(1).strip()
    return {"station":"Skai","title":title,"episodes":[{"id":"latest","title":title,"url":show_url}]}

def star_stream(episode_url):
    html = fetch(episode_url)
    m = re.search(r'data-video="([^"]+)"', html)
    if not m:
        raise RuntimeError("star data-video not found")
    entry_id = m.group(1)
    return f"https://cdnapisec.kaltura.com/p/713821/sp/0/playManifest/entryId/{entry_id}/format/applehttp/protocol/https/flavorParamId/0/manifest.m3u8"

def star_show(show_url):
    html = fetch(show_url)
    title = "Star Show"
    m = re.search(r'<title>(.*?)</title>', html, re.S)
    if m:
        title = m.group(1).strip()
    # collect episode links
    eps = []
    seen=set()
    for m in re.finditer(r'href="(/tv/[^"]+)"', html):
        href=m.group(1)
        if 'epeisodio' in href.lower() or 'episode' in href.lower():
            full="https://www.star.gr"+href
            if full not in seen:
                seen.add(full)
                eps.append({"id":href.strip('/').split('/')[-1],"title":href.strip('/').split('/')[-1].replace('-',' '),"url":full})
    if not eps:
        eps=[{"id":"latest","title":title,"url":show_url}]
    return {"station":"Star Channel","title":title,"episodes":eps[:20]}

def alpha_stream(episode_url):
    html = fetch(episode_url)
    m = re.search(r'https://[^"\' ]+\.mp4', html)
    if not m:
        raise RuntimeError("alpha mp4 not found")
    return m.group(0)

def alpha_show(show_url, fallback_url=None):
    html = fetch(show_url)
    title = "Alpha Show"
    m = re.search(r'<title>(.*?)</title>', html, re.S)
    if m:
        title = m.group(1).strip()
    eps=[]
    seen=set()
    for m in re.finditer(r'href="(/series/[^"]+/episode/[^"]+)"', html):
        full="https://www.alphatv.gr"+m.group(1)
        if full not in seen:
            seen.add(full)
            eps.append({"id":m.group(1).strip('/').split('/')[-1],"title":m.group(1).strip('/').split('/')[-1].replace('-',' '),"url":full})
    if not eps:
        eps=[{"id":"latest","title":title,"url":fallback_url or show_url}]
    return {"station":"Alpha TV","title":title,"episodes":eps[:20]}
def ert_stream(series_url, episode_index=0):
    # use ertflix API
    html = fetch(series_url)
    series_id = series_url.rstrip('/').split('/')[-1]
    # series_id like ser.305756-elektra -> id for API is part before? extractor uses id = last path segment? Actually obtain_id regex. Use series id param = 'ser.305756' ? API expects id maybe 'ser.305756-elektra'? Let's derive from extractor logic: id = re.findall("(?!.*\/)[^-]*", url)[0] -> first non-dash segment of basename = 'ser.305756'? Actually basename ser.305756-elektra, [^-]* => ser.305756. Use that.
    api_id = series_id.split('-')[0]
    params = {"platformCodename":"www","id":api_id}
    r = requests.get("https://api.app.ertflix.gr/v1/Tile/GetSeriesDetails", params=params, impersonate="chrome")
    details = r.json()
    # pick first episode of first season
    ep = None
    for season in details.get("EpisodeGroups", []) or []:
        episodes = season.get("Episodes") or season.get("episodes") or []
        if episodes:
            ep = episodes[episode_index if episode_index < len(episodes) else 0]
            break
    if not ep:
        raise RuntimeError("ert no episode")
    codename = ep.get("Codename") or ep.get("codename")
    params2 = {"platformCodename":"www","codename":codename}
    r2 = requests.get("https://api.app.ertflix.gr/v1/Player/AcquireContent", params=params2, impersonate="chrome")
    data = r2.json()
    if not data.get("Result",{}).get("Success"):
        raise RuntimeError("ert acquire failed")
    mediafile=None
    for mf in data.get("MediaFiles",[]):
        if mf.get("RoleName")=="main":
            mediafile=mf; break
    if mediafile is None and data.get("MediaFiles"):
        mediafile=data["MediaFiles"][0]
    index_url=None
    for fmt in mediafile.get("Formats",[]):
        if ".m3u8" in fmt.get("Url",""):
            index_url=fmt["Url"]; break
    if not index_url:
        raise RuntimeError("ert m3u8 not found")
    return index_url

def ert_show(series_url):
    html = fetch(series_url)
    title = "ERT Show"
    m = re.search(r'<title>(.*?)</title>', html, re.S)
    if m:
        title = m.group(1).strip()
    # episodes from API
    series_id = series_url.rstrip('/').split('/')[-1]
    api_id = series_id.split('-')[0]
    params = {"platformCodename":"www","id":api_id}
    r = requests.get("https://api.app.ertflix.gr/v1/Tile/GetSeriesDetails", params=params, impersonate="chrome")
    details = r.json()
    eps=[]
    for season in details.get("EpisodeGroups", []) or []:
        episodes = season.get("Episodes") or season.get("episodes") or []
        for ep in episodes[:20]:
            eps.append({"id":ep.get("Codename") or ep.get("codename","ep"),"title":ep.get("Title") or ep.get("subtitle") or "Episode","url":series_url,"codename":ep.get("Codename") or ep.get("codename")})
    if not eps:
        eps=[{"id":"latest","title":title,"url":series_url}]
    return {"station":"ERT","title":title,"episodes":eps}
