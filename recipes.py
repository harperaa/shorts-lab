"""Advanced-studio recipes — the ad-builder kit's workflows as one engine.

Each recipe grounds its LLM prompt-building in the bundled kieref guide
text, then dispatches to the right KIE surface (jobs / veo / gpt4o) or the
instance image backend where capabilities allow. Media rules:

  images  — instance model (grok imagine, FAL, ...) OR KIE, per the
            existing Ads Lab generator toggle
  video / audio — KIE ONLY. The instance-side grok image model cannot
            produce video or sound; recipes below enforce that server-side.

Pipelines (character sheet, pixar, claymation) follow the kit's sequenced
identity-lock pattern: each storyboard frame carries the prior frame (and
cast sheet) as reference URLs.
"""
from __future__ import annotations

import json
import threading
import time

try:
    from . import store, kie, analysis, references
    from .kieref import loader as kiedocs
except ImportError:  # loaded outside package context
    import store, kie, analysis, references  # type: ignore
    from kieref import loader as kiedocs  # type: ignore


# ---------------------------------------------------------------------------
# Catalog (drives the Advanced panel UI)
# ---------------------------------------------------------------------------

CATALOG = [
    # -- stills -------------------------------------------------------------
    {"id": "ugc-selfie", "name": "UGC product selfie", "emoji": "🤳",
     "media": "image", "kind": "single",
     "desc": "Authentic iPhone-selfie frame: your character holding the "
             "product, ugc-selfie aesthetic refs fighting the polished-AI "
             "default.",
     "refs": ["character", "product", "aesthetic"]},
    {"id": "product-showcase", "name": "Product showcase still", "emoji": "🛍️",
     "media": "image", "kind": "single",
     "desc": "AI person interacting with your product — the approved still "
             "becomes a video starting frame.",
     "refs": ["product", "character"]},
    {"id": "youtube-thumbnail", "name": "YouTube thumbnails", "emoji": "🖼️",
     "media": "image", "kind": "batch",
     "desc": "5 CTR formulas (peace-sign, real-vs-AI, terminal, reaction "
             "shock, before/after) fired as parallel variants.",
     "refs": ["character"]},
    {"id": "image-ad-template", "name": "Image ad (37-template library)",
     "emoji": "🗂️", "media": "image", "kind": "single",
     "desc": "Apple-Notes lists, editorial hero, comparison tables, fake "
             "Slack threads, iMessage, magazine covers... typography "
             "templates run on ChatGPT Image 2, photoreal on Nano Banana.",
     "refs": ["product"]},
    {"id": "influencer-recreation", "name": "Recreate an influencer look",
     "emoji": "🪞", "media": "image", "kind": "single",
     "desc": "Rebuild a look from a reference photo into a reusable still.",
     "refs": ["character"]},
    # -- video (KIE ONLY) ---------------------------------------------------
    {"id": "seedance-ugc", "name": "Seedance UGC review", "emoji": "📱",
     "media": "video", "kind": "video", "model": "bytedance/seedance-2",
     "desc": "9-layer UGC formula: iPhone aesthetic, natural eye-contact "
             "breaks, casual delivery. Native audio.",
     "refs": ["character", "product"]},
    {"id": "seedance-premium-reveal", "name": "Premium product reveal",
     "emoji": "🖤", "media": "video", "kind": "video",
     "model": "bytedance/seedance-2",
     "desc": "Dark void, text narrative, hero rotation — no person.",
     "refs": ["product"]},
    {"id": "seedance-product-hero", "name": "Product hero (elemental)",
     "emoji": "💦", "media": "video", "kind": "video",
     "model": "bytedance/seedance-2",
     "desc": "Splash, mist, light rays, slow rotation.",
     "refs": ["product"]},
    {"id": "seedance-lookbook", "name": "Studio lookbook + VO", "emoji": "🎙️",
     "media": "video", "kind": "video", "model": "bytedance/seedance-2",
     "desc": "Polished multi-look editorial with embedded voiceover.",
     "refs": ["product"]},
    {"id": "seedance-walkthrough", "name": "Feature walkthrough",
     "emoji": "⚙️", "media": "video", "kind": "video",
     "model": "bytedance/seedance-2",
     "desc": "Fast-paced product-demo cuts.", "refs": ["product"]},
    {"id": "sora-video", "name": "Sora 2 video", "emoji": "🌀",
     "media": "video", "kind": "video", "model": "sora-2-text-to-video",
     "desc": "Long-form text-to-video up to 20s; duration auto-picked "
             "from the script (~2.5 words/sec).", "refs": []},
    {"id": "veo-video", "name": "Veo 3.1 video", "emoji": "🎥",
     "media": "video", "kind": "video", "model": "veo3_fast",
     "desc": "Animate a still (REFERENCE_2_VIDEO), transition two stills, "
             "or pure text-to-video.", "refs": ["character"]},
    {"id": "kling-broll", "name": "Kling 3.0 b-roll", "emoji": "🎞️",
     "media": "video", "kind": "video", "model": "kling-3",
     "desc": "Cinematic b-roll and scene clips.", "refs": []},
    # -- pipelines (KIE ONLY) ----------------------------------------------
    {"id": "character-sheet", "name": "New AI influencer (10-angle sheet)",
     "emoji": "🧬", "media": "image", "kind": "pipeline",
     "desc": "Two-pass: hero portrait first, then 9 angles locked to the "
             "hero. Saved into references/influencers/ for reuse.",
     "refs": []},
    {"id": "pixar", "name": "Pixar-style animated ad", "emoji": "🎬",
     "media": "video", "kind": "pipeline",
     "desc": "8-beat mascot story: ChatGPT Image 2 storyboard (sequential "
             "identity lock) → Seedance i2v per beat.",
     "refs": ["product"]},
    {"id": "claymation", "name": "Claymation ad", "emoji": "🏺",
     "media": "video", "kind": "pipeline",
     "desc": "Aardman-style 8-beat narrator arc, clay textures, optional "
             "stop-motion judder in post.", "refs": ["product"]},
    # -- tools --------------------------------------------------------------
    {"id": "analyze-video", "name": "Reverse-engineer a video",
     "emoji": "🔎", "media": "tool", "kind": "tool",
     "desc": "Extract a reference video's structure into a reusable "
             "Seedance template.", "refs": []},
    {"id": "clone-ad", "name": "Clone a video ad", "emoji": "🧪",
     "media": "tool", "kind": "tool",
     "desc": "Analyze a reference ad and adapt it to your product as a "
             "ready-to-fire prompt.", "refs": []},
]

