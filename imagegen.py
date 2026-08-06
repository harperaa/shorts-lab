"""Image-generation backend selection for Ads Lab.

Two backends:
  hermes  whatever image model the instance itself has loaded — resolved
          exactly the way hermes' own image_generate tool resolves it:
          the configured plugin provider (xAI Grok Imagine, OpenAI
          gpt-image, OpenRouter, Krea, DeepInfra, ...) when
          image_gen.provider is set, else the in-tree FAL catalog when a
          FAL key / managed gateway is present. Synchronous; local
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
    """Is the instance's own image model usable, and which one is it?

    Mirrors hermes' own resolution: availability covers both the FAL
    path AND an explicitly configured plugin provider (image_gen.provider
    in config.yaml — set via `hermes tools` → Image Generation), so a
    grok-only or gpt-image-only instance reports its model here.
    """
    try:
        from tools.image_generation_tool import (
            _active_image_capabilities,
            check_image_generation_requirements,
        )
        caps = _active_image_capabilities()
        return {
            "available": bool(check_image_generation_requirements()),
            "provider": caps.get("provider") or None,
            "model": caps.get("model") or None,
            "canEdit": "image" in (caps.get("modalities") or []),
        }
    except Exception:  # noqa: BLE001 — hermes internals absent (tests)
        return {"available": False, "provider": None, "model": None,
                "canEdit": False}


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
    """Local asset -> data URI (image backends accept these; no hosting)."""
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
    """Run one generation on the instance's image model. SYNCHRONOUS.

    Routing mirrors hermes' _handle_image_generate: configured plugin
    provider first (xAI / OpenAI / ...), then the FAL path. Returns the
    result image — a URL for FAL, usually a LOCAL FILE PATH for plugin
    providers (they save to $HERMES_HOME/cache/images/) — or raises.
    """
    from tools import image_generation_tool as it

    refs = [u for u in (ref_urls or []) if u]
    kwargs = dict(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        image_url=(source_url or None),
        reference_image_urls=(refs or None),
    )
    raw = it._dispatch_to_plugin_provider(
        prompt, aspect_ratio, image_url=kwargs["image_url"],
        reference_image_urls=kwargs["reference_image_urls"])
    if raw is None and hasattr(it, "_maybe_route_managed_krea"):
        raw = it._maybe_route_managed_krea(
            prompt, aspect_ratio, image_url=kwargs["image_url"],
            reference_image_urls=kwargs["reference_image_urls"])
    if raw is None:
        raw = it.image_generate_tool(**kwargs)
    out = json.loads(raw)
    if not out.get("success") or not out.get("image"):
        raise RuntimeError(str(out.get("error")
                               or "image generation failed")[:300])
    return str(out["image"])


def import_result(image: str) -> tuple:
    """Normalize a generation result for the dashboard.

    Returns (public_url, spellcheck_url). Remote URLs pass through
    unchanged; a local file path (plugin providers save to the hermes
    cache) is copied into the plugin's asset store and served from the
    plugin API, with a data URI for the vision spellcheck.
    """
    if image.startswith(("http://", "https://", "data:")):
        return image, image
    from pathlib import Path

    try:
        from . import kie
    except ImportError:
        import kie  # type: ignore
    p = Path(image)
    if not p.exists():
        raise RuntimeError(f"generated image not found at {image}")
    aid = kie.save_asset(p.name, p.read_bytes())
    return f"/api/plugins/shorts-lab/asset/{aid}", asset_data_uri(aid)
