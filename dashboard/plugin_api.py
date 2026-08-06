"""Shorts Lab dashboard plugin — backend API routes.

Mounted at /api/plugins/shorts-lab/. Competitor Shorts research (shared
channel list with YouTube Insights), derivative script generation, Meta Ad
Library research, and winning-ad style transfer via KIE.ai.
"""
from __future__ import annotations

import base64
import importlib
import importlib.util
import sys
import threading
import time
from pathlib import Path

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
except Exception:  # allows unit tests without dashboard dependencies
    class APIRouter:  # type: ignore
        def get(self, *a, **k):
            return lambda fn: fn

        def post(self, *a, **k):
            return lambda fn: fn

    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code: int, detail: str = ""):
            super().__init__(detail)
            self.status_code = status_code

    class BaseModel:  # type: ignore
        pass

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_PKG = "hermes_plugin_pkg_shorts_lab"

if _PKG not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        _PKG, str(_PLUGIN_ROOT / "__init__.py"),
        submodule_search_locations=[str(_PLUGIN_ROOT)])
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_PKG] = _mod
    _spec.loader.exec_module(_mod)

store = importlib.import_module(f"{_PKG}.store")
transcripts = importlib.import_module(f"{_PKG}.transcripts")
meta_ads = importlib.import_module(f"{_PKG}.meta_ads")
kie = importlib.import_module(f"{_PKG}.kie")
sync_job = importlib.import_module(f"{_PKG}.sync_job")
analysis = importlib.import_module(f"{_PKG}.analysis")

router = APIRouter()

_SYNC_STALE_SECONDS = 600


def _has_key(env_var: str) -> bool:
    import os
    if (os.environ.get(env_var) or "").strip():
        return True
    try:
        for line in (store._home() / ".env").read_text().splitlines():
            if line.strip().startswith(env_var + "="):
                return bool(line.split("=", 1)[1].strip())
    except OSError:
        pass
    return False


def _sync_state(key: str) -> dict:
    st = store.kv_get(key) or {}
    if st.get("running") and time.time() - (st.get("startedAt") or 0) > \
            _SYNC_STALE_SECONDS:
        st = {**st, "running": False,
              "error": "sync timed out — try again"}
        store.kv_set(key, st)
    return st


def _run_sync(key: str, fn) -> None:
    def worker():
        try:
            summary = fn()
            store.kv_set(key, {"running": False, "finishedAt": time.time(),
                               "summary": summary})
        except Exception as exc:  # noqa: BLE001
            store.kv_set(key, {"running": False, "finishedAt": time.time(),
                               "error": str(exc)[:300]})
    store.kv_set(key, {"running": True, "startedAt": time.time()})
    threading.Thread(target=worker, daemon=True).start()


def _public_state() -> dict:
    shorts = []
    for s in store.list_shorts(30):
        shorts.append({
            "videoId": s["video_id"], "channel": s["channel"],
            "title": s["title"], "link": s["link"],
            "published": s.get("published"),
            "durationSeconds": s.get("duration_seconds"),
            "viewCount": s.get("view_count") or 0,
            "thumbnail": s.get("thumbnail") or "",
            "hasTranscript": bool((s.get("transcript") or "").strip()),
        })
    creations = []
    for c in store.list_creations():
        creations.append({
            "id": c["id"], "kind": c["kind"], "title": c["title"],
            "brief": c["brief"], "status": c["status"],
            "resultUrl": c.get("result_url") or "",
            "error": c.get("error") or "",
            "createdAt": c.get("created_at"),
            "pattern": (c.get("source") or {}).get("pattern", ""),
        })
    return {
        "channels": store.list_channels(),
        "shorts": shorts,
        "shortsAnalysis": store.kv_get("shortsAnalysis"),
        "shortsSync": _sync_state("shortsSyncState"),
        "adPages": store.list_ad_pages(),
        "ads": store.list_ads(),
        "adsSync": _sync_state("adsSyncState"),
        "creations": creations,
        "keys": {
            "transcript": _has_key("TRANSCRIPT_API_KEY"),
            "meta": _has_key("META_ACCESS_TOKEN"),
            "apify": _has_key("APIFY_API_TOKEN"),
            "kie": _has_key("KIE_API_KEY"),
            "imgbb": _has_key("IMGBB_API_KEY"),
        },
        "adsSource": meta_ads.get_ads_source(),
        "autoSync": sync_job.is_enabled(),
    }