RECIPE_IDS = {r["id"] for r in CATALOG}


def catalog() -> list:
    return CATALOG


def recipe(recipe_id: str) -> dict:
    for r in CATALOG:
        if r["id"] == recipe_id:
            return r
    raise RuntimeError(f"unknown recipe: {recipe_id}")


# ---------------------------------------------------------------------------
# Prompt building (LLM + bundled guide corpus)
# ---------------------------------------------------------------------------

_PROMPT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string",
                  "description": "short internal name for the creation"},
        "prompts": {"type": "array", "items": {"type": "string"},
                    "description": "the generation prompt(s) — exactly N, "
                                   "each complete and standalone, written "
                                   "to the guide's formula"},
        "notes": {"type": "string",
                  "description": "one sentence: which guide formula was "
                                 "applied and how"},
    },
    "required": ["title", "prompts", "notes"],
}


def build_prompts(recipe_id: str, brief: str, n: int = 1,
                  extra: str = "") -> dict:
    """Compose generation prompt(s) for a recipe, grounded in the bundled
    guide text for that recipe."""
    guide = kiedocs.guide_text(recipe_id)
    r = recipe(recipe_id)
    n = max(1, min(10, int(n or 1)))
    payload = (
        f"RECIPE: {r['name']} — {r['desc']}\n\n"
        f"USER'S BRIEF: {(brief or '').strip()[:2000]}\n"
        + (f"\nEXTRA DIRECTION: {extra.strip()[:800]}\n" if extra else "")
        + f"\nPRODUCE EXACTLY {n} prompt(s), each a complete standalone "
          "generation prompt following the guide formulas below — use the "
          "guide's structure, layer order, camera/lighting vocabulary, and "
          "realism techniques rather than inventing your own format.\n\n"
          "=== GUIDE (authoritative) ===\n" + guide[:22000])
    out = analysis._complete(
        "You compose generation prompts for ad creatives, strictly "
        "following the supplied production guide.",
        payload, _PROMPT_SCHEMA, f"recipe_{recipe_id.replace('-', '_')}",
        3000)
    prompts = [str(p) for p in (out.get("prompts") or []) if str(p).strip()]
    if not prompts:
        raise RuntimeError("recipe planner returned no prompts")
    return {"title": out.get("title") or r["name"],
            "prompts": prompts[:n] + [prompts[-1]] * max(0, n - len(prompts)),
            "notes": out.get("notes") or ""}


