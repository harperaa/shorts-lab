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
imagegen = importlib.import_module(f"{_PKG}.imagegen")
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
        "imageBackend": {
            "active": imagegen.get_backend(),
            "choice": store.kv_get("imageBackend") or "auto",
            "hermes": imagegen.hermes_status(),
        },
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


def _qa_url(url: str, ad_copy: str, regen) -> tuple:
    """Spellcheck a finished image; regenerate up to twice on misspellings.
    Returns (final_url, warning). Fails open when the checker can't run."""
    warn = ""
    verdict = None
    for attempt in range(3):
        try:
            verdict = analysis.spellcheck_image(url, ad_copy or "")
        except Exception:  # noqa: BLE001
            return url, ""
        if verdict["ok"]:
            return url, ""
        if attempt >= 2:
            break
        try:
            url = regen()
        except Exception:  # noqa: BLE001
            break
    if verdict is not None and not verdict["ok"]:
        warn = ("spelling issues persisted after retries: "
                + "; ".join(verdict["issues"])[:180])
    return url, warn


def _hermes_batch(jobs):
    """[(cid, prompt, source_url, refs, ad_copy)] — the instance's image
    model is synchronous, so a daemon thread fills creations as each
    finishes (spellcheck + retries inline)."""
    def worker():
        for cid, prompt, src_url, refs, ad_copy in jobs:
            try:
                def regen():
                    return imagegen.hermes_generate(prompt, src_url, refs)
                url, warn = _qa_url(regen(), ad_copy, regen)
                store.update_creation(cid, status="ready",
                                      result_url=url, error=warn)
            except Exception as exc:  # noqa: BLE001
                store.update_creation(cid, status="failed",
                                      error=str(exc)[:300])
    threading.Thread(target=worker, daemon=True).start()


class ImageBackendBody(BaseModel):
    backend: str = "auto"


@router.post("/adlab/backend")
def adlab_backend(body: ImageBackendBody):
    try:
        imagegen.set_backend((body.backend or "auto").strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "state": _public_state()}


class AdLabBody(BaseModel):
    brief: str = ""
    adContext: str = ""
    sourceAssetId: str = ""
    styleAssetId: str = ""
    sourceUrl: str = ""
    styleUrl: str = ""
    variants: int = 1


@router.post("/adlab/generate")
def adlab_generate(body: AdLabBody):
    if not (body.brief or "").strip():
        raise HTTPException(status_code=400,
                            detail="describe your product/offer first")
    n = max(1, min(50, int(body.variants or 1)))
    backend = imagegen.get_backend()
    try:
        plan = analysis.build_ad_prompt(body.brief, body.adContext or "",
                                        variants=n)
        if backend == "hermes":
            # the instance's model takes data URIs — no public hosting
            source_url = (body.sourceUrl or "").strip() or (
                imagegen.asset_data_uri(body.sourceAssetId)
                if (body.sourceAssetId or "").strip() else None)
            style_url = (body.styleUrl or "").strip() or (
                imagegen.asset_data_uri(body.styleAssetId)
                if (body.styleAssetId or "").strip() else None)
        else:
            source_url = (body.sourceUrl or "").strip() or (
                kie.host_asset(body.sourceAssetId)
                if (body.sourceAssetId or "").strip() else None)
            style_url = (body.styleUrl or "").strip() or (
                kie.host_asset(body.styleAssetId)
                if (body.styleAssetId or "").strip() else None)
        refs = [u for u in [style_url] if u]
        prompts = [str(p) for p in (plan.get("variantPrompts") or [])
                   if str(p).strip()][:n]
        copies = [str(c) for c in (plan.get("copyVariants") or [])
                  if str(c).strip()][:n]
        if len(prompts) < n:
            # model under-delivered (or n == 1) — nano is non-deterministic,
            # so repeating the base prompt still yields distinct takes
            prompts += [plan["generationPrompt"]] * (n - len(prompts))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:300])

    first_cid = None
    errors = []
    hermes_jobs = []
    for i, prompt in enumerate(prompts):
        title = (plan.get("title") or "Ad creative") + \
            (f" — variant {i + 1}/{n}" if n > 1 else "")
        this_copy = (copies[i] if i < len(copies)
                     else plan.get("adCopy") or "")
        task_id = None
        if backend == "kie":
            try:
                task_id = kie.submit_image(prompt, aspect_ratio="1:1",
                                           source_url=source_url,
                                           ref_urls=refs)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"variant {i + 1}: {str(exc)[:120]}")
                continue
        cid = store.create_creation(
            "image-ad", title, body.brief,
            f"# {title}\n\n**Ad copy (this take):** {this_copy}\n\n"
            f"**Notes:** {plan.get('notes')}\n\n## Generation prompt\n\n"
            f"{prompt}",
            status="generating",
            source={"adContext": (body.adContext or "")[:500],
                    "prompt": prompt[:4000], "adCopy": this_copy[:500],
                    "backend": backend,
                    "sourceUrl": ("" if backend == "hermes"
                                  else (source_url or "")),
                    "styleUrl": ("" if backend == "hermes"
                                 else (refs[0] if refs else "")),
                    "retries": 0})
        if task_id:
            store.update_creation(cid, task_id=task_id)
        else:
            hermes_jobs.append((cid, prompt, source_url, refs, this_copy))
        if first_cid is None:
            first_cid = cid
    if hermes_jobs:
        _hermes_batch(hermes_jobs)
    if first_cid is None:
        raise HTTPException(status_code=502,
                            detail="; ".join(errors)[:300] or "all variants failed")
    return {"ok": True, "creationId": first_cid,
            "submitted": n - len(errors), "backend": backend,
            "errors": errors, "state": _public_state()}


