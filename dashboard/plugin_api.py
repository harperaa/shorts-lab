"""Shorts Lab dashboard plugin — backend API routes.

Mounted at /api/plugins/shorts-lab/. Competitor Shorts research (shared
channel list with YouTube Insights), derivative script generation, Meta Ad
Library research, and winning-ad style transfer via KIE.ai.
"""
from __future__ import annotations

import base64
import importlib
import os
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
surge = importlib.import_module(f"{_PKG}.surge")
references = importlib.import_module(f"{_PKG}.references")
recipes = importlib.import_module(f"{_PKG}.recipes")
meta_publish = importlib.import_module(f"{_PKG}.meta_publish")
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
            "copyTakes": (c.get("source") or {}).get("copyTakes", []),
            "postCopy": (c.get("source") or {}).get("postCopy", []),
            "steps": [{"id": st_.get("id"), "state": st_.get("state"),
                       "url": st_.get("url", "")}
                      for st_ in ((c.get("source") or {}).get("steps")
                                  or [])][:12],
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
            "surge": surge.is_connected(),
            "metaAds": meta_publish.is_connected(),
        },
        "adsSource": meta_ads.get_ads_source(),
        "surgeEmail": surge.default_email(),
        "videoTemplates": (store.kv_get("videoTemplates") or [])[:12],
        "metaPublished": (store.kv_get("metaPublished") or [])[:10],
        "autoSync": sync_job.is_enabled(),
        "adlabJob": _sync_state("adlabJobState"),
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


class SurgePublishBody(BaseModel):
    ids: list = []
    domain: str = ""


@router.post("/adlab/surge/publish")
def adlab_surge_publish(body: SurgePublishBody):
    try:
        entry = surge.publish(body.ids or [], body.domain or "")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:300])
    return {"ok": True, "page": entry, "state": _public_state()}


@router.get("/adlab/surge/pages")
def adlab_surge_pages():
    try:
        pages = surge.list_pages()
    except Exception:  # noqa: BLE001 — fall back to what we published
        pages = [{"domain": p["domain"], "url": p["url"],
                  "timeAgo": ""} for p in (store.kv_get("surgePages") or [])]
    return {"ok": True, "pages": pages}


class ConnectBody(BaseModel):
    env: str = "META_ACCESS_TOKEN"
    key: str = ""
    login: str = ""      # surge: account email · metaads: ad account id
    extra: str = ""      # metaads: the Facebook Page id


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
    elif body.env == "META_AD_ACCOUNT_ID":
        # Meta ADS connect: key=token, login=ad account id, extra=page id.
        acct = (body.login or "").strip()
        page = (body.extra or "").strip()
        if not acct or not page:
            raise HTTPException(status_code=400,
                                detail="ad account id and page id are "
                                       "both required")
        check = meta_publish.validate_account(key, acct)
        if not check.get("ok"):
            raise HTTPException(
                status_code=400,
                detail=f"Meta rejected the setup: {check.get('error')}")
        meta_ads.store_key("META_ACCESS_TOKEN", key)
        meta_ads.store_key("META_PAGE_ID", page)
        key = acct           # stored under META_AD_ACCOUNT_ID below
    elif body.env == "SURGE_TOKEN":
        login = (body.login or "").strip()
        if login:
            # email + password entered: mint the token via surge's own
            # login (creates the account for a new email); the password
            # makes this one request and is never stored
            minted = surge.login(login, key)
            if not minted.get("ok"):
                raise HTTPException(status_code=400,
                                    detail=str(minted.get("error")))
            key = minted["token"]
            meta_ads.store_key("SURGE_LOGIN", login)
        else:
            check = surge.validate(key)
            if not check.get("ok"):
                raise HTTPException(
                    status_code=400,
                    detail=f"surge rejected the token: {check.get('error')}")
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