_TEMPLATE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "template": {"type": "string",
                     "description": "the reusable parameterized prompt "
                                    "template with {placeholders}"},
        "parameters": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
    },
    "required": ["name", "template", "parameters", "notes"],
}


def analyze_video(url: str, description: str, recipe_id: str = "analyze-video") -> dict:
    """Reverse-engineer a reference video into a reusable Seedance
    template (kit's analyze-video / clone-ad workflows). Stored in kv."""
    guide = kiedocs.guide_text(recipe_id) + "\n\n" + \
        kiedocs.guide_text("seedance-ugc")
    payload = (
        f"REFERENCE VIDEO URL: {url}\n"
        f"WHAT'S IN IT (user's description of the video, shot by shot if "
        f"they gave one): {description[:3000]}\n\n"
        "Extract the video's structure — hook mechanics, shot list, pacing, "
        "camera language, text overlays, audio style — into ONE reusable "
        "parameterized Seedance 2.0 prompt template with {placeholders} "
        "for product, person, and setting. Follow the workflow below.\n\n"
        "=== WORKFLOW GUIDE ===\n" + guide[:20000])
    out = analysis._complete(
        "You reverse-engineer reference videos into reusable, "
        "parameterized Seedance prompt templates.",
        payload, _TEMPLATE_SCHEMA, "analyze_video", 2500)
    tpl = {"name": str(out.get("name") or "Template")[:120],
           "template": str(out.get("template") or "")[:6000],
           "parameters": [str(p)[:60] for p in
                          (out.get("parameters") or [])][:12],
           "notes": str(out.get("notes") or "")[:500],
           "sourceUrl": url[:500], "at": time.time()}
    templates = store.kv_get("videoTemplates") or []
    templates.insert(0, tpl)
    store.kv_set("videoTemplates", templates[:40])
    return tpl


# ---------------------------------------------------------------------------
# Video jobs → creations
# ---------------------------------------------------------------------------

def start_video(recipe_id: str, brief: str, model: str = "",
                aspect_ratio: str = "9:16", duration: int = 0,
                ref_urls: list = None, veo_mode: str = "",
                variants: int = 1, extra: str = "") -> list:
    """Build prompts and fire video task(s). KIE ONLY — video is beyond
    the instance image backend. Returns created creation ids."""
    r = recipe(recipe_id)
    if r["media"] != "video":
        raise RuntimeError(f"{recipe_id} is not a video recipe")
    model = (model or r.get("model") or "bytedance/seedance-2").strip()
    info = kie.model_info(model)
    if info["type"] != "video":
        raise RuntimeError(f"{model} is not a video model")

    n = max(1, min(4, int(variants or 1)))
    plan = build_prompts(recipe_id, brief, n=n, extra=extra)

    # sora auto-duration from script length (~2.5 words/sec, kit rule)
    if not duration and model.startswith("sora-2"):
        words = len((brief or "").split())
        want = max(4, round(words / 2.5))
        duration = min((d for d in info["durations"]), key=lambda d: abs(d - want))

    cids = []
    for i, prompt in enumerate(plan["prompts"][:n]):
        sub = kie.submit_video(model, prompt, aspect_ratio=aspect_ratio,
                               duration=duration or None,
                               image_urls=ref_urls or [],
                               veo_mode=veo_mode)
        title = plan["title"] + (f" — take {i + 1}/{n}" if n > 1 else "")
        cid = store.create_creation(
            "video-ad", title, brief,
            f"# {title}\n\n**Recipe:** {r['name']}  \n"
            f"**Model:** {info['label']}"
            + (f" · {duration}s" if duration else "")
            + f"\n\n**Notes:** {plan['notes']}\n\n"
            f"## Generation prompt\n\n{prompt}",
            status="generating",
            source={"recipe": recipe_id, "model": model,
                    "family": sub["family"], "prompt": prompt[:4000],
                    "retries": 0})
        store.update_creation(cid, task_id=sub["taskId"])
        cids.append(cid)
    return cids


