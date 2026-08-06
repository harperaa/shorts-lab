"""shorts-lab analysis — the marketing brain.

Grounded in the digital-marketing-pro skill pack baked into the mentee image
(video-script, social-strategy, creative-testing-framework): relevant skill
excerpts ride into every prompt so the analysis speaks the same frameworks
the rest of the platform teaches. Runs on the host LLM via PluginLlm.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

try:
    from . import store
except ImportError:  # loaded outside package context
    import store  # type: ignore

logger = logging.getLogger(__name__)

PLUGIN_ID = "shorts-lab"
_MARKETING_SKILLS = ("video-script", "social-strategy",
                     "creative-testing-framework")
_SKILL_EXCERPT_CHARS = 2200


def _llm():
    from agent.plugin_llm import PluginLlm
    return PluginLlm(plugin_id=PLUGIN_ID)


def _complete(instructions: str, payload: str, schema: dict,
              name: str, max_tokens: int) -> dict:
    import re
    res = _llm().complete_structured(
        instructions=instructions,
        input=[{"type": "text", "text": payload}],
        json_schema=schema,
        schema_name=name,
        temperature=0.4,
        max_tokens=max_tokens,
        timeout=240,
        purpose=f"shorts-lab-{name}",
    )
    parsed = getattr(res, "parsed", None)
    if parsed is None:
        raw = getattr(res, "text", "") or ""
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                parsed = None
    if not isinstance(parsed, dict):
        raise RuntimeError("the model returned no usable analysis — try again")
    return parsed


def _skill_dirs() -> list[Path]:
    dirs = [Path("/opt/hermes/plugins/digital-marketing-pro/skills"),
            store._home() / "plugins" / "digital-marketing-pro" / "skills"]
    extra = os.environ.get("SHORTS_LAB_SKILLS_DIR")
    if extra:
        dirs.insert(0, Path(extra))
    return dirs


def marketing_context() -> str:
    """Excerpts from the marketing skill pack, when installed."""
    chunks = []
    for base in _skill_dirs():
        if not base.is_dir():
            continue
        for name in _MARKETING_SKILLS:
            doc = base / name / "SKILL.md"
            try:
                text = doc.read_text()[:_SKILL_EXCERPT_CHARS]
                chunks.append(f"### {name}\n{text}")
            except OSError:
                continue
        if chunks:
            break
    if not chunks:
        return ""
    return ("\n\nMARKETING FRAMEWORKS (from the platform's skill pack — "
            "apply these):\n" + "\n\n".join(chunks))


# ---------------------------------------------------------------------------
# Shorts Research: what's winning
# ---------------------------------------------------------------------------

_SHORTS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string",
                    "description": "3-4 sentence read of the competitive landscape"},
        "channels": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "whatIsWorking": {"type": "string",
                                  "description": "2-3 sentences on this channel's winning play"},
                "hookStyle": {"type": "string"},
                "format": {"type": "string",
                           "description": "talking head / b-roll / screen capture / skit / listicle etc."},
            },
            "required": ["channel", "whatIsWorking", "hookStyle", "format"]}},
        "winningHooks": {"type": "array", "items": {"type": "string"},
                         "description": "5-10 hook patterns seen in the highest-view shorts, quoted or paraphrased with view counts"},
        "winningMessages": {"type": "array", "items": {"type": "string"},
                            "description": "recurring messages/angles that pull views"},
        "winningFormats": {"type": "array", "items": {"type": "string"},
                           "description": "structures + pacing that win (e.g. 'cold-open claim, 3 rapid proofs, CTA at 80%')"},
        "winningStyles": {"type": "array", "items": {"type": "string"},
                          "description": "visual/delivery styles that win (captions style, energy, cuts)"},
        "topShorts": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "videoId": {"type": "string"},
                "title": {"type": "string"},
                "why": {"type": "string",
                        "description": "one sentence: why this one wins"},
            },
            "required": ["videoId", "title", "why"]}},
        "opportunities": {"type": "array", "items": {"type": "string"},
                          "description": "3-6 concrete derivative ideas the user should make next, tied to observed winners"},
    },
    "required": ["summary", "channels", "winningHooks", "winningMessages",
                 "winningFormats", "winningStyles", "topShorts",
                 "opportunities"],
}


def analyze_shorts(days: int = 30) -> dict:
    shorts = [s for s in store.list_shorts(days)]
    if not shorts:
        raise RuntimeError("no shorts pulled yet — hit Sync first")
    shorts.sort(key=lambda s: -(s.get("view_count") or 0))
    lines = []
    for s in shorts[:60]:
        t = (s.get("transcript") or "").strip()
        lines.append(
            f"- [{s['video_id']}] {s['channel']} | {s['title']!r} | "
            f"{s.get('view_count') or 0:,} views | "
            f"{round(s.get('duration_seconds') or 0)}s\n"
            f"  transcript: {t[:600] if t else '(none captured)'}")
    corpus = "\n".join(lines)

    prompt = (
        "You are a short-form video strategist. Below are a creator's "
        f"monitored competitors' YouTube Shorts from the last {days} days, "
        "sorted by view count, with transcripts where available.\n\n"
        "Analyze WHAT IS WINNING: hooks (the first 1-2 lines), message "
        "angles, formats/structures, and delivery styles. Quote real hooks "
        "with their view counts. Tie every claim to specific shorts. Then "
        "propose concrete derivative opportunities the creator should make "
        "next — same winning pattern, their own topic and voice, never a "
        "copy." + marketing_context() +
        f"\n\nTHE SHORTS:\n{corpus}")

    parsed = dict(_complete(
        "Analyze competitor YouTube Shorts and report what is winning. "
        "Tie every claim to specific shorts; quote real hooks with views.",
        prompt, _SHORTS_SCHEMA, "shorts_analysis", 4000))
    parsed["analyzedAt"] = time.time()
    parsed["shortCount"] = len(shorts)
    parsed["days"] = days
    store.kv_set("shortsAnalysis", parsed)
    return parsed


# ---------------------------------------------------------------------------
# Shorts Content: derivative scripts
# ---------------------------------------------------------------------------

_DERIVATIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "hook": {"type": "string",
                 "description": "the spoken first 1-2 lines — pattern-matched to a winning hook"},
        "script": {"type": "string",
                   "description": "full spoken script with [0:00]-style beat timestamps, 30-60s"},
        "shotList": {"type": "array", "items": {"type": "string"},
                     "description": "shot-by-shot visual plan"},
        "caption": {"type": "string",
                    "description": "post caption, first line does the work"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "patternUsed": {"type": "string",
                        "description": "which winning pattern this derives from, and from whom"},
    },
    "required": ["title", "hook", "script", "shotList", "caption",
                 "hashtags", "patternUsed"],
}


def create_derivative(brief: str, pattern: str = "") -> int:
    """Generate a derivative short script from the winning-pattern analysis.
    Returns the creation id."""
    analysis_ctx = store.kv_get("shortsAnalysis")
    ctx = ""
    if analysis_ctx:
        ctx = ("\n\nTHE CURRENT WINNING-PATTERN ANALYSIS (derive from "
               "these observed winners):\n" +
               json.dumps({k: analysis_ctx.get(k) for k in
                           ("winningHooks", "winningMessages",
                            "winningFormats", "winningStyles",
                            "opportunities")}, indent=2)[:4000])
    want = f"\n\nPattern to use: {pattern}" if pattern.strip() else ""
    prompt = (
        "You are a short-form scriptwriter. Write ONE derivative YouTube "
        "Short script: take a proven winning pattern from the analysis and "
        "apply it to the creator's brief — their topic, their voice. "
        "Derivative means the same hook mechanics, structure, and pacing "
        "that demonstrably win; never a copy of anyone's content.\n\n"
        f"CREATOR'S BRIEF: {brief.strip()[:2000]}" + want + ctx +
        marketing_context())
    p = _complete(
        "Write one derivative YouTube Short script from a proven winning "
        "pattern applied to the creator's brief. Never copy content.",
        prompt, _DERIVATIVE_SCHEMA, "short_derivative", 2500)
    md = (f"# {p['title']}\n\n**Hook:** {p['hook']}\n\n"
          f"**Pattern:** {p['patternUsed']}\n\n## Script\n\n{p['script']}\n\n"
          "## Shot list\n\n" +
          "\n".join(f"{i+1}. {s}" for i, s in enumerate(p["shotList"])) +
          f"\n\n## Caption\n\n{p['caption']}\n\n" +
          " ".join(f"#{h.lstrip('#')}" for h in p["hashtags"]))
    return store.create_creation(
        "short-script", p["title"], brief, md, status="ready",
        source={"pattern": p.get("patternUsed", "")})


# ---------------------------------------------------------------------------
# Ads Lab: winning-ad style transfer prompt
# ---------------------------------------------------------------------------

_AD_PROMPT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string",
                  "description": "short internal name for this ad creative"},
        "generationPrompt": {
            "type": "string",
            "description": ("the full image-generation prompt: recreate the "
                            "reference ad's composition, styling, text "
                            "placement and mood, but with the source "
                            "subject/product and the user's copy")},
        "variantPrompts": {
            "type": "array", "items": {"type": "string"},
            "description": ("when N variants were requested: exactly N "
                            "COMPLETE standalone generation prompts, each a "
                            "distinct take — vary the headline angle, "
                            "composition, color mood, or CTA framing — while "
                            "keeping the source subject faithful. Empty for "
                            "a single ad.")},
        "adCopy": {"type": "string",
                   "description": "the exact headline/text the image should carry — an IMPROVED derivative of the winning ad's copy, never an unrelated invention"},
        "copyVariants": {
            "type": "array", "items": {"type": "string"},
            "description": ("when N variants were requested: exactly N "
                            "improved copy takes derived from the winning "
                            "ad's copy — same persuasion mechanics, varied "
                            "hook/angle/CTA — one per variant prompt, in "
                            "the same order")},
        "postCopyVariants": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "hook": {"type": "string",
                             "description": "the scroll-stopping opening "
                                            "line"},
                    "content": {"type": "string",
                                "description": "the full body copy. MIRROR "
                                               "THE WINNING AD'S ORIGINAL "
                                               "COPY in shape and length: "
                                               "if it runs long with "
                                               "bullets, emojis, line "
                                               "breaks, or multiple "
                                               "paragraphs, reproduce that "
                                               "same structure and a "
                                               "comparable word count — "
                                               "never compress it to a "
                                               "couple of sentences"},
                    "cta": {"type": "string",
                            "description": "the closing call to action "
                                           "line"},
                },
                "required": ["hook", "content", "cta"],
            },
            "description": ("POST COPY to publish WITH the ad — the "
                            "primary text above the creative, distinct "
                            "from the headline rendered inside the image. "
                            "Provide exactly 3 objects per ad image, "
                            "concatenated in variant order (variant 1's "
                            "three first, then variant 2's three, ...). "
                            "Each is an improved take derived from the "
                            "winning ad's ORIGINAL copy — same persuasion "
                            "mechanics, adapted to the user's offer — with "
                            "a clear hook, content, and cta. The content "
                            "must MATCH the original's style and length: "
                            "keep its bullets, emojis, spacing, and "
                            "paragraph rhythm rather than summarizing. "
                            "With no winning copy supplied, still write "
                            "complete long-form social-post copy.")},
        "copyTakesPerVariant": {
            "type": "array",
            "items": {"type": "array", "items": {"type": "string"}},
            "description": ("for EVERY ad image (one entry per variant, "
                            "same order; a single entry when no variants): "
                            "exactly 3 ad-copy takes — the line rendered in "
                            "the image first, then two strong alternates "
                            "the user can swap in, all derived from the "
                            "winning copy's mechanics")},
        "notes": {"type": "string",
                  "description": "one or two sentences: which mechanics of the winning copy were kept, and how each take varies it"},
    },
    "required": ["title", "generationPrompt", "adCopy", "notes"],
}


def build_ad_prompt(brief: str, ad_context: str = "",
                    variants: int = 1,
                    has_source_image: bool = False) -> dict:
    """Compose the style-transfer generation prompt (image-ad-clone style:
    extract what makes the winner work, re-parameterize with the user's
    subject and offer). With variants > 1, also produce that many distinct
    standalone prompts."""
    variants = max(1, min(50, int(variants or 1)))
    ad_note = (
        f"\n\nTHE WINNING AD BEING CLONED (metadata + full copy): "
        f"{ad_context.strip()[:3500]}"
        "\n\nTHE WINNING COPY IS RAW MATERIAL — the whole point of "
        "handing it over. Dissect WHY it works (hook mechanics, tension, "
        "promise, CTA), then WRITE IMPROVED VARIATIONS of it: same "
        "persuasion mechanics and voice, adapted to the user's offer, "
        "tightened where the original rambles. Never ignore it and invent "
        "unrelated copy; never repeat it verbatim. adCopy (and each entry "
        "of copyVariants) must be a recognizable, improved descendant of "
        "the winning copy."
        if ad_context.strip() else "")
    identity_note = (
        "\n\nSOURCE PORTRAIT SUPPLIED — IDENTITY IS NON-NEGOTIABLE: the "
        "person in the user's source image MUST be the person shown in the "
        "final ad. Every generationPrompt (and every variantPrompt) must "
        "OPEN with an explicit instruction like: 'Use the exact person from "
        "the provided source image — same face, hair, and identity, "
        "photorealistically preserved; do not generate a different or "
        "generic person.' Never describe the person generically (no 'a "
        "professional woman' etc.) — always anchor to the source image."
        if has_source_image else "")
    variant_note = (
        f"\n\nVARIANTS REQUESTED: {variants}. Fill variantPrompts with "
        f"exactly {variants} complete, standalone prompts — each ONE ad "
        "image with a distinct angle (headline, composition, color mood, "
        "CTA framing) — and copyVariants with the matching improved copy "
        "take for each, in the same order. Never ask a single image to "
        "contain multiple variations." if variants > 1 else "")
    prompt = (
        "You are an ad creative director doing a style transfer (the "
        "image-ad-clone method): study the winning reference ad, extract "
        "what makes it work — composition, framing, text placement, color "
        "mood, energy — and write ONE image-generation prompt that recreates "
        "that winning formula with the user's OWN subject (their supplied "
        "source image is image 1; the winning ad screenshot, when supplied, "
        "follows as the style reference) and the user's offer.\n"
        "The prompt must instruct: keep the source subject's identity "
        "faithful (face/product unchanged), adopt the reference's layout "
        "and styling, and render the ad copy text EXACTLY as given.\n"
        "For every ad image also fill copyTakesPerVariant with exactly 3 "
        "copy takes (rendered line first, two alternates) AND "
        "postCopyVariants with exactly 3 {hook, content, cta} post-copy "
        "objects per ad image in variant order (the primary text "
        "published WITH the ad, derived from the winning ad's original "
        "copy — not the in-image text). Post-copy content must mirror "
        "the original's SHAPE AND LENGTH — keep its bullets, emojis, "
        "line breaks, and paragraph rhythm; do not shrink long copy "
        "into a summary.\n\n"
        f"USER'S BRIEF (product/offer/audience): {brief.strip()[:2000]}"
        + ad_note + identity_note + variant_note + marketing_context())
    return dict(_complete(
        "Compose one image-generation prompt that transfers a winning ad's "
        "style onto the user's own subject and offer.",
        prompt, _AD_PROMPT_SCHEMA, "ad_style_prompt", 1500))


# ---------------------------------------------------------------------------
# Chat tool
# ---------------------------------------------------------------------------

def tool_shorts_search(args: dict) -> str:
    q = str(args.get("query") or "").strip().lower()
    limit = int(args.get("limit") or 5)
    shorts = store.list_shorts(90)
    if q:
        shorts = [s for s in shorts
                  if q in (s.get("title") or "").lower()
                  or q in (s.get("transcript") or "").lower()
                  or q in (s.get("channel") or "").lower()]
    shorts = shorts[:max(1, min(limit, 20))]
    out = [{"videoId": s["video_id"], "channel": s["channel"],
            "title": s["title"], "views": s.get("view_count"),
            "link": s.get("link"),
            "transcript": (s.get("transcript") or "")[:800]}
           for s in shorts]
    return json.dumps({"count": len(out), "shorts": out})


# ---------------------------------------------------------------------------
# Image text QA — read the rendered ad and catch misspellings before the
# user ever sees the creative
# ---------------------------------------------------------------------------

_SPELLCHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "textOk": {"type": "boolean",
                   "description": "true ONLY if every word rendered in the "
                                  "image is correctly spelled and cleanly "
                                  "legible (no gibberish glyphs, no "
                                  "duplicated or mangled letters)"},
        "readText": {"type": "string",
                     "description": "the text exactly as rendered in the image"},
        "personMatch": {
            "type": "boolean",
            "description": "when a reference portrait was supplied: true "
                           "ONLY if the main person in the ad is visually "
                           "the SAME individual as the reference portrait "
                           "(face, hair, identity). True when no portrait "
                           "was supplied or the ad shows no person."},
        "issues": {"type": "array", "items": {"type": "string"},
                   "description": "each spelling/legibility problem found, "
                                  "plus 'person mismatch: ...' when the ad "
                                  "shows a different individual than the "
                                  "reference portrait"},
    },
    "required": ["textOk", "personMatch", "readText", "issues"],
}


def spellcheck_image(image_url: str, expected_copy: str = "",
                     source_url: str = "") -> dict:
    """Vision QA on a generated ad image: spelling always; when
    ``source_url`` is given (the user's portrait), also verify the ad
    shows that SAME person. Best-effort: raises only on LLM transport
    errors — the caller decides whether to fail open."""
    expected = (f"\n\nThe INTENDED ad copy was: {expected_copy.strip()!r} — "
                "flag any deviation in spelling (wording tweaks are fine, "
                "misspelled words are not)."
                if (expected_copy or "").strip() else "")
    person = ("\n\nThe SECOND image is the user's reference portrait. "
              "personMatch=true ONLY if the main person in the ad (first "
              "image) is visually the SAME individual — same face and "
              "identity, not a lookalike or generic model. If it is a "
              "different person, set personMatch=false and add an issue "
              "starting 'person mismatch:'."
              if (source_url or "").strip()
              else "\n\nNo reference portrait was supplied — set "
                   "personMatch=true.")
    inputs = [{"type": "image", "url": image_url}]
    if (source_url or "").strip():
        inputs.append({"type": "image", "url": source_url.strip()})
    import re
    res = _llm().complete_structured(
        instructions=(
            "You are proofing an AI-generated ad image. Read EVERY piece of "
            "rendered text. textOk=true only if all words are correctly "
            "spelled and cleanly legible — gibberish glyphs, mangled or "
            "duplicated letters, and misspellings all fail."
            + expected + person),
        input=inputs,
        json_schema=_SPELLCHECK_SCHEMA,
        schema_name="ad_spellcheck",
        temperature=0.0,
        max_tokens=500,
        timeout=120,
        purpose="shorts-lab-ad-spellcheck",
    )
    parsed = getattr(res, "parsed", None)
    if parsed is None:
        raw = getattr(res, "text", "") or ""
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        parsed = json.loads(m.group(0)) if m else None
    if not isinstance(parsed, dict):
        raise RuntimeError("spellcheck returned nothing usable")
    person_ok = bool(parsed.get("personMatch", True))
    return {"ok": bool(parsed.get("textOk")) and person_ok,
            "textOk": bool(parsed.get("textOk")),
            "personOk": person_ok,
            "readText": str(parsed.get("readText") or "")[:300],
            "issues": [str(i)[:120] for i in (parsed.get("issues") or [])][:5]}