@router.get("/asset/{asset_id}")
def asset_get(asset_id: str):
    """Serve a stored asset — creations generated on the instance's own
    image model land here (their results are local files, not URLs)."""
    if "/" in asset_id or "\\" in asset_id or ".." in asset_id:
        raise HTTPException(status_code=400, detail="bad asset id")
    path = store.assets_dir() / asset_id
    if not path.exists():
        raise HTTPException(status_code=404, detail="asset not found")
    import mimetypes as _mt
    media = _mt.guess_type(asset_id)[0] or "application/octet-stream"
    try:
        from fastapi.responses import FileResponse
        return FileResponse(str(path), media_type=media)
    except Exception:  # noqa: BLE001 — test stubs without fastapi
        return {"ok": True, "bytes": path.stat().st_size, "media": media}


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


def _qa_pair(gen, ad_copy: str, source_spell: str = "") -> tuple:
    """Generate, spellcheck, regenerate up to twice on misspellings.
    `gen` returns (public_url, spellcheck_url) — plugin providers save
    local files, so the two can differ. Returns (public_url, warning);
    fails open when the checker can't run."""
    public, spell = gen()
    verdict = None
    for attempt in range(3):
        try:
            verdict = analysis.spellcheck_image(spell, ad_copy or "",
                                                source_url=source_spell or "")
        except Exception:  # noqa: BLE001
            return public, ""
        if verdict["ok"]:
            return public, ""
        if attempt >= 2:
            break
        try:
            public, spell = gen()
        except Exception:  # noqa: BLE001
            break
    warn = ""
    if verdict is not None and not verdict["ok"]:
        warn = ("QA issues persisted after retries: "
                + "; ".join(verdict["issues"])[:180])
    return public, warn


