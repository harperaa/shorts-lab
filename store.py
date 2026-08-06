"""shorts-lab storage.

Two databases:

1. Our own sqlite at <HERMES_HOME>/plugins-data/shorts-lab/data.db — shorts,
   Meta ad pages/ads, creations, and cached analyses.
2. The YouTube Insights db at plugins-data/youtube-insights/data.db, where
   the COMPETITOR CHANNEL LIST lives. Shorts Lab reads and writes that same
   ``channels`` table (identical DDL + normalization), so adding or removing
   a competitor on either page reflects on both — one source of truth, no
   sync job.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _home() -> Path:
    val = (os.environ.get("HERMES_HOME") or "").strip()
    return Path(val).expanduser() if val else Path.home() / ".hermes"


def data_dir() -> Path:
    d = _home() / "plugins-data" / "shorts-lab"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / "data.db"


def assets_dir() -> Path:
    d = data_dir() / "assets"
    d.mkdir(parents=True, exist_ok=True)
    return d


_SCHEMA = """
CREATE TABLE IF NOT EXISTS shorts (
    video_id TEXT PRIMARY KEY,
    channel TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    link TEXT NOT NULL DEFAULT '',
    published REAL,
    duration_seconds REAL,
    view_count INTEGER NOT NULL DEFAULT 0,
    thumbnail TEXT NOT NULL DEFAULT '',
    transcript TEXT NOT NULL DEFAULT '',
    fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ad_pages (
    page_id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    added_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ads (
    archive_id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL,
    page_name TEXT NOT NULL DEFAULT '',
    snapshot_url TEXT NOT NULL DEFAULT '',
    started REAL,
    stopped REAL,
    active INTEGER NOT NULL DEFAULT 0,
    platforms TEXT NOT NULL DEFAULT '[]',
    pulled_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS creations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,                 -- 'short-script' | 'image-ad' | 'video'
    title TEXT NOT NULL DEFAULT '',
    brief TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',   -- script/prompt markdown
    status TEXT NOT NULL DEFAULT 'ready',   -- draft|generating|ready|failed
    task_id TEXT,
    result_url TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '{}',  -- json: refs, style ad, assets
    error TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    # migration: creative payload (body/image/cta from the Apify snapshot)
    try:
        conn.execute("ALTER TABLE ads ADD COLUMN creative TEXT "
                     "NOT NULL DEFAULT '{}'")
    except sqlite3.OperationalError:
        pass          # column already exists
    return conn


# ---------------------------------------------------------------------------
# Shared competitor list (YouTube Insights' channels table)
# ---------------------------------------------------------------------------

def yti_db_path() -> Path:
    d = _home() / "plugins-data" / "youtube-insights"
    d.mkdir(parents=True, exist_ok=True)
    return d / "data.db"


def normalize_handle(handle: str) -> str:
    # identical to youtube-insights' yti_store.normalize_handle
    h = (handle or "").strip()
    return h if h.startswith("@") else f"@{h}" if h else ""


def _yti_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(yti_db_path())
    conn.row_factory = sqlite3.Row
    # same DDL youtube-insights uses, so whichever plugin runs first wins
    conn.execute("CREATE TABLE IF NOT EXISTS channels ("
                 "handle TEXT PRIMARY KEY, added_at TEXT NOT NULL)")
    return conn


def list_channels() -> list[str]:
    conn = _yti_conn()
    try:
        rows = conn.execute(
            "SELECT handle FROM channels ORDER BY added_at").fetchall()
        return [r["handle"] for r in rows]
    finally:
        conn.close()


def add_channel(handle: str) -> list[str]:
    h = normalize_handle(handle)
    if not h:
        raise ValueError("handle required")
    conn = _yti_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO channels(handle, added_at) VALUES (?, ?)",
            (h, datetime.now(timezone.utc).isoformat()))
        conn.commit()
    finally:
        conn.close()
    return list_channels()


def remove_channel(handle: str) -> list[str]:
    h = normalize_handle(handle)
    conn = _yti_conn()
    try:
        conn.execute("DELETE FROM channels WHERE handle = ?", (h,))
        conn.commit()
    finally:
        conn.close()
    return list_channels()


# ---------------------------------------------------------------------------
# Shorts
# ---------------------------------------------------------------------------

def upsert_short(video_id: str, channel: str, title: str, link: str,
                 published: Optional[float], duration_seconds: Optional[float],
                 view_count: int, thumbnail: str = "",
                 transcript: str = "") -> bool:
    """Insert or refresh a short. Returns True when newly inserted.
    An empty transcript never clobbers a stored one."""
    conn = connect()
    try:
        row = conn.execute("SELECT video_id, transcript FROM shorts "
                           "WHERE video_id=?", (video_id,)).fetchone()
        with conn:
            if row:
                conn.execute(
                    "UPDATE shorts SET channel=?, title=?, link=?, "
                    "published=coalesce(?, published), "
                    "duration_seconds=coalesce(?, duration_seconds), "
                    "view_count=?, thumbnail=?, "
                    "transcript=CASE WHEN ?='' THEN transcript ELSE ? END, "
                    "fetched_at=? WHERE video_id=?",
                    (channel, title[:300], link, published, duration_seconds,
                     int(view_count or 0), thumbnail,
                     transcript, transcript[:100_000], time.time(), video_id))
                return False
            conn.execute(
                "INSERT INTO shorts (video_id, channel, title, link, published,"
                " duration_seconds, view_count, thumbnail, transcript,"
                " fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (video_id, channel, title[:300], link, published,
                 duration_seconds, int(view_count or 0), thumbnail,
                 transcript[:100_000], time.time()))
            return True
    finally:
        conn.close()


def list_shorts(days: int = 30) -> list[dict]:
    cutoff = time.time() - days * 86400
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM shorts WHERE published IS NULL OR published >= ? "
            "ORDER BY published DESC", (cutoff,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Meta ads
# ---------------------------------------------------------------------------

def list_ad_pages() -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM ad_pages ORDER BY added_at").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_ad_page(page_id: str, name: str) -> None:
    conn = connect()
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO ad_pages (page_id, name, added_at) "
                "VALUES (?,?,coalesce((SELECT added_at FROM ad_pages "
                "WHERE page_id=?), ?))",
                (str(page_id), name[:200], str(page_id), time.time()))
    finally:
        conn.close()


def remove_ad_page(page_id: str) -> None:
    conn = connect()
    try:
        with conn:
            conn.execute("DELETE FROM ad_pages WHERE page_id=?",
                         (str(page_id),))
            conn.execute("DELETE FROM ads WHERE page_id=?", (str(page_id),))
    finally:
        conn.close()


def upsert_ad(archive_id: str, page_id: str, page_name: str,
              snapshot_url: str, started: Optional[float],
              stopped: Optional[float], active: bool,
              platforms: list, creative: Optional[dict] = None) -> bool:
    conn = connect()
    try:
        row = conn.execute("SELECT archive_id FROM ads WHERE archive_id=?",
                           (str(archive_id),)).fetchone()
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO ads (archive_id, page_id, page_name,"
                " snapshot_url, started, stopped, active, platforms,"
                " creative, pulled_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (str(archive_id), str(page_id), page_name[:200], snapshot_url,
                 started, stopped, 1 if active else 0,
                 json.dumps(platforms or []),
                 json.dumps(creative or {})[:20_000], time.time()))
        return row is None
    finally:
        conn.close()