@router.get("/state")
def state():
    return _public_state()


class ChannelBody(BaseModel):
    handle: str = ""
    action: str = "add"     # add | remove


@router.post("/channels")
def channels(body: ChannelBody):
    try:
        if body.action == "remove":
            store.remove_channel(body.handle)
        else:
            store.add_channel(body.handle)
            # with auto-sync enabled, tracked channels join the cron
            try:
                if sync_job.is_enabled():
                    sync_job.ensure_shorts_job()
            except Exception:  # noqa: BLE001 — cron absent outside hermes
                pass
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "state": _public_state()}


class AutoSyncBody(BaseModel):
    enabled: bool = False


@router.post("/autosync")
def autosync(body: AutoSyncBody):
    try:
        sync_job.set_enabled(bool(body.enabled))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)[:200])
    return {"ok": True, "state": _public_state()}


@router.post("/shorts/sync")
def shorts_sync():
    st = _sync_state("shortsSyncState")
    if st.get("running"):
        return {"ok": True, "state": _public_state()}
    _run_sync("shortsSyncState", transcripts.fetch_shorts)
    return {"ok": True, "state": _public_state()}


@router.post("/shorts/analyze")
def shorts_analyze():
    try:
        analysis.analyze_shorts()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:300])
    return {"ok": True, "state": _public_state()}


class DerivativeBody(BaseModel):
    brief: str = ""
    pattern: str = ""


@router.post("/derivative")
def derivative(body: DerivativeBody):
    if not (body.brief or "").strip():
        raise HTTPException(status_code=400,
                            detail="tell the writer what the short is about")
    try:
        cid = analysis.create_derivative(body.brief, body.pattern or "")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:300])
    return {"ok": True, "creationId": cid, "state": _public_state()}


class ConnectBody(BaseModel):
    env: str = "META_ACCESS_TOKEN"
    key: str = ""


@router.post("/connect")
def connect(body: ConnectBody):
    key = (body.key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="paste the token first")
    if body.env == "META_ACCESS_TOKEN":
        # cheapest sanity check there is — catches truncated pastes and
        # expired tokens before they get stored
        check = meta_ads.validate_token(key)
        if not check.get("ok"):
            raise HTTPException(
                status_code=400,
                detail=f"Meta rejected the token: {check.get('error')}")
    elif body.env == "APIFY_API_TOKEN":
        check = meta_ads.validate_apify_token(key)
        if not check.get("ok"):
            raise HTTPException(
                status_code=400,
                detail=f"Apify rejected the token: {check.get('error')}")
    elif body.env == "KIE_API_KEY":
        check = kie.validate_key(key)
        if not check.get("ok"):
            raise HTTPException(
                status_code=400,
                detail=f"KIE rejected the key: {check.get('error')}")
    elif body.env == "IMGBB_API_KEY":
        check = kie.validate_imgbb_key(key)
        if not check.get("ok"):
            raise HTTPException(
                status_code=400,
                detail=f"imgBB rejected the key: {check.get('error')}")
    try:
        meta_ads.store_key(body.env, key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "state": _public_state()}


class AdsSearchBody(BaseModel):
    term: str = ""


@router.post("/ads/search")
def ads_search(body: AdsSearchBody):
    if not (body.term or "").strip():
        raise HTTPException(status_code=400, detail="search term required")
    try:
        results = meta_ads.search_pages_any(body.term.strip())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:300])
    return {"ok": True, "results": results}


class MonitorBody(BaseModel):
    pageId: str = ""
    name: str = ""


