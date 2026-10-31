import json
import re

from greektv.common import clean, fetch, page_poster, page_title, placeholder, slug_title

BASE = "https://www.skai.gr"
CATEGORIES = ["seires", "psuchagogia", "ntokimanter", "enimerosi", "athlitika"]


def _title(html, fallback):
    match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if match:
        title = clean(re.sub(r"<[^>]+>", " ", match.group(1)))
        if title:
            return title
    title = clean(page_title(html))
    if " | " in title:
        title = title.split(" | ")[-1]
    if title and "σεζόν" not in title.lower():
        return title
    return fallback or "Skai"


def _season_number(season_url, fallback):
    match = re.search(r"(\d+)os-kuklos", season_url)
    if match:
        return int(match.group(1))
    return fallback


def discover():
    groups = {}
    for category in CATEGORIES:
        try:
            html = fetch(f"{BASE}/tv/shows/{category}")
        except Exception:  # noqa: BLE001
            continue
        pattern = rf'href="(/tv/show/{category}/([^"/]+)/([^"/]+))"'
        for match in re.finditer(pattern, html):
            base = f"{BASE}/tv/show/{category}/{match.group(2)}/"
            season_url = f"{BASE}{match.group(1).rstrip('/')}/"
            group = groups.get(base)
            if group is None:
                group = {
                    "url": base,
                    "title": slug_title(match.group(2)),
                    "poster": None,
                    "data": {"seasons": []},
                }
                groups[base] = group
            if season_url not in group["data"]["seasons"]:
                group["data"]["seasons"].append(season_url)
    return list(groups.values())


def _embedded_episodes(html):
    match = re.search(r'"episodes"\s*:\s*(\[)', html)
    if not match:
        return []
    try:
        episodes, _ = json.JSONDecoder().raw_decode(html[match.start(1):])
    except ValueError:
        return []
    result = []
    for episode in episodes:
        link = episode.get("link") or ""
        if link.startswith("/episode/"):
            link = "/tv" + link
        if not link:
            continue
        url = link if link.startswith("http") else BASE + link
        number = int(episode.get("episode_number") or 0)
        result.append(
            {
                "id": url.rstrip("/").split("/")[-1],
                "url": url,
                "title": f"Επεισόδιο {number}" if number else "Επεισόδιο",
                "episode": number,
                "thumbnail": episode.get("img") or "",
            }
        )
    return result


def _ajax_episodes(html):
    result = []
    pattern = r'<a[^>]+href="(/tv/episode/[^"]+)"[^>]*>(.*?)</a>'
    for match in re.finditer(pattern, html, re.S):
        block = match.group(2)
        h3 = re.search(r"<h3[^>]*>(.*?)</h3>", block, re.S)
        title = clean(re.sub(r"<[^>]+>", " ", h3.group(1))) if h3 else ""
        number_match = re.search(r"(\d+)", title)
        number = int(number_match.group(1)) if number_match else 0
        img_match = re.search(r'<img[^>]+src="([^"]+)"', block, re.S)
        thumbnail = img_match.group(1) if img_match else ""
        url = BASE + match.group(1)
        result.append(
            {
                "id": match.group(1).strip("/").split("/")[-1],
                "url": url,
                "title": title or "Επεισόδιο",
                "episode": number,
                "thumbnail": thumbnail,
            }
        )
    return result


def show(ref):
    title = None
    poster = None
    episodes = {}

    seasons = ref.get("data", {}).get("seasons") or []
    for index, season_url in enumerate(seasons):
        try:
            html = fetch(season_url)
        except Exception:  # noqa: BLE001
            continue
        title = title or _title(html, ref.get("title"))
        poster = poster or page_poster(html)
        season = _season_number(season_url, index + 1)

        for episode in _embedded_episodes(html):
            episode["season"] = season
            _add(episodes, episode)

        show_id_match = re.search(r'"show_id"\s*:\s*"?(\d+)', html)
        if show_id_match:
            try:
                ajax_html = fetch(
                    f"{BASE}/tv/ajaxshowsepisode/{show_id_match.group(1)}/0"
                )
            except Exception:  # noqa: BLE001
                ajax_html = ""
            for episode in _ajax_episodes(ajax_html):
                episode["season"] = season
                _add(episodes, episode)

    if title is None:
        title = ref.get("title") or "Skai"
    if poster is None:
        poster = placeholder(title)

    result = list(episodes.values())
    result.sort(key=lambda episode: (episode.get("season", 1), episode.get("episode") or 0))
    return {"title": title, "poster": poster, "episodes": result}


def _add(episodes, episode):
    episodes.setdefault(episode["url"], episode)


def _stream_from_page(html):
    match = re.search(r'"episode"\s*:\s*(\[|\{)', html)
    if not match:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(html[match.start(1):])
    except ValueError:
        return None
    episode = data[0] if isinstance(data, list) else data
    if isinstance(episode, dict):
        return episode.get("media_item_file")
    return None


def stream(episode):
    media_file = _stream_from_page(fetch(episode["url"]))
    if not media_file:
        raise RuntimeError(f"Skai stream not found for {episode['url']}")
    media_file = media_file.lstrip("/")
    return (
        "https://videostream.skai.gr/skaivod/_definst_/mp4:skai/"
        f"{media_file}/chunklist.m3u8"
    )
