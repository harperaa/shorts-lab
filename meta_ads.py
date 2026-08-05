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


def _rank_pages(counts: Counter, names: dict, term: str) -> list:
    """Name matches beat ad volume — a keyword search matches ad TEXT, so
    high-volume pages that merely mention the words would otherwise drown
    out the advertiser actually named that (same heuristic as the kit's
    resolve_via_search)."""
    import re as _re
    t = term.lower().strip()
    words = [w for w in _re.split(r"[^a-z0-9]+", t) if len(w) > 2]

    def score(pid):
        name = (names.get(pid) or "").lower()
        exact = 2 if name == t else 0
        allw = 1 if words and all(w in name for w in words) else 0
        return (exact + allw, counts[pid])

    ordered = sorted(counts, key=score, reverse=True)
    return [{"pageId": pid, "name": names.get(pid) or pid,
             "adCount": counts[pid],
             "nameMatch": score(pid)[0] > 0} for pid in ordered[:20]]


def search_pages(term: str, countries: str = "US",
                 days: int = 365) -> list[dict]:
    """Discover competitor pages by searching the Ad Library for a term.
    Returns [{pageId, name, adCount}] ranked by ad volume."""
    token = _get_token()
    date_min, date_max = _dates(days)
    data = _get(f"{BASE_URL}/ads_archive", {
        "access_token": token,
        "search_terms": term,
        "search_type": ("KEYWORD_EXACT_PHRASE" if " " in term.strip()
                        else "KEYWORD_UNORDERED"),
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
    return _rank_pages(counts, names, term)


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
        "ad_active_status": "ACTIVE",
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
    """Refresh ads for every monitored page via the selected backend."""
    pages = store.list_ad_pages()
    summary = {"pages": len(pages), "ads": 0, "new": 0, "errors": [],
               "source": get_ads_source()}
    for p in pages:
        try:
            ads, new = pull_page_ads_any(p["page_id"])
            summary["ads"] += len(ads)
            summary["new"] += new
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append(f"{p.get('name') or p['page_id']}: "
                                     f"{str(exc)[:150]}")
    store.kv_set("adsFetch", {"at": time.time(), "summary": summary})
    return summary


_ALLOWED_KEYS = {"META_ACCESS_TOKEN", "KIE_API_KEY", "TRANSCRIPT_API_KEY",
                 "APIFY_API_TOKEN"}


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


# ---------------------------------------------------------------------------
# Apify backend — scrape the PUBLIC Ad Library via the official Apify actor
# (apify/facebook-ads-scraper). No Meta account, no app review: an Apify
# token is a 2-minute signup. Verified 2026-08: input takes startUrls of
# Ad Library pages; output items carry adArchiveID/startDate/endDate/
# isActive/publisherPlatform/pageName.
# ---------------------------------------------------------------------------

APIFY_ACTOR = "apify~facebook-ads-scraper"


def _apify_token() -> str:
    import os as _os
    tok = (_os.environ.get("APIFY_API_TOKEN") or "").strip()
    if not tok:
        try:
            for line in (store._home() / ".env").read_text().splitlines():
                if line.strip().startswith("APIFY_API_TOKEN="):
                    tok = line.split("=", 1)[1].strip()
                    break
        except OSError:
            pass
    if not tok:
        raise RuntimeError("APIFY_API_TOKEN not set — hit Connect Apify")
    return tok


def validate_apify_token(token: str) -> dict:
    """Cheapest sanity check: GET /v2/users/me."""
    url = ("https://api.apify.com/v2/users/me?token="
           + urllib.parse.quote((token or "").strip()))
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        u = (data.get("data") or {})
        if u.get("username") or u.get("id"):
            return {"ok": True, "name": u.get("username") or u.get("id")}
        return {"ok": False, "error": "unexpected response"}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"HTTP {exc.code} — token rejected"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:150]}


