"""KIE.ai client — distilled from the ad-builder kit's Nano Banana generator
(Kruse Media LLC / AI Cyber Sherpas LLC, MIT). stdlib urllib only.

Facts (verified against the kit + docs.kie.ai):
- POST /api/v1/jobs/createTask  {"model": ..., "input": {...}} -> taskId
- GET  /api/v1/jobs/recordInfo?taskId=...  -> state, resultJson (JSON string)
  containing resultUrls
- Bearer KIE_API_KEY; reference images must be PUBLIC URLs (no upload flow),
  so local assets are hosted via imgBB — the kit's proven uploader
  (scripts/imgbb-upload.sh); 0x0.st shut off uploads entirely.
"""
from __future__ import annotations

import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Optional

try:
    from . import store
except ImportError:  # loaded outside package context
    import store  # type: ignore

BASE_URL = os.environ.get("KIE_BASE_URL", "https://api.kie.ai")
# Model strings verified against the live marketplace 2026-08-06 — KIE's
# catalog is MIXED: fresh generation keeps the bare string + image_input,
# while the edit model moved to the google/ prefix + image_urls. The old
# bare "nano-banana-edit" now 422s ("model name not supported").
IMAGE_MODEL = "nano-banana-2"              # fresh generation (image_input)
EDIT_MODEL = "google/nano-banana-edit"     # source + style refs (image_urls)

# appended to ad prompts, straight from the kit's hard-won suffixes
NO_CHROME_SUFFIX = (" No phone UI chrome, no status bar, no app frame unless"
                    " the ad concept explicitly calls for it.")
GLYPH_SUFFIX = (" All text must be spelled exactly as specified, real"
                " renderable glyphs, no gibberish lettering.")