def _hermes_batch(jobs):
    """[(cid, prompt, source_url, refs, ad_copy)] — the instance's image
    model is synchronous, so a daemon thread fills creations as each
    finishes (spellcheck + retries inline)."""
    def worker():
        for cid, prompt, src_url, refs, ad_copy in jobs:
            try:
                def gen():
                    return imagegen.import_result(
                        imagegen.hermes_generate(prompt, src_url, refs))
                url, warn = _qa_pair(gen, ad_copy, src_url or "")
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
    """Kick off ad generation as a SERVER-SIDE job so it survives page
    refreshes — the browser gets an immediate ack, the page shows the
    running job from state (adlabJob), and creations appear as the
    planner finishes."""
    if not (body.brief or "").strip():
        raise HTTPException(status_code=400,
                            detail="describe your product/offer first")
    if _sync_state("adlabJobState").get("running"):
        raise HTTPException(status_code=409,
                            detail="a generation is already being planned — "
                                   "let it finish first")
    n = max(1, min(50, int(body.variants or 1)))
    backend = imagegen.get_backend()

    def job():
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
        has_portrait = bool((body.sourceAssetId or "").strip()
                            or (body.sourceUrl or "").strip())
        plan = analysis.build_ad_prompt(body.brief, body.adContext or "",
                                        variants=n,
                                        has_source_image=has_portrait)
        prompts = [str(p) for p in (plan.get("variantPrompts") or [])
                   if str(p).strip()][:n]
        copies = [str(c) for c in (plan.get("copyVariants") or [])
                  if str(c).strip()][:n]
        if len(prompts) < n:
            # model under-delivered (or n == 1) — nano is non-deterministic,
            # so repeating the base prompt still yields distinct takes
            prompts += [plan["generationPrompt"]] * (n - len(prompts))

        take_sets = plan.get("copyTakesPerVariant") or []
        post_flat = [t for t in (plan.get("postCopyVariants") or [])
                     if isinstance(t, dict) or str(t).strip()]
        if has_portrait:
            # belt and braces on top of the plan-level mandate — the clause
            # rides every prompt so retries keep it too
            ident = (" Use the exact person from the provided source image — "
                     "same face, hair, and identity, photorealistically "
                     "preserved; do not generate a different or generic person.")
            prompts = [p + ident for p in prompts]
        first_cid = None
        errors = []
        hermes_jobs = []
        for i, prompt in enumerate(prompts):
            title = (plan.get("title") or "Ad creative") + \
                (f" — variant {i + 1}/{n}" if n > 1 else "")
            this_copy = (copies[i] if i < len(copies)
                         else plan.get("adCopy") or "")
            raw_takes = (take_sets[i] if i < len(take_sets) else None) or []
            takes = [str(t)[:300] for t in raw_takes if str(t).strip()][:3]
            if this_copy and this_copy not in takes:
                takes = [this_copy[:300]] + takes[:2]
            raw_posts = post_flat[i * 3:(i + 1) * 3] or post_flat[:3]
            posts = []
            for t in raw_posts[:3]:
                if isinstance(t, dict):
                    p = {"hook": str(t.get("hook") or "")[:400],
                         "content": str(t.get("content") or "")[:4000],
                         "cta": str(t.get("cta") or "")[:300]}
                    if p["hook"] or p["content"]:
                        posts.append(p)
                elif str(t).strip():          # planner fell back to plain text
                    posts.append(
                        {"hook": "", "content": str(t)[:4000], "cta": ""})
            task_id = None
            if backend == "kie":
                try:
                    task_id = kie.submit_image(prompt, aspect_ratio="1:1",
                                               source_url=source_url,
                                               ref_urls=refs)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"variant {i + 1}: {str(exc)[:120]}")
                    continue
            takes_md = "\n".join(
                f"{j + 1}. {t}" for j, t in enumerate(takes)) or this_copy
            posts_md = "\n\n".join(
                f"**Variant {j + 1}:**\n- Hook: {t['hook']}\n"
                f"- Content: {t['content']}\n- CTA: {t['cta']}"
                for j, t in enumerate(posts))
            cid = store.create_creation(
                "image-ad", title, body.brief,
                f"# {title}\n\n**Post copy (runs with the ad):**\n\n"
                f"{posts_md or '(none)'}\n\n"
                f"**In-image copy takes:**\n\n{takes_md}\n\n"
                f"**Notes:** {plan.get('notes')}\n\n## Generation prompt\n\n"
                f"{prompt}",
                status="generating",
                source={"adContext": (body.adContext or "")[:500],
                        "prompt": prompt[:4000], "adCopy": this_copy[:500],
                        "copyTakes": takes,
                        "postCopy": posts,
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
            raise RuntimeError(
                "; ".join(errors)[:300] or "all variants failed")
        return {"created": n - len(errors), "backend": backend,
                "errors": errors}

    def worker():
        try:
            summary = job()
            store.kv_set("adlabJobState",
                         {"running": False, "finishedAt": time.time(),
                          "summary": summary})
        except Exception as exc:  # noqa: BLE001
            store.kv_set("adlabJobState",
                         {"running": False, "finishedAt": time.time(),
                          "error": str(exc)[:300]})
    store.kv_set("adlabJobState",
                 {"running": True, "stage": "planning",
                  "startedAt": time.time()})
    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True, "started": True, "backend": backend,
            "state": _public_state()}


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


# ---------------------------------------------------------------------------
# Advanced studio — references, recipes, pipelines, templates, log
# ---------------------------------------------------------------------------

@router.get("/advanced/state")
def advanced_state():
    hs = imagegen.hermes_status()
    return {
        "recipes": recipes.catalog(),
        "models": {k: {kk: vv for kk, vv in v.items()}
                   for k, v in kie.MODELS.items()},
        "references": references.tree(),
        "referencesImport": store.kv_get("referencesImport"),
        "videoTemplates": store.kv_get("videoTemplates") or [],
        "log": kie.recent_log(30),
        "capabilities": {
            "instanceModel": hs,
            "instanceVideo": False,     # grok/FAL image tools: images only
            "kie": bool((os.environ.get("KIE_API_KEY") or "").strip()),
            "videoNote": "Video and sound generation run on KIE only — "
                         "the instance image model cannot produce them.",
        },
    }


@router.get("/reference/{path:path}")
def reference_get(path: str):
    try:
        p = references.path_for(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not p.is_file():
        raise HTTPException(status_code=404, detail="reference not found")
    import mimetypes as _mt
    media = _mt.guess_type(p.name)[0] or "application/octet-stream"
    try:
        from fastapi.responses import FileResponse
        return FileResponse(str(p), media_type=media)
    except Exception:  # noqa: BLE001
        return {"ok": True, "bytes": p.stat().st_size}


class ReferenceUploadBody(BaseModel):
    folder: str = "products"
    filename: str = "image.jpg"
    dataBase64: str = ""


@router.post("/reference/upload")
def reference_upload(body: ReferenceUploadBody):
    import base64 as _b64
    try:
        payload = _b64.b64decode(body.dataBase64 or "", validate=True)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="bad base64 payload")
    try:
        rel = references.save(body.folder, body.filename, payload)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "path": rel, "references": references.tree()}


