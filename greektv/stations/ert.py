from curl_cffi import requests
from greektv.common import clean, fetch_json, placeholder, slug_title

BASE = "https://api.app.ertflix.gr"
LIMIT = 100


def discover():
    shows = {}
    try:
        first = fetch_json(
            f"{BASE}/v2/Tile/FilterTiles",
            params={
                "platformCodename": "www",
                "limit": LIMIT,
                "page": 1,
                "tileTypes": "ser",
            },
        )
    except Exception:  # noqa: BLE001
        return []

    total_pages = (first.get("Pagination") or {}).get("TotalPages") or 1
    pages = [first]
    for page in range(2, total_pages + 1):
        try:
            pages.append(
                fetch_json(
                    f"{BASE}/v2/Tile/FilterTiles",
                    params={
                        "platformCodename": "www",
                        "limit": LIMIT,
                        "page": page,
                        "tileTypes": "ser",
                    },
                )
            )
        except Exception:  # noqa: BLE001
            continue

    for payload in pages:
        for tile in payload.get("Tiles") or []:
            series_id = tile.get("Id")
            if not series_id or series_id in shows:
                continue
            codename = tile.get("Codename") or series_id
            shows[series_id] = {
                "url": f"https://www.ertflix.gr/series/{series_id}",
                "title": slug_title(codename),
                "poster": None,
                "data": {"id": series_id},
            }
    return list(shows.values())


def _poster(images):
    if not images:
        return None
    for role in ("poster", "photo"):
        for image in images:
            if image.get("Role") == role and image.get("IsMain"):
                return image.get("Url")
    for role in ("poster", "photo", "photo-details", "hbbtv-icon"):
        for image in images:
            if image.get("Role") == role:
                return image.get("Url")
    return images[0].get("Url")


def show(ref):
    series_id = ref["data"]["id"]
    details = fetch_json(
        f"{BASE}/v1/Tile/GetSeriesDetails",
        params={"platformCodename": "www", "id": series_id},
    )
    series = details.get("Series") or {}
    title = clean(series.get("Title")) or ref.get("title") or "ERT"
    images = series.get("Images") or []
    poster = _poster(images) or ref.get("poster") or placeholder(title)
    background = None
    for image in images:
        if image.get("Role") in ("hbbtv-background", "photo-details"):
            background = image.get("Url")
            break
    if not background:
        background = poster

    episodes = []
    for index, group in enumerate(details.get("EpisodeGroups") or []):
        season = group.get("SeasonNumber") or index + 1
        for position, episode in enumerate(group.get("Episodes") or []):
            codename = episode.get("Codename")
            if not codename:
                continue
            number = episode.get("EpisodeNumber") or position + 1
            episode_title = (
                clean(episode.get("Subtitle"))
                or clean(episode.get("Title"))
                or f"Επεισόδιο {number}"
            )
            image_url = ""
            image = episode.get("Image")
            if isinstance(image, dict):
                image_url = image.get("Url") or ""
            episodes.append(
                {
                    "id": codename,
                    "url": ref["url"],
                    "title": episode_title,
                    "season": season,
                    "episode": number,
                    "thumbnail": image_url,
                    "extra": {"codename": codename},
                }
            )

    episodes.sort(key=lambda episode: (episode["season"], episode.get("episode") or 0))
    return {"title": title, "poster": poster, "background": background, "episodes": episodes}


def _pick_media_file(media_files):
    if not media_files:
        return None
    for media_file in media_files:
        role = (media_file.get("RoleName") or "").lower()
        codename = (media_file.get("RoleCodename") or "").lower()
        if role == "main" or codename == "main":
            return media_file
    return media_files[0]


def _pick_format(media_file):
    formats = media_file.get("Formats") or []
    for fmt in formats:
        if ".m3u8" in (fmt.get("Url") or "").lower() or fmt.get("Type") == 2:
            return fmt.get("Url")
    for fmt in formats:
        if fmt.get("Url"):
            return fmt.get("Url")
    return None


def stream(episode):
    codename = episode.get("extra", {}).get("codename")
    if not codename:
        raise RuntimeError("ERT episode without codename")
    payload = fetch_json(
        f"{BASE}/v1/Player/AcquireContent",
        params={"platformCodename": "www", "codename": codename},
    )
    if not (payload.get("Result") or {}).get("Success"):
        raise RuntimeError(f"ERT acquire failed for {codename}")
    media_file = _pick_media_file(payload.get("MediaFiles"))
    if not media_file:
        raise RuntimeError(f"ERT no media files for {codename}")
    url = _pick_format(media_file)
    if not url:
        raise RuntimeError(f"ERT no playable format for {codename}")
    lower = url.lower()
    if ".m3u8" not in lower and not lower.endswith((".mp4", ".mpd")):
        url = url.rstrip("/") + "/index.m3u8"
    # Resolve redirects to the final playable host.
    try:
        response = requests.get(url, impersonate="chrome", timeout=20, allow_redirects=True, stream=True)
        response.close()
        if response.status_code < 400 and response.url:
            url = response.url
    except Exception:  # noqa: BLE001
        pass
    return url
