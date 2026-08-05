"""transcriptapi.com client — Shorts edition.

Same API youtube-insights uses (channel/latest + transcript endpoints, Bearer
TRANSCRIPT_API_KEY, curl UA for Cloudflare), but the filter is INVERTED:
youtube-insights skips Shorts; Shorts Lab keeps ONLY them — a "/shorts/"
link, or a transcript running under 120 seconds.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

try:
    from . import store
except ImportError:  # loaded outside package context (tests, tooling)
    import store  # type: ignore

API_BASE = os.environ.get("YTI_API_BASE", "https://transcriptapi.com/api/v2")
LOOKBACK_DAYS = 30
SHORT_MAX_SECONDS = 120


def _get_key() -> str:
    key = (os.environ.get("TRANSCRIPT_API_KEY") or "").strip()
    if not key:
        # fall back to the shared ~/.hermes/.env the Keys page writes
        env_path = store._home() / ".env"
        try:
            for line in env_path.read_text().splitlines():
                if line.strip().startswith("TRANSCRIPT_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
        except OSError:
            pass
    if not key:
        raise RuntimeError("TRANSCRIPT_API_KEY not set — add it on the Keys "
                           "page (shared with YouTube Insights)")
    return key


def _http_get(url: str, headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    # transcriptapi.com sits behind Cloudflare, which rejects Python-urllib's
    # default signature; a curl-style UA passes (same as youtube-insights).
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.4.0",
                                               **headers})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    try:
        return status, json.loads(body)
    except json.JSONDecodeError:
        return status, {"error": f"non-JSON response: {body[:200]}"}


def channel_latest_url(channel: str) -> str:
    return f"{API_BASE}/youtube/channel/latest?channel={urllib.parse.quote(channel)}"


def transcript_url(video_id: str) -> str:
    return (f"{API_BASE}/youtube/transcript?video_url={urllib.parse.quote(video_id)}"
            f"&format=json&include_timestamp=true&send_metadata=true")


def _parse_published(published: str) -> Optional[float]:
    try:
        s = published.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, AttributeError):
        return None


def fetch_shorts(lookback_days: int = LOOKBACK_DAYS,
                 http_get: Optional[Callable] = None,
                 sleep: Callable[[float], None] = time.sleep) -> dict:
    """Pull recent Shorts for every monitored competitor channel."""
    http_get = http_get or _http_get
    key = _get_key()
    headers = {"Authorization": f"Bearer {key}"}
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=lookback_days)).timestamp()

    channels = store.list_channels()
    summary = {"channels": len(channels), "seen": 0, "shorts": 0,
               "new": 0, "transcribed": 0, "errors": []}
    if not channels:
        summary["errors"].append(
            "no competitor channels tracked — add one below")
        return summary

    for channel in channels:
        status, data = http_get(channel_latest_url(channel), headers)
        results = data.get("results")
        if data.get("error") or not isinstance(results, list):
            msg = f"channel {channel} failed (HTTP {status}): " \
                  f"{data.get('error') or json.dumps(data)[:150]}"
            if status in (401, 403):
                msg += " — key rejected; re-check TRANSCRIPT_API_KEY"
            summary["errors"].append(msg)
            continue

        for video in results:
            vid = str(video.get("videoId") or video.get("video_id") or "")
            link = str(video.get("link") or "")
            published = _parse_published(str(video.get("published") or ""))
            if not vid:
                continue
            summary["seen"] += 1
            is_shorts_link = "/shorts/" in link
            if published is not None and published < cutoff:
                continue

            transcript = ""
            duration: Optional[float] = None
            # transcript decides duration; for /shorts/ links we want it
            # anyway (it feeds the analysis), for others it's the only way
            # to detect an unlabeled short
            t_status, t_data = http_get(transcript_url(vid), headers)
            if not t_data.get("error") and t_status < 400:
                segs = t_data.get("transcript") or []
                if segs:
                    last = segs[-1]
                    duration = float(last.get("start") or 0) + \
                        float(last.get("duration") or 0)
                    transcript = " ".join(
                        str(s.get("text") or "") for s in segs).strip()

            is_short = is_shorts_link or (
                duration is not None and duration < SHORT_MAX_SECONDS)
            if not is_short:
                continue

            summary["shorts"] += 1
            created = store.upsert_short(
                vid, channel, str(video.get("title") or "untitled"),
                link or f"https://www.youtube.com/shorts/{vid}",
                published, duration, int(video.get("viewCount") or 0),
                f"https://i.ytimg.com/vi/{vid}/oardefault.jpg",
                transcript)
            summary["new"] += 1 if created else 0
            summary["transcribed"] += 1 if transcript else 0
        sleep(0.5)

    store.kv_set("shortsFetch", {"at": time.time(), "summary": summary})
    return summary