def list_ads(page_id: Optional[str] = None) -> list[dict]:
    conn = connect()
    try:
        if page_id:
            rows = conn.execute("SELECT * FROM ads WHERE page_id=?",
                                (str(page_id),)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM ads").fetchall()
        out = []
        now = time.time()
        for r in rows:
            d = dict(r)
            d["platforms"] = json.loads(d.get("platforms") or "[]")
            try:
                d["creative"] = json.loads(d.get("creative") or "{}")
            except (TypeError, ValueError):
                d["creative"] = {}
            start = d.get("started")
            end = d.get("stopped") or (now if d.get("active") else None)
            d["daysRunning"] = (round((end - start) / 86400)
                                if start and end and end > start else None)
            out.append(d)
        out.sort(key=lambda a: (a["daysRunning"] is None,
                                -(a["daysRunning"] or 0)))
        return out
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Creations
# ---------------------------------------------------------------------------

def create_creation(kind: str, title: str, brief: str, content: str = "",
                    status: str = "ready", source: Optional[dict] = None) -> int:
    conn = connect()
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO creations (kind, title, brief, content, status,"
                " source, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (kind, title[:300], brief[:5000], content, status,
                 json.dumps(source or {}), time.time(), time.time()))
            return cur.lastrowid
    finally:
        conn.close()


def update_creation(cid: int, **fields) -> None:
    allowed = {"title", "brief", "content", "status", "task_id",
               "result_url", "error", "source"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            if k == "source" and isinstance(v, dict):
                v = json.dumps(v)
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    sets.append("updated_at=?")
    vals.append(time.time())
    vals.append(cid)
    conn = connect()
    try:
        with conn:
            conn.execute(f"UPDATE creations SET {', '.join(sets)} WHERE id=?",
                         vals)
    finally:
        conn.close()


def get_creation(cid: int) -> Optional[dict]:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM creations WHERE id=?",
                           (cid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["source"] = json.loads(d.get("source") or "{}")
        return d
    finally:
        conn.close()


def list_creations(kind: Optional[str] = None) -> list[dict]:
    conn = connect()
    try:
        if kind:
            rows = conn.execute("SELECT * FROM creations WHERE kind=? "
                                "ORDER BY created_at DESC", (kind,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM creations "
                                "ORDER BY created_at DESC").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["source"] = json.loads(d.get("source") or "{}")
            out.append(d)
        return out
    finally:
        conn.close()


def delete_creation(cid: int) -> None:
    conn = connect()
    try:
        with conn:
            conn.execute("DELETE FROM creations WHERE id=?", (cid,))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# kv (cached analyses, fetch state)
# ---------------------------------------------------------------------------

def kv_get(key: str):
    conn = connect()
    try:
        row = conn.execute("SELECT value FROM kv WHERE key=?",
                           (key,)).fetchone()
        return json.loads(row["value"]) if row else None
    finally:
        conn.close()


def kv_set(key: str, value) -> None:
    conn = connect()
    try:
        with conn:
            conn.execute("INSERT OR REPLACE INTO kv (key, value) "
                         "VALUES (?,?)", (key, json.dumps(value)))
    finally:
        conn.close()