def _parse_any_date(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):        # actor sometimes emits unix secs
        return float(v) if v > 10_000 else None
    return _parse_day(str(v))


def _extract_creative(it: dict) -> dict:
    """Pull the displayable creative out of the actor's snapshot blob —
    body text, title, CTA, media image, page avatar — defensively across
    the shapes the actor emits (snapshot.body.text, cards[], images[],
    videos[])."""
    snap = it.get("snapshot") or {}
    if not isinstance(snap, dict):
        snap = {}
    cards = snap.get("cards") or []
    card0 = cards[0] if cards and isinstance(cards[0], dict) else {}

    def pick(obj, *keys):
        # the actor emits camelCase in practice; its docs show snake_case —
        # accept both (verified against a live run, 2026-08-05)
        for k in keys:
            v = obj.get(k)
            if v:
                return v
        return ""

    body = snap.get("body")
    if isinstance(body, dict):
        body = body.get("text")
    body = body or card0.get("body") or ""
    if isinstance(body, dict):
        body = body.get("text") or ""

    image = ""
    video = False
    video_url = ""
    for vid in (snap.get("videos") or []):
        if isinstance(vid, dict):
            video_url = pick(vid, "videoSdUrl", "video_sd_url",
                             "videoHdUrl", "video_hd_url")
            if video_url:
                break
    if not video_url:
        video_url = pick(card0, "videoSdUrl", "video_sd_url",
                         "videoHdUrl", "video_hd_url")
    for img in (snap.get("images") or []):
        if isinstance(img, dict):
            image = pick(img, "originalImageUrl", "original_image_url",
                         "resizedImageUrl", "resized_image_url")
            if image:
                break
    if not image:
        for vid in (snap.get("videos") or []):
            if isinstance(vid, dict):
                image = pick(vid, "videoPreviewImageUrl",
                             "video_preview_image_url")
                if image:
                    video = True
                    break
    if not image:
        image = pick(card0, "originalImageUrl", "original_image_url",
                     "resizedImageUrl", "resized_image_url")
        if not image:
            image = pick(card0, "videoPreviewImageUrl",
                         "video_preview_image_url")
            video = bool(image)

    return {
        "body": str(body or "")[:2000],
        "title": str(pick(snap, "title") or pick(card0, "title"))[:200],
        "cta": str(pick(snap, "ctaText", "cta_text")
                   or pick(card0, "ctaText", "cta_text"))[:60],
        "image": str(image or "")[:1000],
        "video": video or bool(video_url),
        "videoUrl": str(video_url or "")[:1500],
        "profile": str(pick(snap, "pageProfilePictureUrl",
                            "page_profile_picture_url"))[:1000],
        "link": str(pick(snap, "linkUrl", "link_url")
                    or pick(card0, "linkUrl", "link_url"))[:600],
    }


def apify_pull_page_ads(page_id: str, limit: int = 50) -> tuple[list, int]:
    """Run the actor synchronously for one page's Ad Library URL and
    upsert the results. Sync runs take ~30-120s."""
    token = _apify_token()
    lib_url = ("https://www.facebook.com/ads/library/?active_status=active"
               "&ad_type=all&country=US&search_type=page"
               f"&view_all_page_id={page_id}")
    body = json.dumps({
        "startUrls": [{"url": lib_url}],
        "resultsLimit": min(limit, 100),
        "activeStatus": "active",
    }).encode()
    url = (f"https://api.apify.com/v2/acts/{APIFY_ACTOR}"
           "/run-sync-get-dataset-items?token="
           + urllib.parse.quote(token) + "&timeout=240")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=280) as resp:
            items = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"Apify run failed (HTTP {exc.code}): {detail}")
    if not isinstance(items, list):
        raise RuntimeError(f"Apify returned no dataset: {str(items)[:200]}")

    new = 0
    page_name = ""
    for it in items[:limit]:
        aid = str(it.get("adArchiveID") or it.get("adArchiveId")
                  or it.get("ad_archive_id") or "")
        if not aid:
            continue
        page_name = it.get("pageName") or page_name
        started = _parse_any_date(it.get("startDate")
                                  or it.get("startDateFormatted"))
        stopped = _parse_any_date(it.get("endDate")
                                  or it.get("endDateFormatted"))
        active = bool(it.get("isActive"))
        if active:
            stopped = None
        created = store.upsert_ad(
            aid, str(it.get("pageID") or it.get("pageId") or page_id),
            it.get("pageName") or "",
            f"https://www.facebook.com/ads/library/?id={aid}",
            started, stopped, active,
            it.get("publisherPlatform") or it.get("publisherPlatforms") or [],
            creative=_extract_creative(it))
        new += 1 if created else 0
    if page_name:
        store.add_ad_page(str(page_id), page_name)
    return items[:limit], new