def _get_key() -> str:
    key = (os.environ.get("KIE_API_KEY") or "").strip()
    if not key:
        env_path = store._home() / ".env"
        try:
            for line in env_path.read_text().splitlines():
                if line.strip().startswith("KIE_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
        except OSError:
            pass
    if not key:
        raise RuntimeError("KIE_API_KEY not set — add it on the Keys page "
                           "(kie.ai/api-key)")
    return key


def _post_json(url: str, body: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {_get_key()}",
                 "Content-Type": "application/json",
                 "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body_txt = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body_txt)
        except json.JSONDecodeError:
            raise RuntimeError(f"KIE HTTP {exc.code}: {body_txt[:200]}")


def _get_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {_get_key()}",
                      "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def credit() -> dict:
    """Cheapest auth check — account credit balance."""
    return _get_json(f"{BASE_URL}/api/v1/chat/credit")


def submit_image(prompt: str, aspect_ratio: str = "9:16",
                 source_url: Optional[str] = None,
                 ref_urls: Optional[list[str]] = None) -> str:
    """Create an image task. With source_url -> edit mode (style transfer:
    source first, style refs follow). Returns the taskId."""
    refs = [u for u in (ref_urls or []) if u]
    final_prompt = prompt + NO_CHROME_SUFFIX + GLYPH_SUFFIX
    if source_url:
        model = EDIT_MODEL
        inputs: dict = {"prompt": final_prompt,
                        "image_urls": [source_url] + refs,
                        "output_format": "png",
                        "aspect_ratio": aspect_ratio or "auto"}
    else:
        model = IMAGE_MODEL
        inputs = {"prompt": final_prompt, "aspect_ratio": aspect_ratio,
                  "output_format": "png"}
        if refs:
            inputs["image_input"] = refs
    resp = _post_json(f"{BASE_URL}/api/v1/jobs/createTask",
                      {"model": model, "input": inputs})
    data = resp.get("data") or {}
    task_id = data.get("taskId") or resp.get("taskId")
    code = resp.get("code")
    if code is not None and code != 200:
        raise RuntimeError(f"KIE submit code={code}: "
                           f"{resp.get('msg') or resp}")
    if not task_id:
        raise RuntimeError(f"KIE submit returned no taskId: {resp}")
    return task_id


def check_task(task_id: str) -> dict:
    """One poll tick. Returns {state, url?, error?} — the caller decides
    cadence (the dashboard polls from the page; no long-blocking here)."""
    resp = _get_json(f"{BASE_URL}/api/v1/jobs/recordInfo?taskId={task_id}")
    data = resp.get("data") or {}
    state = data.get("state")
    if state == "success":
        raw = data.get("resultJson")
        result = json.loads(raw) if isinstance(raw, str) else (raw or {})
        urls = result.get("resultUrls") or result.get("urls")
        if not urls:
            imgs = result.get("images") or result.get("output")
            if isinstance(imgs, list) and imgs:
                urls = [i.get("url") if isinstance(i, dict) else i
                        for i in imgs]
        if not urls:
            return {"state": "fail",
                    "error": f"success but no URLs: {str(result)[:200]}"}
        return {"state": "success", "url": urls[0]}
    if state in {"fail", "failed"}:
        return {"state": "fail",
                "error": str(data.get("failMsg") or data.get("error")
                             or resp.get("msg") or "generation failed")[:300]}
    return {"state": state or "waiting"}


# ---------------------------------------------------------------------------
# Asset hosting — KIE fetches references by public URL only
# ---------------------------------------------------------------------------

def save_asset(filename: str, payload: bytes) -> str:
    """Store an uploaded asset locally; returns its asset id."""
    ext = Path(filename or "asset.jpg").suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise RuntimeError("asset must be a jpg/png/webp image")
    if len(payload) > 15 * 1024 * 1024:
        raise RuntimeError("asset too large (15 MB max)")
    aid = uuid.uuid4().hex[:16] + ext
    (store.assets_dir() / aid).write_bytes(payload)
    return aid


def host_asset(asset_id: str) -> str:
    """Host a stored asset on imgBB (the ad-builder kit's proven uploader —
    0x0.st shut off uploads) and return the public URL KIE can fetch.

    Ported from the kit's scripts/imgbb-upload.sh: sha256 content cache,
    auto-delete after 30 minutes BY DEFAULT (override with IMGBB_EXPIRATION,
    60-15552000 seconds) — a mentee's portrait should not live forever on a
    public host — and a 900s safety margin so a cached URL never dies while
    KIE's queue is still fetching it."""
    import hashlib
    import time as _time

    path = store.assets_dir() / asset_id
    if not path.exists():
        raise RuntimeError(f"asset {asset_id} not found")
    payload = path.read_bytes()
    if len(payload) > 32 * 1024 * 1024:
        raise RuntimeError("asset too large for imgBB (32 MB max)")

    key = ""
    for var in ("IMGBB_API_KEY", "IMAGBB_API_KEY"):   # kit accepts the typo
        key = (os.environ.get(var) or "").strip()
        if not key:
            try:
                for line in (store._home() / ".env").read_text().splitlines():
                    if line.strip().startswith(var + "="):
                        key = line.split("=", 1)[1].strip()
                        break
            except OSError:
                pass
        if key:
            break
    if not key:
        raise RuntimeError("IMGBB_API_KEY not set — grab a free key at "
                           "api.imgbb.com and add it on the Keys page "
                           "(reference images must be publicly hosted for "
                           "the generator)")

    sha = hashlib.sha256(payload).hexdigest()
    now = _time.time()
    cache = store.kv_get("hostedAssets") or {}
    hit = cache.get(sha)
    if isinstance(hit, dict):
        exp = hit.get("expiresAt")
        if hit.get("url") and (not exp or exp > now + 900):
            return hit["url"]

    boundary = uuid.uuid4().hex
    ctype = mimetypes.guess_type(asset_id)[0] or "image/jpeg"
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; '
            f'filename="{asset_id}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n").encode() + payload + \
        f"\r\n--{boundary}--\r\n".encode()
    url = f"https://api.imgbb.com/1/upload?key={key}"
    # short-lived by default: 30 minutes covers KIE's queue + generation
    # (plus a redo or two via the sha256 cache) and then the image is gone
    expiration = (os.environ.get("IMGBB_EXPIRATION") or "").strip() or "1800"
    url += f"&expiration={expiration}"
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "User-Agent": "shorts-lab/1.0 (hermes plugin)"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"imgBB upload failed (HTTP {exc.code}): {detail}")
    if not data.get("success"):
        err = (data.get("error") or {}).get("message") or str(data)[:200]
        raise RuntimeError(f"imgBB upload failed: {err}")
    hosted = data["data"]["url"]
    entry = {"url": hosted, "at": now,
             "expiresAt": now + int(expiration)}
    cache[sha] = entry
    store.kv_set("hostedAssets", cache)
    return hosted


def validate_key(key: str) -> dict:
    """Cheapest KIE auth check with an explicit key (credit balance)."""
    req = urllib.request.Request(
        f"{BASE_URL}/api/v1/chat/credit",
        headers={"Authorization": f"Bearer {(key or '').strip()}",
                 "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        if data.get("code") == 200:
            return {"ok": True, "credits": data.get("data")}
        return {"ok": False, "error": str(data.get("msg") or data)[:150]}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"HTTP {exc.code} — key rejected"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:150]}


# 1x1 transparent PNG — the smallest real upload imgBB will accept
_PROBE_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c626001000000ffff03000006000557bfabd40000000049"
    "454e44ae426082")