class ReferenceDeleteBody(BaseModel):
    path: str = ""


@router.post("/reference/delete")
def reference_delete(body: ReferenceDeleteBody):
    try:
        references.delete(body.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "references": references.tree()}


@router.post("/reference/import-starter")
def reference_import_starter():
    out = references.import_starter_pack()
    return {"ok": True, **out, "references": references.tree()}


def _host_reference(rel: str) -> str:
    """A library file -> public URL for KIE (via the imgBB pipeline)."""
    p = references.path_for(rel)
    if not p.is_file():
        raise HTTPException(status_code=404, detail=f"reference {rel} missing")
    aid = kie.save_asset(p.name, p.read_bytes())
    return kie.host_asset(aid)


class RecipeStartBody(BaseModel):
    recipe: str = ""
    brief: str = ""
    model: str = ""
    aspectRatio: str = "9:16"
    duration: int = 0
    veoMode: str = ""
    variants: int = 1
    extra: str = ""
    refPaths: list = []        # reference-library paths
    refUrls: list = []         # already-public URLs


@router.post("/advanced/recipe/start")
def advanced_recipe_start(body: RecipeStartBody):
    try:
        r = recipes.recipe((body.recipe or "").strip())
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    kie_ready = bool((os.environ.get("KIE_API_KEY") or "").strip())
    refs = [u for u in (body.refUrls or []) if isinstance(u, str) and u]
    backend = imagegen.get_backend()
    # image recipes on the instance backend take library refs as data URIs
    # (no hosting); KIE paths (video, pipelines, kie backend) need public
    # URLs via the imgBB pipeline
    needs_hosting = (r["media"] == "video" or r["kind"] == "pipeline"
                     or backend == "kie")
    try:
        for rel in (body.refPaths or [])[:14]:
            if needs_hosting:
                refs.append(_host_reference(str(rel)))
            else:
                p = references.path_for(str(rel))
                if not p.is_file():
                    raise HTTPException(status_code=404,
                                        detail=f"reference {rel} missing")
                aid = kie.save_asset(p.name, p.read_bytes())
                refs.append(imagegen.asset_data_uri(aid))

        if r["media"] == "video":
            if not kie_ready:
                raise HTTPException(
                    status_code=409,
                    detail="video + sound generation needs KIE — the "
                           "instance image model does images only. "
                           "Connect KIE first.")
            cids = recipes.start_video(
                r["id"], body.brief, model=body.model,
                aspect_ratio=body.aspectRatio or "9:16",
                duration=int(body.duration or 0), ref_urls=refs,
                veo_mode=body.veoMode or "", variants=body.variants,
                extra=body.extra or "")
            return {"ok": True, "creationIds": cids,
                    "state": _public_state()}

        if r["id"] == "character-sheet":
            if not kie_ready:
                raise HTTPException(status_code=409,
                                    detail="the character-sheet pipeline "
                                           "runs on KIE — connect it first")
            cid = recipes.start_character_sheet(
                (body.extra or body.brief or "influencer")[:60], body.brief)
            return {"ok": True, "creationIds": [cid],
                    "state": _public_state()}

        if r["id"] in ("pixar", "claymation"):
            if not kie_ready:
                raise HTTPException(status_code=409,
                                    detail="storyboard pipelines run on "
                                           "KIE — connect it first")
            cid = recipes.start_storyboard(r["id"], body.brief,
                                           beats=int(body.duration or 8),
                                           ref_urls=refs)
            return {"ok": True, "creationIds": [cid],
                    "state": _public_state()}

        # plain image recipes: build prompts from the guide, then ride the
        # EXISTING backend selection (instance model or KIE)
        n = max(1, min(10, int(body.variants or 1)))
        plan = recipes.build_prompts(r["id"], body.brief, n=n,
                                     extra=body.extra or "")
        cids = []
        hermes_jobs = []
        for i, prompt in enumerate(plan["prompts"][:n]):
            title = plan["title"] + (f" — take {i + 1}/{n}" if n > 1 else "")
            task_id = None
            family = "jobs"
            if backend == "kie":
                if r["id"] == "image-ad-template" or \
                        (body.model or "") == "gpt4o-image":
                    sub = kie.submit_gpt4o_image(prompt, size="1:1",
                                                 files_url=refs)
                else:
                    sub = kie.submit_jobs_image(
                        body.model or "nano-banana-2", prompt,
                        aspect_ratio=body.aspectRatio or "1:1",
                        image_input=refs)
                task_id, family = sub["taskId"], sub["family"]
            cid = store.create_creation(
                "image-ad", title, body.brief,
                f"# {title}\n\n**Recipe:** {r['name']}\n\n"
                f"**Notes:** {plan['notes']}\n\n"
                f"## Generation prompt\n\n{prompt}",
                status="generating",
                source={"recipe": r["id"], "prompt": prompt[:4000],
                        "family": family, "backend": backend,
                        "retries": 0})
            if task_id:
                store.update_creation(cid, task_id=task_id)
            else:
                hermes_jobs.append((cid, prompt, None,
                                    refs[:3], ""))
            cids.append(cid)
        if hermes_jobs:
            _hermes_batch(hermes_jobs)
        return {"ok": True, "creationIds": cids, "state": _public_state()}
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:300])