class IterateBody(BaseModel):
    id: int = 0
    instruction: str = ""
    variants: int = 1


@router.post("/adlab/iterate")
def adlab_iterate(body: IterateBody):
    """Edit a produced image: the creation's result becomes the new source
    and the user's instruction is the edit — no LLM planning round-trip."""
    c = store.get_creation(body.id)
    if not c:
        raise HTTPException(status_code=404, detail="creation not found")
    if not (c.get("result_url") or "").strip():
        raise HTTPException(status_code=409,
                            detail="that creation has no image yet")
    instruction = (body.instruction or "").strip()
    if not instruction:
        raise HTTPException(status_code=400,
                            detail="describe the edit first")
    n = max(1, min(10, int(body.variants or 1)))
    backend = imagegen.get_backend()
    prompt = (instruction +
              " Keep everything else in the image unchanged — same "
              "composition, text placement, colors, and identity.")
    first_cid = None
    errors = []
    hermes_jobs = []
    for i in range(n):
        task_id = None
        if backend == "kie":
            try:
                task_id = kie.submit_image(prompt, aspect_ratio="1:1",
                                           source_url=c["result_url"])
            except Exception as exc:  # noqa: BLE001
                errors.append(f"take {i + 1}: {str(exc)[:120]}")
                continue
        title = c["title"] + " — edit" + (f" {i + 1}/{n}" if n > 1 else "")
        cid = store.create_creation(
            "image-ad", title, c.get("brief") or "",
            f"# {title}\n\n**Edit instruction:** {instruction}\n\n"
            f"Iterated from creation #{c['id']} ({c['title']}).",
            status="generating",
            source={"parentId": c["id"], "instruction": instruction[:300],
                    "prompt": prompt[:4000], "backend": backend,
                    "sourceUrl": c["result_url"], "retries": 0})
        if task_id:
            store.update_creation(cid, task_id=task_id)
        else:
            hermes_jobs.append((cid, prompt, c["result_url"], [], ""))
        if first_cid is None:
            first_cid = cid
    if hermes_jobs:
        _hermes_batch(hermes_jobs)
    if first_cid is None:
        raise HTTPException(status_code=502,
                            detail="; ".join(errors)[:300] or "iterate failed")
    return {"ok": True, "creationId": first_cid, "state": _public_state()}


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
            src = dict(c.get("source") or {})
            retries = int(src.get("retries") or 0)
            verdict = None
            try:
                # proof the rendered text BEFORE the user sees the card —
                # fail open if the checker itself can't run
                verdict = analysis.spellcheck_image(
                    tick["url"], src.get("adCopy") or "")
            except Exception:  # noqa: BLE001
                verdict = None
            if verdict is not None and not verdict["ok"] \
                    and src.get("prompt") and retries < 2:
                # misspelled render: bin it and resubmit the same prompt
                try:
                    new_task = kie.submit_image(
                        src["prompt"], aspect_ratio="1:1",
                        source_url=src.get("sourceUrl") or None,
                        ref_urls=[u for u in [src.get("styleUrl")] if u])
                    src["retries"] = retries + 1
                    src["lastIssues"] = verdict["issues"]
                    store.update_creation(
                        body.id, task_id=new_task, source=src,
                        error="retry {}/2 — spelling issues: {}".format(
                            retries + 1,
                            "; ".join(verdict["issues"])[:150]))
                    return {"ok": True, "state": _public_state()}
                except Exception:  # noqa: BLE001
                    pass          # resubmit failed — fall through to ready
            warn = ""
            if verdict is not None and not verdict["ok"]:
                warn = ("spelling issues persisted after retries: "
                        + "; ".join(verdict["issues"])[:180])
            store.update_creation(body.id, status="ready",
                                  result_url=tick["url"], error=warn)
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
