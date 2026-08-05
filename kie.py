"""KIE.ai client — distilled from the ad-builder kit's Nano Banana generator
(Kruse Media LLC / AI Cyber Sherpas LLC, MIT). stdlib urllib only.

Facts (verified against the kit + docs.kie.ai):
- POST /api/v1/jobs/createTask  {"model": ..., "input": {...}} -> taskId
- GET  /api/v1/jobs/recordInfo?taskId=...  -> state, resultJson (JSON string)
  containing resultUrls
- Bearer KIE_API_KEY; reference images must be PUBLIC URLs (no upload flow),
  so local assets are hosted via 0x0.st (the kit's recommended temp host)
  just long enough for KIE to fetch them.
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
IMAGE_MODEL = "nano-banana-2"        # fresh generation
EDIT_MODEL = "nano-banana-edit"      # source image + style refs

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
                        "image_input": [source_url] + refs}
    else:
        model = IMAGE_MODEL
        inputs = {"prompt": final_prompt, "aspect_ratio": aspect_ratio}
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
    """Push a stored asset to 0x0.st (the kit's recommended temp host) so
    KIE can fetch it; returns the public URL. Cached per asset."""
    cache = store.kv_get("hostedAssets") or {}
    if asset_id in cache:
        return cache[asset_id]
    path = store.assets_dir() / asset_id
    if not path.exists():
        raise RuntimeError(f"asset {asset_id} not found")
    payload = path.read_bytes()
    boundary = uuid.uuid4().hex
    ctype = mimetypes.guess_type(asset_id)[0] or "image/jpeg"
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; '
            f'filename="{asset_id}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n").encode() + payload + \
        f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        "https://0x0.st", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "User-Agent": "shorts-lab/1.0 (hermes plugin)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        url = resp.read().decode().strip()
    if not url.startswith("http"):
        raise RuntimeError(f"asset hosting failed: {url[:200]}")
    cache[asset_id] = url
    store.kv_set("hostedAssets", cache)
    return url