class AnalyzeVideoBody(BaseModel):
    url: str = ""
    description: str = ""
    recipe: str = "analyze-video"


@router.post("/advanced/analyze-video")
def advanced_analyze_video(body: AnalyzeVideoBody):
    if not (body.url or "").strip() and not (body.description or "").strip():
        raise HTTPException(status_code=400,
                            detail="give the video URL and describe it")
    try:
        tpl = recipes.analyze_video(
            (body.url or "").strip(), body.description or "",
            recipe_id=("clone-ad" if body.recipe == "clone-ad"
                       else "analyze-video"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:300])
    return {"ok": True, "template": tpl, "state": _public_state()}


class AnimateBody(BaseModel):
    id: int = 0
    model: str = "bytedance/seedance-2"


@router.post("/advanced/animate")
def advanced_animate(body: AnimateBody):
    if not (os.environ.get("KIE_API_KEY") or "").strip():
        raise HTTPException(status_code=409,
                            detail="animating beats runs on KIE — "
                                   "connect it first")
    try:
        made = recipes.animate_storyboard(body.id, model=body.model)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True, "clips": made, "state": _public_state()}


@router.get("/adlab/meta/adsets")
def meta_adsets():
    try:
        return {"ok": True, "adsets": meta_publish.list_adsets()}
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:300])


class MetaPublishBody(BaseModel):
    ids: list = []
    adsetId: str = ""
    link: str = ""
    cta: str = "LEARN_MORE"


