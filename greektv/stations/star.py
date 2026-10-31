import re

from bs4 import BeautifulSoup

from greektv.common import clean, fetch, page_poster, page_title, placeholder, slug_title

BASE = "https://www.star.gr"
CATEGORIES = ["seires", "psychagogia", "starland", "enimerosi"]
SHOW_PATTERN = re.compile(
    r"^/tv/(seires|psychagogia|starland|enimerosi)/([^/]+)/?$"
)
EPISODE_PATTERN = re.compile(
    r"^/tv/(seires|psychagogia|starland|enimerosi)/([^/]+)/([^/]+?)/?$"
)


def _title(raw):
    title = clean(raw)
    return title or "Star Channel"


def discover():
    shows = {}
    for category in CATEGORIES:
        try:
            html = fetch(f"{BASE}/tv/{category}")
        except Exception:  # noqa: BLE001
            continue
        soup = BeautifulSoup(html, "html.parser")
        for anchor in soup.find_all("a", href=True):
            match = SHOW_PATTERN.match(anchor["href"])
            if not match:
                continue
            slug = match.group(2)
            if slug.startswith("tag_"):
                continue
            url = f"{BASE}/tv/{match.group(1)}/{slug}"
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


def _season_and_episode(slug):
    season = 0
    season_match = re.search(
        r"(\d+)(?:os|i|h|η|ος)[-_ ]?(?:kuklos|kyklos|sezon|κύκλος|σεζόν)", slug
    )
    if not season_match:
        season_match = re.search(r"sezon[-_ ]?(\d+)", slug)
    if season_match:
        season = int(season_match.group(1))

    episode = 0
    episode_match = re.search(r"epeisodio[-_ ]?(\d+)", slug)
    if episode_match:
        episode = int(episode_match.group(1))
    return season, episode


def _date_key(slug, text):
    match = re.match(r"^(\d{2})(\d{2})(\d{4})", slug)
    if match:
        return (int(match.group(3)), int(match.group(2)), int(match.group(1)))
    match = re.search(r"(\d{2})[./-](\d{2})[./-](\d{4})", text)
    if match:
        return (int(match.group(3)), int(match.group(2)), int(match.group(1)))
    return None


def _is_episode(category, slug):
    if category == "seires":
        return "epeisodio" in slug and "trailer" not in slug
    if category == "psychagogia":
        return "epeisodio" in slug or bool(re.match(r"^\d{6,8}-", slug))
    return True


def show(ref):
    html = fetch(ref["url"])
    title = _title(page_title(html))
    poster = page_poster(html) or ref.get("poster") or placeholder(title)

    category, show_slug = ref["url"].rstrip("/").split("/")[-2:]
    pages_to_scan = [html]
    soup = BeautifulSoup(html, "html.parser")
    tag_urls = []
    for anchor in soup.find_all("a", href=True):
        if "tag_" in anchor["href"]:
            tag_urls.append(f"{BASE}{anchor['href']}")
    for tag_url in sorted(set(tag_urls)):
        try:
            tag_html = fetch(tag_url)
        except Exception:  # noqa: BLE001
            continue
        tag_soup = BeautifulSoup(tag_html, "html.parser")
        has_episode = False
        for anchor in tag_soup.find_all("a", href=True):
            match = EPISODE_PATTERN.match(anchor["href"])
            if not match:
                continue
            category = match.group(1)
            episode_slug = match.group(3)
            if episode_slug.startswith("tag_"):
                continue
            if _is_episode(category, episode_slug):
                has_episode = True
                break
        if has_episode:
            pages_to_scan.append(tag_html)

    episodes = {}
    for page_html in pages_to_scan:
        page_soup = BeautifulSoup(page_html, "html.parser")
        for anchor in page_soup.find_all("a", href=True):
            match = EPISODE_PATTERN.match(anchor["href"])
            if not match:
                continue
            category = match.group(1)
            episode_slug = match.group(3)
            if episode_slug.startswith("tag_") or not _is_episode(category, episode_slug):
                continue
            url = f"{BASE}/tv/{category}/{match.group(2)}/{episode_slug}"
            season, number = _season_and_episode(episode_slug)
            anchor_text = clean(anchor.get_text(" "))
            date_key = _date_key(episode_slug, anchor_text)
            if number:
                episode_title = f"Επεισόδιο {number}"
            elif date_key:
                episode_title = f"{date_key[2]:02d}/{date_key[1]:02d}/{date_key[0]}"
            else:
                episode_title = slug_title(episode_slug)
            episodes.setdefault(
                url,
                {
                    "id": episode_slug,
                    "url": url,
                    "title": episode_title,
                    "season": season or 1,
                    "episode": number,
                    "date_key": date_key,
                },
            )

    result = list(episodes.values())
    result.sort(
        key=lambda episode: (
            episode["season"],
            episode.get("episode") or 0,
            episode.get("date_key") or (9999, 12, 31),
        )
    )
    for episode in result:
        episode.pop("date_key", None)
    return {"title": title, "poster": poster, "background": poster, "episodes": result}


def stream(episode):
    html = fetch(episode["url"])
    match = re.search(
        r"https://deliver2\.siliconweb\.com/kwik/star\.m3u8\?key=([A-Za-z0-9]+)",
        html,
    )
    if match:
        return f"https://deliver2.siliconweb.com/kwik/star.m3u8?key={match.group(1)}"
    match = re.search(r'data-video="([^"]+)"', html)
    if match:
        return (
            "https://deliver2.siliconweb.com/kwik/star.m3u8?key="
            + match.group(1)
        )
    match = re.search(r'(https?://[^"\' ]+\.m3u8[^"\' ]*)', html)
    if match:
        return match.group(1)
    raise RuntimeError(f"Star stream not found for {episode['url']}")
