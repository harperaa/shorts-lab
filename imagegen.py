"""Image-generation backend selection for Ads Lab.

Two backends:
  hermes  the instance's own loaded image model (hermes' FAL-backed
          image_generate tool — grok-era instances ship FLUX/nano-banana-pro/
          gpt-image via FAL or the managed gateway). Synchronous; local
          assets ride as data URIs, so NO imgBB hosting is needed.
  kie     KIE.ai jobs (async tasks) — the original path; needs imgBB for
          local assets.

Selection: explicit toggle (kv "imageBackend": hermes|kie), else auto —
hermes when an image model is loaded, else KIE.
"""
from __future__ import annotations

import base64
import json
import logging
import mimetypes

try:
    from . import store
except ImportError:  # loaded outside package context
    import store  # type: ignore

logger = logging.getLogger(__name__)


def hermes_status() -> dict:
    """Is the instance's own image model usable, and what is it?"""
    try:
        from tools.image_generation_tool import (
            _resolve_fal_model,
            check_fal_api_key,
        )
        available = bool(check_fal_api_key())
        model_id, meta = _resolve_fal_model()
        return {
            "available": available,
            "model": meta.get("display") or model_id,
            "canEdit": bool(meta.get("edit_endpoint")),
        }
    except Exception:  # noqa: BLE001 — hermes internals absent (tests)
        return {"available": False, "model": None, "canEdit": False}


def get_backend() -> str:
    """hermes | kie — explicit choice wins; auto prefers the loaded model."""
    choice = store.kv_get("imageBackend")
    if choice in ("hermes", "kie"):
        if choice == "hermes" and not hermes_status()["available"]:
            return "kie"       # model got unloaded — fail safe to KIE
        return choice
    return "hermes" if hermes_status()["available"] else "kie"


def set_backend(backend: str) -> None:
    if backend not in ("hermes", "kie", "auto"):
        raise ValueError("backend must be hermes, kie, or auto")
    if backend == "auto":
        store.kv_set("imageBackend", None)
    else:
        store.kv_set("imageBackend", backend)


def asset_data_uri(asset_id: str) -> str:
    """Local asset -> data URI (FAL accepts these; no public hosting)."""
    path = store.assets_dir() / asset_id
    if not path.exists():
        raise RuntimeError(f"asset {asset_id} not found")
    payload = path.read_bytes()
    if len(payload) > 10 * 1024 * 1024:
        raise RuntimeError("asset too large for inline upload (10 MB max)")
    mime = mimetypes.guess_type(asset_id)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(payload).decode()}"


def hermes_generate(prompt: str, source_url: str | None = None,
                    ref_urls: list | None = None,
                    aspect_ratio: str = "1:1") -> str:
    """Run one generation on the instance's image model. SYNCHRONOUS —
    returns the finished image URL or raises with the tool's error."""
    from tools.image_generation_tool import image_generate_tool

    refs = [u for u in (ref_urls or []) if u]
    raw = image_generate_tool(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        image_url=source_url or None,
        reference_image_urls=refs or None,
    )
    out = json.loads(raw)
    if not out.get("success") or not out.get("image"):
        raise RuntimeError(str(out.get("error")
                               or "image generation failed")[:300])
    return out["image"]
