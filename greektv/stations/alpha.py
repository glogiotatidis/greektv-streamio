import re

from bs4 import BeautifulSoup

from greektv.common import clean, fetch, page_poster, page_title, placeholder, slug_title

BASE = "https://www.alphatv.gr"


def _title(raw):
    title = clean(raw)
    for prefix in ("Σειρά: ", "Εκπομπή: "):
        if title.startswith(prefix):
            title = title[len(prefix):]
    if title.endswith("| AlphaTV"):
        title = title[: -len("| AlphaTV")].strip()
    return title or "Alpha TV"


def discover():
    shows = {}
    for listing, pattern in (
        (f"{BASE}/series/", r'href="(https://www\.alphatv\.gr/series/([a-z0-9-]+)/)"'),
        (f"{BASE}/shows/", r'href="(https://www\.alphatv\.gr/show/([a-z0-9-]+)/)"'),
    ):
        try:
            html = fetch(listing)
        except Exception:  # noqa: BLE001
            continue
        for match in re.finditer(pattern, html):
            url = match.group(1)
            shows.setdefault(
                url,
                {
                    "url": url,
                    "title": slug_title(match.group(2)),
                    "poster": None,
                    "data": {"kind": "series" if "/series/" in url else "show"},
                },
            )
    return list(shows.values())


def _season_and_episode(slug):
    season = 0
    episode = 0
    match = re.search(
        r"(?:^|[-_])s[-_ ]?(\d+)[-_ ]?(?:ep|e|epeisodio)[-_ ]?(\d+)", slug
    )
    if match:
        season = int(match.group(1))
        episode = int(match.group(2))
    else:
        match = re.search(r"(?:^|[-_])(?:ep|e|epeisodio)[-_ ]?(\d+)", slug)
        if match:
            episode = int(match.group(1))
    return season, episode


def _episode_links(html, slug, kind):
    segment = "episode" if kind == "series" else "show-episode"
    prefix = f"{BASE}/{'series' if kind == 'series' else 'show'}/{slug}/{segment}/"
    found = {}
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if not href.startswith(prefix):
            continue
        url = href.split("?")[0]
        episode_slug = url.rstrip("/").split("/")[-1]
        text = clean(anchor.get_text(" "))
        found.setdefault(
            url,
            {
                "id": episode_slug,
                "url": url,
                "title": text,
                "slug": episode_slug,
            },
        )
        if text and not found[url]["title"]:
            found[url]["title"] = text
    return list(found.values())


def _collect_pages(base_url, kind, slug, season=None, season_query=False):
    suffix = f"?season=season-{season}" if season_query else ""
    episodes = {}
    for page in range(1, 101):
        if "?" in base_url:
            base, query = base_url.split("?", 1)
            query = "?" + query
        else:
            base, query = base_url, ""
        if page == 1:
            url = f"{base}{query}{suffix}"
        else:
            url = f"{base}paged/{page}/{query}{suffix}"
        try:
            html = fetch(url)
        except Exception:  # noqa: BLE001
            break
        before = len(episodes)
        for episode in _episode_links(html, slug, kind):
            episodes.setdefault(episode["url"], episode)
        if page > 1 and len(episodes) == before:
            break
    return list(episodes.values())


def show(ref):
    html = fetch(ref["url"])
    title = _title(page_title(html))
    poster = page_poster(html) or ref.get("poster") or placeholder(title)
    kind = ref.get("data", {}).get("kind", "series")
    slug = ref["url"].rstrip("/").split("/")[-1]
    episodes_url = f"{ref['url'].rstrip('/')}/episodes/"

    if kind == "series":
        listing = fetch(episodes_url)
        seasons = sorted(
            {int(number) for number in re.findall(r"season=season-(\d+)", listing)}
        ) or [1]
        episodes = {}
        for season in seasons:
            for episode in _collect_pages(
                episodes_url, kind, slug, season=season, season_query=True
            ):
                actual_season, number = _season_and_episode(episode["slug"])
                episode["season"] = actual_season or season
                episode["episode"] = number
                if not episode["title"]:
                    episode["title"] = (
                        f"Επεισόδιο {number}" if number else slug_title(episode["slug"])
                    )
                episodes.setdefault(episode["url"], episode)
        result = list(episodes.values())
        result.sort(
            key=lambda episode: (
                episode["season"],
                episode.get("episode") or 0,
                episode["slug"],
            )
        )
    else:
        listing = fetch(episodes_url)
        seasons = sorted({value for value in re.findall(r"season=(\d{4})", listing)})
        if not seasons:
            seasons = [None]
        collected = {}
        for season in seasons:
            base_url = episodes_url
            query = season is not None
            # pass season year through a closure by temporarily monkeypatching _collect_pages base
            if season is None:
                pages = _collect_pages(base_url, kind, slug)
            else:
                pages = _collect_pages(
                    f"{base_url}?season={season}", kind, slug, season=season, season_query=False
                )
            for episode in pages:
                collected.setdefault(episode["url"], episode)
        result = list(collected.values())
        for episode in result:
            date_match = re.search(r"(\d{2})-(\d{2})-(\d{2})/?$", episode["slug"])
            episode["date_key"] = (
                (int(date_match.group(3)), int(date_match.group(2)), int(date_match.group(1)))
                if date_match
                else (99, 99, 99)
            )
            episode["season"] = 1
            episode["episode"] = 0
            if not episode["title"]:
                episode["title"] = slug_title(episode["slug"])
        result.sort(key=lambda episode: (episode.pop("date_key"), episode["slug"]))
        for index, episode in enumerate(result, start=1):
            episode["episode"] = index

    for episode in result:
        episode.pop("slug", None)
    return {"title": title, "poster": poster, "background": poster, "episodes": result}


def stream(episode):
    html = fetch(episode["url"]).replace("\\/", "/")
    match = re.search(r'"embedUrl"\s*:\s*"(https?://[^"]+)"', html)
    if match:
        return match.group(1)
    match = re.search(r'https://[^"\' ]+\.mp4', html)
    if match:
        return match.group(0)
    match = re.search(r'(https?://[^"\' ]+\.m3u8[^"\' ]*)', html)
    if match:
        return match.group(1)
    raise RuntimeError(f"Alpha stream not found for {episode['url']}")