def validate_imgbb_key(key: str) -> dict:
    """imgBB has no auth-check endpoint — validate with a tiny 60s-expiry
    probe upload."""
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; '
            f'filename="probe.png"\r\n'
            f"Content-Type: image/png\r\n\r\n").encode() + _PROBE_PNG + \
        f"\r\n--{boundary}--\r\n".encode()
    url = (f"https://api.imgbb.com/1/upload?key={(key or '').strip()}"
           "&expiration=60")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "User-Agent": "shorts-lab/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        if data.get("success"):
            return {"ok": True}
        return {"ok": False,
                "error": str((data.get("error") or {}).get("message")
                             or data)[:150]}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:120]
        return {"ok": False, "error": f"HTTP {exc.code}: {detail}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:150]}


# ---------------------------------------------------------------------------
# Full model catalog — capabilities drive the Advanced studio UI and the
# backend gating (the instance's grok image model does IMAGES ONLY; every
# video/audio job below requires KIE). Contract per model verified against
# the ad-builder kit's reference.md (docs.kie.ai; marketplace strings
# evolve — surface errors verbatim so drift is visible).
# ---------------------------------------------------------------------------

MODELS = {
    # -- video: unified jobs endpoint --------------------------------------
    "bytedance/seedance-2": {
        "label": "Seedance 2.0", "type": "video", "family": "jobs",
        "audio": True, "durations": list(range(4, 16)),
        "ratios": ["16:9", "9:16", "1:1"], "i2v": True,
        "note": "Flagship: UGC, reveal, hero, lookbook, walkthrough. "
                "Native audio."},
    "bytedance/seedance-2-fast": {
        "label": "Seedance 2.0 Fast", "type": "video", "family": "jobs",
        "audio": True, "durations": list(range(4, 16)),
        "ratios": ["16:9", "9:16", "1:1"], "i2v": True,
        "note": "Cheaper/faster Seedance for iteration."},
    "bytedance/seedance-1.5-pro": {
        "label": "Seedance 1.5 Pro", "type": "video", "family": "jobs",
        "audio": True, "durations": list(range(4, 13)),
        "ratios": ["16:9", "9:16", "1:1"], "i2v": True,
        "note": "Legacy Seedance Pro."},
    "sora-2-text-to-video": {
        "label": "Sora 2", "type": "video", "family": "jobs",
        "audio": True, "durations": [4, 8, 12, 16, 20],
        "ratios": ["16:9", "9:16"], "i2v": False,
        "note": "Long-duration text-to-video (up to 20s)."},
    "sora-2-pro-text-to-video": {
        "label": "Sora 2 Pro", "type": "video", "family": "jobs",
        "audio": True, "durations": [4, 8, 12, 16, 20],
        "ratios": ["16:9", "9:16"], "i2v": False,
        "note": "Premium tier for hero pieces."},
    "sora-2-image-to-video": {
        "label": "Sora 2 image-to-video", "type": "video", "family": "jobs",
        "audio": True, "durations": [4, 8, 12, 16, 20],
        "ratios": ["16:9", "9:16"], "i2v": True,
        "note": "Start a Sora video from a hosted image URL."},
    "kling-3": {
        "label": "Kling 3.0", "type": "video", "family": "jobs",
        "audio": False, "durations": [5, 10],
        "ratios": ["16:9", "9:16", "1:1"], "i2v": True,
        "note": "Cinematic b-roll / scene clips (no dialogue track)."},
    # -- video: dedicated Veo endpoint -------------------------------------
    "veo3_fast": {
        "label": "Veo 3.1 Fast", "type": "video", "family": "veo",
        "audio": True, "durations": [8],
        "ratios": ["16:9", "9:16"], "i2v": True,
        "note": "The ONLY Veo model that supports REFERENCE_2_VIDEO."},
    "veo3": {
        "label": "Veo 3.1", "type": "video", "family": "veo",
        "audio": True, "durations": [8],
        "ratios": ["16:9", "9:16"], "i2v": False,
        "note": "TEXT_2_VIDEO and first+last-frame transitions."},
    "veo3_lite": {
        "label": "Veo 3.1 Lite", "type": "video", "family": "veo",
        "audio": True, "durations": [8],
        "ratios": ["16:9", "9:16"], "i2v": False,
        "note": "Budget Veo tier."},
    # -- image: unified jobs endpoint --------------------------------------
    "nano-banana-2": {
        "label": "Nano Banana 2", "type": "image", "family": "jobs",
        "audio": False, "refs_max": 14,
        "ratios": ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
                   "9:16", "16:9", "21:9", "auto"],
        "note": "Default image model: UGC stills, character sheets, "
                "product shots."},
    "nano-banana-pro": {
        "label": "Nano Banana Pro", "type": "image", "family": "jobs",
        "audio": False, "refs_max": 14,
        "ratios": ["1:1", "2:3", "3:2", "4:5", "9:16", "16:9", "auto"],
        "note": "Gemini 3 Pro Image — locks character identity tighter."},
    "google/nano-banana-edit": {
        "label": "Nano Banana Edit", "type": "image", "family": "jobs",
        "audio": False, "refs_max": 14,
        "ratios": ["auto", "1:1", "9:16", "16:9"],
        "note": "Inpaint / edit an existing image (image_urls)."},
    # -- image: dedicated gpt4o endpoint -----------------------------------
    "gpt4o-image": {
        "label": "ChatGPT Image 2", "type": "image", "family": "gpt4o",
        "audio": False, "refs_max": 5,
        "ratios": ["1:1", "3:2", "2:3"],
        "note": "Typography / UI-mimicry creatives; Pixar + claymation "
                "storyboards."},
}