# ---------------------------------------------------------------------------
# Pipelines
# ---------------------------------------------------------------------------

def _poll_until(task_id: str, family: str, timeout_s: int = 900) -> str:
    """Server-side poll (kit cadence ~30s; we use 15s) until success.
    Returns the result URL or raises."""
    waited = 0
    while waited < timeout_s:
        tick = kie.check_any(task_id, family)
        if tick["state"] == "success":
            return tick["url"]
        if tick["state"] == "fail":
            raise RuntimeError(tick.get("error") or "generation failed")
        time.sleep(15)
        waited += 15
    raise RuntimeError("timed out waiting for KIE task")


_SHEET_ANGLES = [
    ("01-hero-front", "hero front portrait, direct eye contact"),
    ("02-3q-left", "three-quarter view from the left"),
    ("03-3q-right", "three-quarter view from the right"),
    ("04-profile-left", "full left profile"),
    ("05-profile-right", "full right profile"),
    ("06-face-closeup", "tight face close-up"),
    ("07-back-shoulder", "over-the-shoulder from behind"),
    ("08-medium-portrait", "medium portrait, waist up"),
    ("09-full-body-3q", "full body, three-quarter angle"),
    ("10-above-angle", "slightly above camera angle"),
]


def start_character_sheet(name: str, description: str) -> int:
    """Kit's two-pass influencer builder: hero first, then 9 angles with
    the hero URL as identity reference. Results land in
    references/influencers/<slug>/ AND a pipeline creation tracks it."""
    import re as _re
    slug = _re.sub(r"[^a-z0-9-]", "-", (name or "influencer").lower())
    slug = _re.sub(r"-+", "-", slug).strip("-") or "influencer"
    plan = build_prompts("character-sheet", description, n=1)
    hero_prompt = plan["prompts"][0]

    cid = store.create_creation(
        "pipeline", f"Character sheet — {slug}", description,
        f"# Character sheet — {slug}\n\n10-angle identity sheet.\n\n"
        f"**Hero prompt:** {hero_prompt}",
        status="generating",
        source={"recipe": "character-sheet", "slug": slug,
                "steps": [{"id": a, "state": "pending"}
                          for a, _ in _SHEET_ANGLES]})

    def worker():
        src = dict(store.get_creation(cid).get("source") or {})
        steps = src["steps"]
        hero_url = None
        try:
            for i, (angle_id, angle_desc) in enumerate(_SHEET_ANGLES):
                if hero_url is None:
                    prompt = hero_prompt
                    refs = []
                else:
                    prompt = (f"{hero_prompt}\n\nSame exact person as the "
                              f"reference image — identical face, hair, "
                              f"and identity. New shot: {angle_desc}.")
                    refs = [hero_url]
                sub = kie.submit_jobs_image("nano-banana-2", prompt,
                                            aspect_ratio="2:3",
                                            image_input=refs)
                url = _poll_until(sub["taskId"], sub["family"])
                if hero_url is None:
                    hero_url = url
                import urllib.request as _ur
                payload = _ur.urlopen(url, timeout=120).read()
                references.save(f"influencers/{slug}",
                                f"{angle_id}.jpg", payload)
                steps[i] = {"id": angle_id, "state": "done", "url": url}
                src["steps"] = steps
                store.update_creation(cid, source=src)
            store.update_creation(cid, status="ready",
                                  result_url=hero_url or "")
        except Exception as exc:  # noqa: BLE001
            store.update_creation(cid, status="failed",
                                  error=str(exc)[:300])

    threading.Thread(target=worker, daemon=True).start()
    return cid