def apify_search_pages(term: str, limit: int = 50) -> list:
    """Discover competitor pages by running the actor against an Ad
    Library KEYWORD-SEARCH URL (the actor's docs accept search URLs as
    startUrls). Aggregates results into the same page ranking the Meta
    search returns. Sync runs take ~30-120s."""
    token = _apify_token()
    # multi-word queries use exact-phrase — the library matches advertiser
    # names too, and exact phrase keeps "AI Cyber Value Creator" from being
    # buried under every page whose ads merely say "creator"
    stype = ("keyword_exact_phrase" if " " in term.strip()
             else "keyword_unordered")
    search_url = ("https://www.facebook.com/ads/library/?active_status=all"
                  "&ad_type=all&country=US&q="
                  + urllib.parse.quote(term.strip())
                  + f"&search_type={stype}")
    body = json.dumps({"startUrls": [{"url": search_url}],
                       "resultsLimit": min(max(limit, 100), 200)}).encode()
    url = (f"https://api.apify.com/v2/acts/{APIFY_ACTOR}"
           "/run-sync-get-dataset-items?token="
           + urllib.parse.quote(token) + "&timeout=240")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=280) as resp:
            items = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"Apify search failed (HTTP {exc.code}): {detail}")
    if not isinstance(items, list):
        raise RuntimeError(f"Apify returned no dataset: {str(items)[:200]}")
    counts = Counter()
    names = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        pid = str(it.get("pageID") or it.get("pageId") or "")
        if not pid:
            continue
        counts[pid] += 1
        names.setdefault(pid, it.get("pageName") or pid)
    return _rank_pages(counts, names, term)


def search_pages_any(term: str) -> list:
    src = get_ads_source()
    if src == "apify":
        return apify_search_pages(term)
    if src == "meta":
        return search_pages(term)
    raise RuntimeError("connect Apify or Meta first")


def get_ads_source() -> str:
    """Which backend pulls ads: explicit choice, else whichever key exists
    (apify preferred — it's the low-friction path)."""
    import os as _os
    choice = store.kv_get("adsSource")
    def _has(var):
        if (_os.environ.get(var) or "").strip():
            return True
        try:
            for line in (store._home() / ".env").read_text().splitlines():
                if line.strip().startswith(var + "=") and                         line.split("=", 1)[1].strip():
                    return True
        except OSError:
            pass
        return False
    if choice in ("meta", "apify"):
        return choice
    if _has("APIFY_API_TOKEN"):
        return "apify"
    if _has("META_ACCESS_TOKEN"):
        return "meta"
    return "none"


def set_ads_source(source: str) -> None:
    if source not in ("meta", "apify"):
        raise ValueError("source must be meta or apify")
    store.kv_set("adsSource", source)


def pull_page_ads_any(page_id: str, limit: int = 50):
    src = get_ads_source()
    if src == "apify":
        return apify_pull_page_ads(page_id, limit=limit)
    if src == "meta":
        return pull_page_ads(page_id, limit=limit)
    raise RuntimeError("connect Apify or Meta first")