VEO_MODES = ("TEXT_2_VIDEO", "REFERENCE_2_VIDEO",
             "FIRST_AND_LAST_FRAMES_2_VIDEO")


def model_info(model: str) -> dict:
    m = MODELS.get(model)
    if not m:
        raise RuntimeError(f"unknown KIE model: {model}")
    return m


def _log_call(model: str, task_id: str, kind: str, extra: dict = None):
    """Append-only generation log (kit convention: model + task + timing,
    NEVER prompts or keys). Powers the Advanced panel's log section."""
    try:
        row = {"at": time.time(), "model": model, "taskId": task_id,
               "kind": kind}
        if extra:
            row.update(extra)
        log = store.data_dir() / "kie-api.jsonl"
        with open(log, "a") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception:  # noqa: BLE001 — logging must never break a job
        pass


def recent_log(limit: int = 40) -> list:
    try:
        lines = (store.data_dir() / "kie-api.jsonl").read_text().splitlines()
    except OSError:
        return []
    out = []
    for ln in lines[-limit:]:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return list(reversed(out))


def _post_with_backoff(url: str, body: dict, timeout: int = 60) -> dict:
    """POST with the kit's 429 discipline (20 req / 10s account limit)."""
    for attempt in range(3):
        try:
            return _post_json(url, body, timeout=timeout)
        except RuntimeError as exc:
            if "429" in str(exc) and attempt < 2:
                time.sleep(4 + attempt * 5)
                continue
            raise
    raise RuntimeError("KIE rate limit persisted")


