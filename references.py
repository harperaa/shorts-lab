"""Reference image library — influencers, products, aesthetics, examples.

Mirrors the ad-builder repo's `references/` convention (see kieref):
  influencers/<name-descriptors>/  10-angle AI character sheets
  products/                        product photos
  aesthetics/<vibe>/               style references (ugc-selfie, ...)
  examples/                        finished-output examples

Files live under plugins-data/shorts-lab/references/ and are served by the
plugin API (GET /reference/{path}). The starter pack imports the public
repo's shipped reference set. Images below the KIE 1024px floor are
auto-upscaled (Lanczos, RGB JPEG) on ingest, matching the repo's spec.
"""
from __future__ import annotations

import io
import re
import time

import requests

try:
    from . import store
except ImportError:  # loaded outside package context
    import store  # type: ignore

FOLDERS = ("influencers", "products", "aesthetics", "examples")
_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_MAX_BYTES = 30 * 1024 * 1024          # KIE's per-image ceiling

_REPO_RAW = ("https://raw.githubusercontent.com/krusemediallc/"
             "claude-code-ai-ad-builder-kie-ai/main/references/")


def root():
    p = store.data_dir() / "references"
    for f in FOLDERS:
        (p / f).mkdir(parents=True, exist_ok=True)
    return p


def _safe_rel(rel: str) -> str:
    rel = (rel or "").strip().strip("/")
    if not rel or ".." in rel or rel.startswith("/") or "\\" in rel:
        raise ValueError("bad reference path")
    top = rel.split("/", 1)[0]
    if top not in FOLDERS:
        raise ValueError(f"folder must be one of {', '.join(FOLDERS)}")
    if not re.fullmatch(r"[A-Za-z0-9._ ()\[\]/-]+", rel):
        raise ValueError("reference path has unsupported characters")
    return rel


def path_for(rel: str):
    return root() / _safe_rel(rel)


def _upscale_if_small(payload: bytes) -> bytes:
    """KIE rejects tiny inputs: below 1024px longest side, upscale to
    1080px with Lanczos and re-encode RGB JPEG (repo spec). Fails open."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(payload))
        longest = max(img.size)
        if longest >= 1024:
            return payload
        scale = 1080 / float(longest)
        img = img.convert("RGB").resize(
            (round(img.size[0] * scale), round(img.size[1] * scale)),
            Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=92)
        return out.getvalue()
    except Exception:  # noqa: BLE001
        return payload


def save(rel_dir: str, filename: str, payload: bytes) -> str:
    """Store one reference image; returns the library-relative path."""
    rel_dir = _safe_rel(rel_dir)
    name = (filename or "image.jpg").strip().replace("/", "-")
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext not in _EXTS:
        raise RuntimeError("only jpg/png/webp reference images")
    if len(payload) > _MAX_BYTES:
        raise RuntimeError("reference image exceeds 30 MB")
    payload = _upscale_if_small(payload)
    if _upscaled_is_jpeg(payload) and ext not in (".jpg", ".jpeg"):
        name = name.rsplit(".", 1)[0] + ".jpg"
    dest = root() / rel_dir / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    return f"{rel_dir}/{name}"


def _upscaled_is_jpeg(payload: bytes) -> bool:
    return payload[:3] == b"\xff\xd8\xff"


def delete(rel: str) -> None:
    p = path_for(rel)
    if p.is_file():
        p.unlink()


def tree() -> dict:
    """Full library listing: folder -> [{path, name, group}]."""
    out = {}
    base = root()
    for folder in FOLDERS:
        rows = []
        fp = base / folder
        for p in sorted(fp.rglob("*")):
            if p.is_file() and p.suffix.lower() in _EXTS:
                rel = p.relative_to(base).as_posix()
                group = p.parent.relative_to(fp).as_posix()
                rows.append({"path": rel, "name": p.name,
                             "group": "" if group == "." else group})
        out[folder] = rows
    return out


# ---------------------------------------------------------------------------
# Starter pack — the public repo's shipped reference set
# ---------------------------------------------------------------------------

# One representative, useful subset per area: every influencer's hero +
# closeup + full-body (identity lock needs multiple angles; the full
# 10-angle sheets stay one click away in the repo), all products, the
# ugc-selfie aesthetic frames, and the finished-still examples.
_INFLUENCERS = [
    "astrid-blonde-bob-high-cheeks-gray-eyes-porcelain",
    "emma-redhead-wavy-freckles-green-eyes-fair",
    "finn-auburn-wavy-freckles-blue-eyes-fair",
    "jayden-brunette-curtain-sharp-jaw-brown-eyes-tan",
    "kai-black-hair-curly-fade-strong-brow-brown-eyes-deep",
    "lena-brunette-long-straight-beauty-mark-brown-eyes-fair",
    "marcus-black-hair-buzz-sharp-jaw-brown-eyes-deep",
    "mila-honey-brown-curly-beauty-mark-green-eyes-tan",
    "nico-brunette-wavy-stubble-green-eyes-olive",
    "priya-black-hair-long-wavy-dimples-brown-eyes-medium",
    "raven-black-hair-choppy-layers-nose-stud-brown-eyes-porcelain",
    "sofia-black-hair-long-straight-dimples-hazel-eyes-olive",
    "zara-black-hair-braids-high-cheeks-brown-eyes-deep",
]
_INFLUENCER_ANGLES = ["01-hero-front.jpg", "06-face-closeup.jpg",
                      "09-full-body-3q.jpg"]
_AESTHETICS = [f"ugc-selfie/videoframe_{n}.jpg"
               for n in (4268, 4516, 5451, 9922, 11833)]
_EXAMPLES = ["ugc-stills/astrid-bathroom-skincare.jpg",
             "ugc-stills/finn-bathroom-cola.jpg",
             "ugc-stills/lena-desk-gummies.jpg",
             "ugc-stills/nico-car-gold-cola.jpg",
             "ugc-stills/priya-kitchen-coffee.jpg"]


def starter_manifest() -> list:
    items = []
    for inf in _INFLUENCERS:
        for angle in _INFLUENCER_ANGLES:
            items.append(f"influencers/{inf}/{angle}")
    items += [f"aesthetics/{a}" for a in _AESTHETICS]
    items += [f"examples/{e}" for e in _EXAMPLES]
    return items


def import_starter_pack(http_get=None) -> dict:
    """Pull the repo's reference set into the local library (skips files
    already present). Returns {imported, skipped, errors}."""
    get = http_get or (lambda url: requests.get(url, timeout=60))
    base = root()
    imported, skipped, errors = 0, 0, []
    for rel in starter_manifest():
        dest = base / rel
        if dest.exists():
            skipped += 1
            continue
        try:
            r = get(_REPO_RAW + rel.replace(" ", "%20"))
            if getattr(r, "status_code", 0) != 200:
                errors.append(f"{rel}: HTTP {getattr(r, 'status_code', '?')}")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            imported += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{rel}: {str(exc)[:80]}")
    store.kv_set("referencesImport",
                 {"at": time.time(), "imported": imported,
                  "skipped": skipped, "errors": errors[:10]})
    return {"imported": imported, "skipped": skipped, "errors": errors[:10]}
