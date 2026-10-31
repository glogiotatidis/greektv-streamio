import hashlib
import html as html_lib
import json
import re
import time
import urllib.parse

from bs4 import BeautifulSoup
from curl_cffi import requests

DEFAULT_HEADERS = {
    "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
}
PLACEHOLDER = "https://placehold.co/300x450/png?text="


def fetch(url, **kwargs):
    headers = dict(DEFAULT_HEADERS)
    headers.update(kwargs.pop("headers", {}) or {})
    last = None
    for attempt in range(5):
        try:
            response = requests.get(
                url,
                impersonate="chrome",
                timeout=30,
                headers=headers,
                **kwargs,
            )
            if response.status_code == 404:
                raise RuntimeError(f"HTTP 404 for {url}")
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 0.0
                except (TypeError, ValueError):
                    delay = 0.0
                if delay <= 0:
                    delay = min(30.0, 2.0 ** attempt)
                last = RuntimeError(f"HTTP 429 for {url}")
                if attempt < 4:
                    time.sleep(delay)
                    continue
                raise last
            if response.status_code >= 400:
                raise RuntimeError(f"HTTP {response.status_code} for {url}")
            return response.text
        except RuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < 4:
                time.sleep(min(30.0, 1.0 + 2.0 ** attempt))
    raise last


def fetch_json(url, **kwargs):
    return json.loads(fetch(url, **kwargs))


def clean(value):
    if value is None:
        return ""
    text = html_lib.unescape(str(value))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def text_of(fragment):
    return clean(BeautifulSoup(fragment or "", "html.parser").get_text(" "))


def meta_content(html, prop):
    patterns = [
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']*)["\']',
        rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{re.escape(prop)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html or "", re.I)
        if match:
            return clean(match.group(1))
    return ""


def page_title(html):
    return meta_content(html, "og:title") or text_of(
        (re.search(r"<title[^>]*>(.*?)</title>", html or "", re.S | re.I) or [None, ""])[1]
    )


def page_poster(html):
    return meta_content(html, "og:image") or meta_content(html, "twitter:image")


def slug_title(slug):
    slug = urllib.parse.unquote(slug or "")
    slug = slug.replace("-", " ").replace("_", " ").strip()
    return re.sub(r"\s+", " ", slug).title()


def placeholder(name):
    return PLACEHOLDER + urllib.parse.quote(name or "Greek TV")


def md5(value, length=8):
    return hashlib.md5((value or "").encode("utf-8")).hexdigest()[:length]


def absolute(base, href):
    return urllib.parse.urljoin(base, href)


def safe_id(value):
    value = str(value or "")
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-.")
    return value or md5(value, 10)


def int_or(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