def _task_id_from(resp: dict) -> str:
    data = resp.get("data") or {}
    task_id = data.get("taskId") or resp.get("taskId")
    code = resp.get("code")
    if code is not None and code != 200:
        raise RuntimeError(f"KIE submit code={code}: "
                           f"{resp.get('msg') or resp}")
    if not task_id:
        raise RuntimeError(f"KIE submit returned no taskId: {resp}")
    return task_id


def submit_video(model: str, prompt: str, aspect_ratio: str = "9:16",
                 duration: Optional[int] = None,
                 image_urls: Optional[list] = None,
                 veo_mode: str = "") -> dict:
    """Create a video task on any catalog model. Returns
    {taskId, family} — the family picks the poll endpoint."""
    info = model_info(model)
    if info["type"] != "video":
        raise RuntimeError(f"{model} is not a video model")
    refs = [u for u in (image_urls or []) if u]

    if info["family"] == "veo":
        mode = (veo_mode or "").strip() or (
            "REFERENCE_2_VIDEO" if len(refs) == 1 else
            "FIRST_AND_LAST_FRAMES_2_VIDEO" if len(refs) == 2 else
            "TEXT_2_VIDEO")
        if mode not in VEO_MODES:
            raise RuntimeError(f"veo mode must be one of {VEO_MODES}")
        if mode == "REFERENCE_2_VIDEO":
            if model != "veo3_fast":
                raise RuntimeError(
                    "REFERENCE_2_VIDEO only supports veo3_fast")
            if len(refs) != 1:
                raise RuntimeError("REFERENCE_2_VIDEO needs exactly 1 "
                                   "image URL")
        if mode == "FIRST_AND_LAST_FRAMES_2_VIDEO" and len(refs) != 2:
            raise RuntimeError("FIRST_AND_LAST_FRAMES_2_VIDEO needs "
                               "exactly 2 image URLs (start, end)")
        body = {"prompt": prompt, "model": model, "generationType": mode,
                "aspect_ratio": aspect_ratio or "16:9",
                "enableTranslation": True}
        if refs and mode != "TEXT_2_VIDEO":
            body["imageUrls"] = refs
        resp = _post_with_backoff(f"{BASE_URL}/api/v1/veo/generate", body)
        task_id = _task_id_from(resp)
        _log_call(model, task_id, "video", {"mode": mode})
        return {"taskId": task_id, "family": "veo"}

    inputs: dict = {"prompt": prompt,
                    "aspect_ratio": aspect_ratio or "9:16"}
    if duration:
        durs = info.get("durations") or []
        if durs and duration not in durs:
            duration = min(durs, key=lambda d: abs(d - duration))
        inputs["duration"] = duration
    if refs:
        if not info.get("i2v"):
            raise RuntimeError(f"{info['label']} is text-to-video only — "
                               "drop the reference image or switch model")
        inputs["image_urls"] = refs
    resp = _post_with_backoff(f"{BASE_URL}/api/v1/jobs/createTask",
                              {"model": model, "input": inputs})
    task_id = _task_id_from(resp)
    _log_call(model, task_id, "video", {"duration": duration})
    return {"taskId": task_id, "family": "jobs"}