@router.post("/ads/monitor")
def ads_monitor(body: MonitorBody):
    if not (body.pageId or "").strip():
        raise HTTPException(status_code=400, detail="pageId required")
    store.add_ad_page(body.pageId.strip(), body.name or body.pageId)
    # with auto-sync enabled, a new monitor joins the twice-daily cron
    try:
        if sync_job.is_enabled():
            sync_job.ensure_ads_job()
    except Exception:  # noqa: BLE001 — cron absent outside hermes (tests)
        pass
    # keyless monitoring is a bookmark to the public Ad Library — only kick
    # a pull when a data backend exists, so no-key users never see an error
    if _has_key("APIFY_API_TOKEN") or _has_key("META_ACCESS_TOKEN"):
        _run_sync("adsSyncState", meta_ads.sync_all_pages)
    return {"ok": True, "state": _public_state()}


@router.post("/ads/unmonitor")
def ads_unmonitor(body: MonitorBody):
    store.remove_ad_page((body.pageId or "").strip())
    return {"ok": True, "state": _public_state()}


class SourceBody(BaseModel):
    source: str = ""


@router.post("/ads/source")
def ads_source(body: SourceBody):
    try:
        meta_ads.set_ads_source((body.source or "").strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "state": _public_state()}


@router.post("/ads/sync")
def ads_sync():
    st = _sync_state("adsSyncState")
    if st.get("running"):
        return {"ok": True, "state": _public_state()}
    _run_sync("adsSyncState", meta_ads.sync_all_pages)
    return {"ok": True, "state": _public_state()}


class AssetBody(BaseModel):
    filename: str = "asset.jpg"
    dataBase64: str = ""


@router.post("/asset")
def asset(body: AssetBody):
    try:
        payload = base64.b64decode(body.dataBase64 or "", validate=False)
        if not payload:
            raise ValueError("empty upload")
        aid = kie.save_asset(body.filename, payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)[:200])
    return {"ok": True, "assetId": aid}


class AdLabBody(BaseModel):
    brief: str = ""
    adContext: str = ""
    sourceAssetId: str = ""
    styleAssetId: str = ""
    sourceUrl: str = ""
    styleUrl: str = ""


@router.post("/adlab/generate")
def adlab_generate(body: AdLabBody):
    if not (body.brief or "").strip():
        raise HTTPException(status_code=400,
                            detail="describe your product/offer first")
    try:
        plan = analysis.build_ad_prompt(body.brief, body.adContext or "")
        source_url = (body.sourceUrl or "").strip() or (
            kie.host_asset(body.sourceAssetId)
            if (body.sourceAssetId or "").strip() else None)
        style_url = (body.styleUrl or "").strip() or (
            kie.host_asset(body.styleAssetId)
            if (body.styleAssetId or "").strip() else None)
        refs = [u for u in [style_url] if u]
        task_id = kie.submit_image(plan["generationPrompt"],
                                   aspect_ratio="1:1",
                                   source_url=source_url, ref_urls=refs)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:300])
    cid = store.create_creation(
        "image-ad", plan.get("title") or "Ad creative", body.brief,
        f"# {plan.get('title')}\n\n**Ad copy:** {plan.get('adCopy')}\n\n"
        f"**Notes:** {plan.get('notes')}\n\n## Generation prompt\n\n"
        f"{plan.get('generationPrompt')}",
        status="generating",
        source={"adContext": (body.adContext or "")[:500]})
    store.update_creation(cid, task_id=task_id)
    return {"ok": True, "creationId": cid, "state": _public_state()}


class CreationBody(BaseModel):
    id: int = 0


@router.post("/creations/check")
def creations_check(body: CreationBody):
    c = store.get_creation(body.id)
    if not c:
        raise HTTPException(status_code=404, detail="creation not found")
    if c["status"] == "generating" and c.get("task_id"):
        try:
            tick = kie.check_task(c["task_id"])
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)[:200])
        if tick["state"] == "success":
            store.update_creation(body.id, status="ready",
                                  result_url=tick["url"])
        elif tick["state"] == "fail":
            store.update_creation(body.id, status="failed",
                                  error=tick.get("error") or "failed")
    return {"ok": True, "state": _public_state()}


@router.post("/creations/delete")
def creations_delete(body: CreationBody):
    store.delete_creation(body.id)
    return {"ok": True, "state": _public_state()}


@router.get("/creation/{cid}")
def creation_detail(cid: int):
    c = store.get_creation(cid)
    if not c:
        raise HTTPException(status_code=404, detail="creation not found")
    return c
