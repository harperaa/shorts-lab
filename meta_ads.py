"""Meta Ad Library client — distilled from the ad-builder kit's
pull-competitor-ads.py (Kruse Media LLC / AI Cyber Sherpas LLC, MIT).

Endpoints (Graph API ads_archive):
- search by page name/terms  -> discover competitor pages
- search_page_ids            -> pull a monitored page's ads
- sort_by=longest_running    -> surface the proven winners

Requires META_ACCESS_TOKEN (Ad Library access). stdlib urllib only.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

try:
    from . import store
except ImportError:  # loaded outside package context
    import store  # type: ignore

API_VERSION = os.environ.get("META_API_VERSION", "v23.0")
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

ARCHIVE_FIELDS = ("id,ad_delivery_start_time,ad_delivery_stop_time,"
                  "ad_snapshot_url,page_id,page_name,publisher_platforms")


def _get_token() -> str:
    tok = (os.environ.get("META_ACCESS_TOKEN") or "").strip()
    if not tok:
        env_path = store._home() / ".env"
        try:
            for line in env_path.read_text().splitlines():
                if line.strip().startswith("META_ACCESS_TOKEN="):
                    tok = line.split("=", 1)[1].strip()
                    break
        except OSError:
            pass
    if not tok:
        raise RuntimeError("META_ACCESS_TOKEN not set — add it on the Keys "
                           "page (Graph API token with Ad Library access)")
    return tok


def _get(url: str, params: Optional[dict] = None,
         retries: int = 3) -> dict[str, Any]:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 and attempt < retries - 1:
                time.sleep(int(exc.headers.get("Retry-After", 30)))
                continue
            if exc.code >= 500 and attempt < retries - 1:
                time.sleep(5)
                continue
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"error": {"message": f"HTTP {exc.code}: {body[:200]}"}}
    return {"error": {"message": "retries exhausted"}}


def _dates(days: int = 365) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return ((now - timedelta(days=days)).strftime("%Y-%m-%d"),
            (now - timedelta(days=1)).strftime("%Y-%m-%d"))


def _parse_day(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")) \
            .timestamp()
    except ValueError:
        try:
            return datetime.strptime(str(s)[:10], "%Y-%m-%d") \
                .replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            return None


def search_pages(term: str, countries: str = "US",
                 days: int = 365) -> list[dict]:
    """Discover competitor pages by searching the Ad Library for a term.
    Returns [{pageId, name, adCount}] ranked by ad volume."""
    token = _get_token()
    date_min, date_max = _dates(days)
    data = _get(f"{BASE_URL}/ads_archive", {
        "access_token": token,
        "search_terms": term,
        "ad_reached_countries": countries,
        "ad_delivery_date_min": date_min,
        "ad_delivery_date_max": date_max,
        "ad_active_status": "ALL",
        "fields": "page_id,page_name",
        "limit": 100,
    })
    if "error" in data:
        raise RuntimeError(f"Meta Ad Library: "
                           f"{data['error'].get('message', 'API error')}")
    ads = data.get("data", [])
    counts = Counter(a.get("page_id") for a in ads if a.get("page_id"))
    names = {a.get("page_id"): a.get("page_name") for a in ads}
    return [{"pageId": pid, "name": names.get(pid) or pid, "adCount": n}
            for pid, n in counts.most_common(20)]


def pull_page_ads(page_id: str, countries: str = "US", days: int = 365,
                  limit: int = 50,
                  sort_by: str = "longest_running") -> tuple[list[dict], int]:
    """Pull a monitored page's ads (longest-running first by default).
    Upserts into the store; returns (ads, new_count)."""
    token = _get_token()
    date_min, date_max = _dates(days)
    params: Optional[dict] = {
        "access_token": token,
        "search_page_ids": str(page_id),
        "ad_reached_countries": countries,
        "ad_delivery_date_min": date_min,
        "ad_delivery_date_max": date_max,
        "ad_active_status": "ALL",
        "sort_by": sort_by,
        "fields": ARCHIVE_FIELDS,
        "limit": min(limit, 100),
    }
    url = f"{BASE_URL}/ads_archive"
    all_ads: list[dict] = []
    seen: set[str] = set()
    while True:
        data = _get(url, params)
        if "error" in data:
            raise RuntimeError(f"Meta Ad Library: "
                               f"{data['error'].get('message', 'API error')}")
        for ad in data.get("data", []):
            if ad.get("id") and ad["id"] not in seen:
                seen.add(ad["id"])
                all_ads.append(ad)
        next_url = (data.get("paging") or {}).get("next")
        if not next_url or len(all_ads) >= limit:
            break
        url, params = next_url, None

    new = 0
    page_name = ""
    for ad in all_ads[:limit]:
        page_name = ad.get("page_name") or page_name
        started = _parse_day(ad.get("ad_delivery_start_time"))
        stopped = _parse_day(ad.get("ad_delivery_stop_time"))
        created = store.upsert_ad(
            ad["id"], str(ad.get("page_id") or page_id),
            ad.get("page_name") or "", ad.get("ad_snapshot_url") or "",
            started, stopped, stopped is None,
            ad.get("publisher_platforms") or [])
        new += 1 if created else 0
    if page_name:
        store.add_ad_page(str(page_id), page_name)
    return all_ads[:limit], new


def sync_all_pages(countries: str = "US") -> dict:
    """Refresh ads for every monitored page."""
    pages = store.list_ad_pages()
    summary = {"pages": len(pages), "ads": 0, "new": 0, "errors": []}
    for p in pages:
        try:
            ads, new = pull_page_ads(p["page_id"], countries=countries)
            summary["ads"] += len(ads)
            summary["new"] += new
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append(f"{p.get('name') or p['page_id']}: "
                                     f"{str(exc)[:150]}")
    store.kv_set("adsFetch", {"at": time.time(), "summary": summary})
    return summary


_ALLOWED_KEYS = {"META_ACCESS_TOKEN", "KIE_API_KEY", "TRANSCRIPT_API_KEY"}


def store_key(env_var: str, value: str) -> None:
    """Persist a key into $HERMES_HOME/.env (replace-not-duplicate) and the
    process env so it applies without a restart. Same pattern delivery-kit
    uses for provider keys."""
    value = (value or "").strip()
    if not value or "\n" in value:
        raise ValueError("key must be a single non-empty line")
    if env_var not in _ALLOWED_KEYS:
        raise ValueError(f"unknown env var: {env_var}")
    path = store._home() / ".env"
    lines = []
    try:
        lines = [l for l in path.read_text().splitlines()
                 if not l.strip().startswith(env_var + "=")]
    except FileNotFoundError:
        pass
    lines.append(f"{env_var}={value}")
    tmp = path.with_suffix(".sl-tmp")
    tmp.write_text("\n".join(lines) + "\n")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.environ[env_var] = value


def validate_token(token: str) -> dict:
    """Sanity-check a Meta token with the cheapest call there is (/me).
    Returns {"ok": True, "name": ...} or {"ok": False, "error": ...}."""
    data = _get(f"{BASE_URL}/me", {"access_token": (token or "").strip(),
                                   "fields": "id,name"})
    if "error" in data:
        return {"ok": False,
                "error": str(data["error"].get("message", "invalid token"))[:200]}
    return {"ok": True, "name": data.get("name") or data.get("id") or ""}