def submit_gpt4o_image(prompt: str, size: str = "1:1",
                       files_url: Optional[list] = None) -> dict:
    """ChatGPT Image 2 via the dedicated /gpt4o-image endpoint (the kit's
    typography/UI-mimicry + storyboard generator). Up to 5 reference URLs."""
    if size not in ("1:1", "3:2", "2:3"):
        raise RuntimeError("gpt4o-image sizes are 1:1, 3:2, 2:3")
    body = {"prompt": prompt + NO_CHROME_SUFFIX + GLYPH_SUFFIX,
            "size": size}
    refs = [u for u in (files_url or []) if u][:5]
    if refs:
        body["filesUrl"] = refs
    resp = _post_with_backoff(f"{BASE_URL}/api/v1/gpt4o-image/generate",
                              body)
    task_id = _task_id_from(resp)
    _log_call("gpt4o-image", task_id, "image")
    return {"taskId": task_id, "family": "gpt4o"}


def submit_jobs_image(model: str, prompt: str, aspect_ratio: str = "1:1",
                      image_input: Optional[list] = None,
                      resolution: str = "1K") -> dict:
    """Catalog image models on the jobs endpoint (nano-banana family) with
    the full reference set (up to 14 URLs)."""
    info = model_info(model)
    if info["type"] != "image" or info["family"] != "jobs":
        raise RuntimeError(f"{model} is not a jobs-endpoint image model")
    refs = [u for u in (image_input or []) if u][:info.get("refs_max", 14)]
    inputs = {"prompt": prompt + NO_CHROME_SUFFIX + GLYPH_SUFFIX,
              "aspect_ratio": aspect_ratio or "auto",
              "resolution": resolution, "output_format": "png"}
    if refs:
        key = "image_urls" if model == "google/nano-banana-edit" \
            else "image_input"
        inputs[key] = refs
    resp = _post_with_backoff(f"{BASE_URL}/api/v1/jobs/createTask",
                              {"model": model, "input": inputs})
    task_id = _task_id_from(resp)
    _log_call(model, task_id, "image")
    return {"taskId": task_id, "family": "jobs"}


def check_any(task_id: str, family: str = "jobs") -> dict:
    """Poll any task family. Returns {state, url?, urls?, error?} with
    state normalized to waiting|generating|success|fail."""
    if family == "jobs":
        return check_task(task_id)
    if family == "veo":
        resp = _get_json(f"{BASE_URL}/api/v1/veo/record-info"
                         f"?taskId={task_id}")
        data = resp.get("data") or {}
        flag = data.get("successFlag")
        if flag == 1:
            urls = ((data.get("response") or {}).get("resultUrls")) or []
            if not urls:
                return {"state": "fail", "error": "veo success but no URLs"}
            return {"state": "success", "url": urls[0], "urls": urls}
        if flag in (2, 3):
            return {"state": "fail",
                    "error": str(data.get("errorMessage")
                                 or "veo generation failed")[:300]}
        return {"state": "generating"}
    if family == "gpt4o":
        resp = _get_json(f"{BASE_URL}/api/v1/gpt4o-image/record-info"
                         f"?taskId={task_id}")
        data = resp.get("data") or {}
        flag = data.get("successFlag")
        if flag == 1:
            info = data.get("response") or data
            urls = (info.get("resultUrls") or info.get("result_urls")
                    or info.get("urls") or [])
            if isinstance(urls, str):
                try:
                    urls = json.loads(urls)
                except ValueError:
                    urls = [urls]
            if not urls:
                return {"state": "fail",
                        "error": "gpt4o success but no URLs"}
            return {"state": "success", "url": urls[0], "urls": urls}
        if flag in (2, 3):
            return {"state": "fail",
                    "error": str(data.get("errorMessage")
                                 or "gpt4o generation failed")[:300]}
        return {"state": "generating"}
    raise RuntimeError(f"unknown task family: {family}")


def refresh_download_url(temp_url: str) -> str:
    """KIE temp files (~24h) — mint a fresh link when one expires."""
    resp = _post_json(f"{BASE_URL}/api/v1/common/download-url",
                      {"url": temp_url})
    data = resp.get("data")
    if isinstance(data, str) and data.startswith("http"):
        return data
    if isinstance(data, dict) and data.get("url"):
        return data["url"]
    raise RuntimeError(f"download-url refresh failed: {str(resp)[:150]}")