@router.post("/adlab/meta/publish")
def meta_publish_route(body: MetaPublishBody):
    """Publish selected creatives as PAUSED Meta ads (draft in Ads
    Manager) — the kit's deploy path, one ad per creation."""
    if not (body.adsetId or "").strip():
        raise HTTPException(status_code=400,
                            detail="pick the target ad set")
    if not (body.link or "").strip().startswith("http"):
        raise HTTPException(status_code=400,
                            detail="the ad needs a destination link (https)")
    published, errors = [], []
    for cid in (body.ids or [])[:10]:
        c = store.get_creation(int(cid))
        if not c or c.get("status") != "ready" or not c.get("result_url"):
            errors.append(f"creation {cid}: not ready")
            continue
        try:
            payload = _creation_image_bytes(c["result_url"])
            entry = meta_publish.publish_creation(
                c, body.adsetId.strip(), body.link.strip(),
                cta=(body.cta or "LEARN_MORE").strip(),
                image_bytes=payload)
            published.append(entry)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"creation {cid}: {str(exc)[:150]}")
    if not published:
        raise HTTPException(status_code=502,
                            detail="; ".join(errors)[:300] or "nothing published")
    return {"ok": True, "published": published, "errors": errors,
            "state": _public_state()}


def _creation_image_bytes(result_url: str) -> bytes:
    import re as _re
    import requests as _rq
    m = _re.match(r"^/api/plugins/shorts-lab/asset/([A-Za-z0-9_.-]+)$",
                  result_url or "")
    if m:
        p = store.assets_dir() / m.group(1)
        if not p.exists():
            raise RuntimeError("asset file missing")
        return p.read_bytes()
    r = _rq.get(result_url, timeout=120)
    r.raise_for_status()
    return r.content


class CreationBody(BaseModel):
    id: int = 0


@router.post("/creations/check")
def creations_check(body: CreationBody):
    c = store.get_creation(body.id)
    if not c:
        raise HTTPException(status_code=404, detail="creation not found")
    if c["status"] == "generating" and c.get("task_id"):
        fam = (c.get("source") or {}).get("family") or "jobs"
        try:
            tick = kie.check_any(c["task_id"], fam) if fam != "jobs" \
                else kie.check_task(c["task_id"])
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
                    tick["url"], src.get("adCopy") or "",
                    source_url=src.get("sourceUrl") or "")
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
                        error="retry {}/2 — QA issues: {}".format(
                            retries + 1,
                            "; ".join(verdict["issues"])[:150]))
                    return {"ok": True, "state": _public_state()}
                except Exception:  # noqa: BLE001
                    pass          # resubmit failed — fall through to ready
            warn = ""
            if verdict is not None and not verdict["ok"]:
                warn = ("QA issues persisted after retries: "
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


# ---------------------------------------------------------------------------
# Accomplishments — read by the acvc /accomplishments aggregator and shown
# on the hermes Achievements page. Full credit when every item is done.
# ---------------------------------------------------------------------------

ACHIEVEMENT = {
    "id": "short-form-operator",
    "name": "Short Form Operator",
    "icon": "⚡",
    "description": "Run the Short Form engine: watch the winners, "
                   "then ship your own creatives.",
}


def achievements_progress() -> dict:
    items = [
        {"id": "channel", "label": "Monitor a competitor shorts channel",
         "done": bool(store.list_channels())},
        {"id": "shorts", "label": "Pull their recent shorts",
         "done": bool(store.list_shorts(3650))},
        {"id": "adspage", "label": "Monitor an ad page on Ads Research",
         "done": bool(store.list_ad_pages())},
        {"id": "creative", "label": "Generate your first creative in the Lab",
         "done": any(c.get("status") == "ready"
                     for c in store.list_creations())},
    ]
    return {"items": items, "complete": all(i["done"] for i in items)}
