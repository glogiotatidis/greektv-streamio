import re

from bs4 import BeautifulSoup

from greektv.common import clean, fetch, fetch_json, page_poster, page_title, placeholder, slug_title

BASE = "https://www.antenna.gr"
EXCLUDED = {"live", "shows", "search", "contact"}


def _title(raw):
    title = clean(raw)
    if " / " in title:
        title = title.split(" / ", 1)[1]
    return title or "ANT1"


def discover():
    try:
        html = fetch(f"{BASE}/shows")
    except Exception:  # noqa: BLE001
        return []
    shows = {}
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        match = re.match(r"^https://www\.antenna\.gr/([a-z0-9-]+)$", href.rstrip("/"))
        if not match:
            continue
        slug = match.group(1)
        if slug in EXCLUDED:
            continue
        classes = " ".join(anchor.get("class") or [])
        text = clean(anchor.get_text(" "))
        if "channel-tv-sidebar-live" in classes or "TV Shows" not in text:
            continue
        url = f"{BASE}/{slug}"
        shows.setdefault(
            url,
            {
                "url": url,
                "title": slug_title(slug),
                "poster": None,
                "data": {},
            },
        )
    return list(shows.values())


def _season_and_episode(text, slug):
    combined = f"{text} {slug}"
    season = 0
    episode = 0

    season_match = re.search(
        r"(\d+)(?:η|ος|i|os|h)[-_ ]?(?:σεζόν|sezon|κύκλος|kyklos|kuklos)",
        combined,
        re.I,
    )
    if not season_match:
        season_match = re.search(r"sezon[-_ ]?(\d+)", combined, re.I)
    if season_match:
        season = int(season_match.group(1))

    episode_match = re.search(r"επεισόδιο[-_ ]?(\d+)", combined, re.I)
    if not episode_match:
        episode_match = re.search(r"epeisodio[-_ ]?(\d+)", combined, re.I)
    if episode_match:
        episode = int(episode_match.group(1))
    return season, episode


def _poster(html, title):
    poster = page_poster(html)
    if poster:
        return poster
    match = re.search(
        r'(https://antenna-ott\.brightcove\.services/static/uploads/[^"\']+)', html
    )
    if match:
        return match.group(1)
    return placeholder(title)


def show(ref):
    html = fetch(ref["url"])
    title = _title(page_title(html))
    poster = _poster(html, title)

    episodes = {}
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        match = re.match(r"^/watch/([a-z0-9]+)/([^/?#]+)", anchor["href"])
        if not match:
            continue
        cid = match.group(1)
        slug = match.group(2)
        text = clean(anchor.get_text(" "))
        season, number = _season_and_episode(text, slug)
        episode_title = text or slug_title(slug)
        url = f"{BASE}/watch/{cid}/{slug}"
        episodes.setdefault(
            cid,
            {
                "id": cid,
                "url": url,
                "title": episode_title,
                "season": season or 1,
                "episode": number,
                "extra": {"cid": cid},
            },
        )

    result = list(episodes.values())
    result.sort(key=lambda episode: (episode["season"], episode.get("episode") or 0))
    return {"title": title, "poster": poster, "episodes": result}


def stream(episode):
    cid = episode.get("extra", {}).get("cid")
    if not cid:
        raise RuntimeError("ANT1 episode without cid")
    payload = fetch_json(
        f"{BASE}/templates/data/PlayerDataGraphQL_v2", params={"cid": cid}
    )
    video_url = (payload.get("video_url") or "").strip()
    if video_url:
        return video_url
    url = (payload.get("url") or "").strip()
    if url:
        return url
    raise RuntimeError(f"ANT1 stream not found for {cid}")
