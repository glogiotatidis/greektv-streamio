import re

from greektv.common import clean, fetch, page_poster, page_title, placeholder, slug_title, text_of

BASE = "https://www.megatv.com"
CATEGORIES = [
    "entertainment",
    "flashback",
    "greekseries",
    "megasports",
    "news",
    "ntokimanter",
    "paidika",
    "pemptousia",
]


def _title(raw):
    title = clean(raw)
    if title.endswith("| MEGA TV"):
        title = title[: -len("| MEGA TV")].strip()
    return title or "Mega TV"


def discover():
    shows = {}
    for category in CATEGORIES:
        try:
            html = fetch(f"{BASE}/showtype/{category}/")
        except Exception:  # noqa: BLE001
            continue
        for match in re.finditer(
            r'href="(https://www\.megatv\.com/ekpompes/(\d+)/([^"/]+)/)"', html
        ):
            url = match.group(1)
            if url in shows:
                continue
            shows[url] = {
                "url": url,
                "title": slug_title(match.group(3)),
                "poster": None,
                "data": {"id": match.group(2)},
            }
    return list(shows.values())


def _episode_links(html):
    found = {}
    for match in re.finditer(
        r'<a[^>]+href="(https://www\.megatv\.com/(?:tvshows|gtvshows)/(\d+)/([^"/]+)/)"[^>]*>(.*?)</a>',
        html,
        re.S,
    ):
        url = match.group(1)
        slug = match.group(3)
        anchor = text_of(match.group(4))
        number_match = re.search(r"[Εε]πεισ[οό]διο\s*(\d+)", anchor)
        if not number_match:
            number_match = re.search(r"epeisodio-(\d+)", slug)
        number = int(number_match.group(1)) if number_match else 0

        date_match = re.search(r"(\d{2})-(\d{2})-(\d{4})$", slug)
        date_key = (
            (int(date_match.group(3)), int(date_match.group(2)), int(date_match.group(1)))
            if date_match
            else None
        )

        title = anchor if anchor and anchor.lower() != "view more" else ""
        if not title or title.lower() == "view more":
            title = f"Επεισόδιο {number}" if number else slug_title(slug)
        current = found.get(url)
        if current is None or (not current.get("anchor") and anchor):
            found[url] = {
                "id": slug,
                "url": url,
                "title": title,
                "episode": number,
                "date_key": date_key,
                "anchor": bool(anchor and anchor.lower() != "view more"),
            }
    return list(found.values())


def show(ref):
    html = fetch(ref["url"])
    title = _title(page_title(html))
    poster = page_poster(html) or ref.get("poster") or placeholder(title)

    episodes = []
    internal = re.search(r"/episodes\?id=([a-z]\d+)&type=(tvshows|gtvshows)", html)
    if internal:
        show_id, show_type = internal.group(1), internal.group(2)
        seen = {}
        for page in range(1, 101):
            if page == 1:
                url = f"{BASE}/episodes?id={show_id}&type={show_type}"
            else:
                url = f"{BASE}/episodes/page/{page}/?id={show_id}&type={show_type}"
            try:
                page_html = fetch(url)
            except Exception:  # noqa: BLE001
                break
            before = len(seen)
            for episode in _episode_links(page_html):
                seen.setdefault(episode["url"], episode)
            if page > 1 and len(seen) == before:
                break
        episodes = list(seen.values())

    if not episodes:
        episodes = _episode_links(html)

    def sort_key(item):
        index, episode = item
        if episode.get("date_key"):
            return (0,) + episode["date_key"]
        if episode.get("episode"):
            return (1, episode["episode"])
        return (2, index)

    episodes = [
        episode
        for _, episode in sorted(enumerate(episodes), key=sort_key)
    ]
    for episode in episodes:
        episode.pop("anchor", None)
        episode.pop("date_key", None)

    return {"title": title, "poster": poster, "episodes": episodes}


def stream(episode):
    html = fetch(episode["url"])
    match = re.search(r'data-kwik_source="([^"]+)"', html)
    if match:
        return match.group(1)
    match = re.search(r'(https?://[^"\' ]+\.m3u8[^"\' ]*)', html)
    if match:
        return match.group(1)
    raise RuntimeError(f"Mega stream not found for {episode['url']}")