def start_storyboard(recipe_id: str, brief: str, beats: int = 8,
                     ref_urls: list = None) -> int:
    """Pixar / claymation stage 1: sequential ChatGPT Image 2 storyboard,
    each beat carrying the PRIOR frame as reference (identity lock)."""
    if recipe_id not in ("pixar", "claymation"):
        raise RuntimeError("storyboard pipelines: pixar or claymation")
    beats = max(3, min(10, int(beats or 8)))
    plan = build_prompts(recipe_id, brief, n=beats)

    cid = store.create_creation(
        "pipeline", f"{recipe(recipe_id)['name']} — storyboard", brief,
        f"# {recipe(recipe_id)['name']}\n\n{beats}-beat storyboard.\n\n"
        + "\n\n".join(f"**Beat {i + 1}:** {p}"
                      for i, p in enumerate(plan["prompts"])),
        status="generating",
        source={"recipe": recipe_id,
                "steps": [{"id": f"beat-{i + 1}", "state": "pending",
                           "prompt": p[:2000]}
                          for i, p in enumerate(plan["prompts"])]})

    base_refs = [u for u in (ref_urls or []) if u]

    def worker():
        src = dict(store.get_creation(cid).get("source") or {})
        steps = src["steps"]
        prev_url = None
        first_url = None
        try:
            for i, step in enumerate(steps):
                refs = list(base_refs)
                if prev_url:
                    refs = [prev_url] + refs
                sub = kie.submit_gpt4o_image(
                    step["prompt"]
                    + ("\nSame characters and art style as the reference "
                       "frame — continue the sequence." if prev_url else ""),
                    size="3:2", files_url=refs[:5])
                url = _poll_until(sub["taskId"], sub["family"])
                prev_url = url
                first_url = first_url or url
                steps[i] = {**step, "state": "done", "url": url}
                src["steps"] = steps
                store.update_creation(cid, source=src)
            store.update_creation(cid, status="ready",
                                  result_url=first_url or "")
        except Exception as exc:  # noqa: BLE001
            store.update_creation(cid, status="failed",
                                  error=str(exc)[:300])

    threading.Thread(target=worker, daemon=True).start()
    return cid


def animate_storyboard(creation_id: int,
                       model: str = "bytedance/seedance-2") -> int:
    """Pixar / claymation stage 2: Seedance image-to-video per beat still.
    Produces one video-ad creation per beat (clips; stitch in your editor
    or via ffmpeg — the kit's restitch scripts are in kieref)."""
    c = store.get_creation(int(creation_id))
    if not c or c.get("kind") != "pipeline":
        raise RuntimeError("storyboard pipeline creation not found")
    src = dict(c.get("source") or {})
    steps = [s for s in (src.get("steps") or [])
             if s.get("state") == "done" and s.get("url")]
    if not steps:
        raise RuntimeError("no finished storyboard frames to animate")
    guide = kiedocs.guide_text(src.get("recipe") or "pixar")
    made = 0
    for i, step in enumerate(steps):
        motion = (f"Animate this storyboard frame (beat {i + 1}). "
                  f"{step.get('prompt', '')[:600]} "
                  "Subtle camera move, natural secondary motion, keep "
                  "characters and style identical to the frame.")
        sub = kie.submit_video(model, motion, aspect_ratio="16:9",
                               duration=5, image_urls=[step["url"]])
        vcid = store.create_creation(
            "video-ad", f"{c['title']} — beat {i + 1} clip",
            c.get("brief") or "",
            f"# Beat {i + 1} clip\n\nAnimated from the storyboard frame.\n\n"
            f"{motion}",
            status="generating",
            source={"recipe": src.get("recipe"), "model": model,
                    "family": sub["family"], "parentId": c["id"],
                    "retries": 0})
        store.update_creation(vcid, task_id=sub["taskId"])
        made += 1
    _ = guide  # guide text reserved for future per-beat motion planning
    return made
