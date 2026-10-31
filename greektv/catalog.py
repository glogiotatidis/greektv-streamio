import hashlib
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from greektv.common import safe_id
from greektv.stations import ORDER, STATIONS

logger = logging.getLogger("greektv")
WORKERS = int(os.environ.get("GREEKTV_WORKERS", "10"))

_refs = None
_refs_lock = threading.Lock()
_loaded = None
_loaded_lock = threading.Lock()
_by_sid = {}
_show_cache = {}
_show_lock = threading.Lock()


def _enabled_stations():
    raw = os.environ.get("GREEKTV_STATIONS", "").strip()
    if not raw:
        return list(ORDER)
    wanted = {part.strip() for part in raw.split(",") if part.strip()}
    return [station for station in ORDER if station in wanted]


def show_id(station, url):
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    return f"greek_tv:{station}:{digest}"


def _discover(station):
    try:
        return station, STATIONS[station]["discover"]()
    except Exception:  # noqa: BLE001
        logger.exception("Discovery failed for %s", station)
        return station, []


def all_refs():
    global _refs
    if _refs is not None:
        return _refs
    with _refs_lock:
        if _refs is not None:
            return _refs
        stations = _enabled_stations()
        workers = max(1, min(WORKERS, len(stations)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_discover, stations))

        refs = []
        for station, items in results:
            logger.info("Discovered %d shows for %s", len(items), station)
            seen = set()
            for ref in items:
                url = ref.get("url")
                if not url or url in seen:
                    continue
                seen.add(url)
                refs.append(
                    {
                        "station": station,
                        "ref": ref,
                        "sid": show_id(station, url),
                    }
                )

        limit = int(os.environ.get("GREEKTV_MAX_SHOWS", "0") or 0)
        if limit:
            refs = refs[:limit]
        _refs = refs
    return _refs


def _normalize_episodes(episodes):
    prepared = []
    for index, raw in enumerate(episodes):
        episode = dict(raw)
        episode["id"] = safe_id(episode.get("id") or index + 1)
        try:
            season = int(episode.get("season") or 1)
        except (TypeError, ValueError):
            season = 1
        try:
            number = int(episode.get("episode") or 0)
        except (TypeError, ValueError):
            number = 0
        episode["season"] = max(1, season)
        episode["_number"] = number
        episode["_index"] = index
        prepared.append(episode)

    prepared.sort(
        key=lambda episode: (
            episode["season"],
            episode["_number"] if episode["_number"] > 0 else 10**9,
            episode["_index"],
        )
    )

    used_numbers = {}
    used_ids = set()
    result = []
    for episode in prepared:
        season = episode["season"]
        number = episode["_number"]
        numbers = used_numbers.setdefault(season, set())
        if number <= 0 or number in numbers:
            number = max(numbers) + 1 if numbers else 1
            while number in numbers:
                number += 1
        numbers.add(number)

        base_id = episode["id"]
        episode_id = base_id
        suffix = 2
        while episode_id in used_ids:
            episode_id = f"{base_id}-{suffix}"
            suffix += 1
        used_ids.add(episode_id)

        episode["id"] = episode_id
        episode["episode"] = number
        episode["title"] = episode.get("title") or f"Επεισόδιο {number}"
        episode.pop("_number", None)
        episode.pop("_index", None)
        result.append(episode)
    return result


def get_show(entry):
    key = (entry["station"], entry["ref"]["url"])
    with _show_lock:
        cached = _show_cache.get(key)
    if cached is not None:
        return cached

    station = entry["station"]
    ref = entry["ref"]
    try:
        data = STATIONS[station]["show"](ref)
    except Exception:  # noqa: BLE001
        logger.exception("Show failed for %s", ref.get("url"))
        data = {
            "title": ref.get("title") or STATIONS[station]["name"],
            "poster": ref.get("poster"),
            "episodes": [],
        }

    data["title"] = data.get("title") or ref.get("title") or STATIONS[station]["name"]
    data["poster"] = data.get("poster") or ref.get("poster") or ""
    data["episodes"] = _normalize_episodes(data.get("episodes") or [])

    with _show_lock:
        _show_cache[key] = data
    return data


def _ensure_loaded():
    global _loaded, _by_sid
    if _loaded is not None:
        return _loaded
    with _loaded_lock:
        if _loaded is not None:
            return _loaded
        refs = all_refs()
        workers = max(1, WORKERS)

        def build(entry):
            return {
                "station": entry["station"],
                "sid": entry["sid"],
                "ref": entry["ref"],
                "show": get_show(entry),
            }

        entries = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(build, entry) for entry in refs]
            for index, future in enumerate(as_completed(futures), start=1):
                entries.append(future.result())
                if index % 25 == 0 or index == len(refs):
                    logger.info("Loaded %d/%d shows", index, len(refs))

        _loaded = [entry for entry in entries if entry["show"].get("episodes")]
        _by_sid = {entry["sid"]: entry for entry in _loaded}
    return _loaded


def all_entries():
    return _ensure_loaded()


def manifest():
    catalogs = [{"type": "series", "id": "greek_tv_all", "name": "Greek TV — All"}]
    for station in _enabled_stations():
        catalogs.append(
            {
                "type": "series",
                "id": f"greek_tv_{station}",
                "name": f"Greek TV — {STATIONS[station]['name']}",
            }
        )
    return {
        "id": "com.greektv.streamio",
        "version": "2.0.0",
        "name": "Greek TV Streamio",
        "description": "On-demand streams from Greek TV stations",
        "resources": ["catalog", "meta", "stream"],
        "types": ["series"],
        "catalogs": catalogs,
        "idPrefixes": ["greek_tv:"],
    }


def catalog(catalog_id):
    entries = _ensure_loaded()
    if catalog_id == "greek_tv_all":
        selected = entries
    elif catalog_id.startswith("greek_tv_"):
        station = catalog_id[len("greek_tv_"):]
        if station not in STATIONS:
            return None
        selected = [entry for entry in entries if entry["station"] == station]
    else:
        return None

    return {
        "metas": [
            {
                "id": entry["sid"],
                "type": "series",
                "name": entry["show"]["title"],
                "poster": entry["show"]["poster"],
            }
            for entry in selected
        ]
    }


def get_meta(sid):
    _ensure_loaded()
    entry = _by_sid.get(sid)
    if not entry:
        return None
    videos = [
        {
            "id": f"{sid}:{episode['id']}",
            "title": episode["title"],
            "season": episode["season"],
            "episode": episode["episode"],
        }
        for episode in entry["show"]["episodes"]
    ]
    return {
        "id": sid,
        "type": "series",
        "name": entry["show"]["title"],
        "poster": entry["show"]["poster"],
        "videos": videos,
    }


def get_streams(item_id):
    _ensure_loaded()
    if ":" not in item_id:
        return []
    sid, episode_id = item_id.rsplit(":", 1)
    entry = _by_sid.get(sid)
    if not entry:
        return []
    episode = next(
        (item for item in entry["show"]["episodes"] if item["id"] == episode_id),
        None,
    )
    if not episode:
        return []
    try:
        url = STATIONS[entry["station"]]["stream"](episode)
    except Exception:  # noqa: BLE001
        logger.exception("Stream failed for %s", item_id)
        return []
    if not url:
        return []
    return [{"title": episode.get("title") or "Stream", "url": url}]
