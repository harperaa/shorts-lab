"""Loader for the bundled kie-ai skill corpus.

The `kieref/` tree is the prompting brain vendored from
krusemediallc/claude-code-ai-ad-builder-kie-ai (same stacked-copyright
lineage as this repo's LICENSE — keep the corpus verbatim, edit upstream).
Recipes pull guide text from here so generation prompts stay grounded in
the validated formulas instead of the LLM's imagination.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent

# recipe id -> guide files (relative to kieref/), in priority order
GUIDES = {
    "seedance-ugc": ["skills/kie-external-api/prompting/prompt-library/seedance-2-ugc.md",
                     "skills/kie-external-api/prompting/prompt-library/seedance-2.md"],
    "seedance-premium-reveal": ["skills/kie-external-api/prompting/prompt-library/seedance-2-premium-reveal.md",
                                "skills/kie-external-api/prompting/prompt-library/seedance-2.md"],
    "seedance-product-hero": ["skills/kie-external-api/prompting/prompt-library/seedance-2-product-hero.md",
                              "skills/kie-external-api/prompting/prompt-library/seedance-2.md"],
    "seedance-lookbook": ["skills/kie-external-api/prompting/prompt-library/seedance-2-studio-lookbook.md",
                          "skills/kie-external-api/prompting/prompt-library/seedance-2.md"],
    "seedance-walkthrough": ["skills/kie-external-api/prompting/prompt-library/seedance-2-feature-walkthrough.md",
                             "skills/kie-external-api/prompting/prompt-library/seedance-2.md"],
    "sora-video": ["skills/kie-external-api/prompting/prompt-library/sora-2.md"],
    "veo-video": ["skills/kie-external-api/prompting/prompt-library/veo-3-1.md"],
    "kling-broll": ["skills/kie-external-api/prompting/prompt-library/kling-3.md"],
    "character-sheet": ["skills/kie-external-api/prompting/prompt-library/character-sheet.md",
                        "skills/kie-external-api/prompting/prompt-library/character-sheet-gpt-image-2.md"],
    "influencer-recreation": ["skills/kie-external-api/prompting/prompt-library/influencer-recreation.md"],
    "ugc-selfie": ["skills/kie-external-api/prompting/prompt-library/ugc-product-selfie.md",
                   "skills/kie-external-api/prompting/prompt-library/ugc-selfie-style.md"],
    "product-showcase": ["skills/kie-external-api/prompting/prompt-library/product-showcase.md"],
    "nano-banana": ["skills/kie-external-api/prompting/prompt-library/nano-banana.md"],
    "youtube-thumbnail": ["skills/generate-youtube-thumbnail/SKILL.md",
                          "shared/skills/generate-youtube-thumbnail/prompting/formulas.md",
                          "shared/skills/generate-youtube-thumbnail/prompting/guide.md"],
    "image-ad-templates": ["shared/skills/image-ad-prompting/prompting/prompt-library.md"],
    "image-ad-overview": ["shared/skills/image-ad-prompting/OVERVIEW.md",
                          "shared/skills/image-ad-prompting/prompting/safety-suffixes.md"],
    "image-ad-clone": ["skills/image-ad-clone/SKILL.md"],
    "chatgpt-image-ad": ["skills/chatgpt-image-ad/SKILL.md",
                         "shared/skills/chatgpt-image-ad/prompting/guide.md"],
    "pixar": ["shared/skills/pixar-style-ad/prompting/guide.md",
              "shared/skills/pixar-style-ad/prompting/storyboard-gpt-image-2.md",
              "shared/skills/pixar-style-ad/prompting/animate-seedance-2.md"],
    "claymation": ["shared/skills/claymation-ad/prompting/guide.md",
                   "shared/skills/claymation-ad/prompting/storyboard-gpt-image-2.md",
                   "shared/skills/claymation-ad/prompting/animate-seedance-2.md"],
    "analyze-video": ["skills/kie-external-api/prompting/analyze-video/SKILL.md"],
    "clone-ad": ["skills/kie-external-api/prompting/clone-ad/SKILL.md"],
    "meta-copy": ["shared/skills/meta-ad-builder/prompting/copy-guide.md"],
    "kie-prompting": ["skills/kie-external-api/prompting/guide.md"],
}


def guide_text(recipe: str, max_chars: int = 24000) -> str:
    """Concatenated guide text for a recipe id (truncated per file fairly)."""
    files = GUIDES.get(recipe) or []
    parts = []
    budget = max_chars // max(1, len(files)) if files else 0
    for rel in files:
        p = ROOT / rel
        if p.exists():
            parts.append(f"--- {rel} ---\n" + p.read_text(errors="replace")[:budget])
    return "\n\n".join(parts)


def available() -> list:
    return sorted(GUIDES)


def image_ad_templates() -> list:
    """The 37-template static image-ad library, parsed from the bundled
    prompt-library.md (`## T<N> — <name>` sections)."""
    import re
    p = ROOT / ("shared/skills/image-ad-prompting/prompting/"
                "prompt-library.md")
    out = []
    if p.exists():
        for m in re.finditer(r"^## (T\d+) — (.+)$", p.read_text(),
                             re.MULTILINE):
            out.append({"id": m.group(1), "name": m.group(2).strip()})
    return out


def image_ad_template_text(template_id: str, max_chars: int = 9000) -> str:
    """One template's full section text plus the shared safety suffixes
    and entry-format notes."""
    import re
    p = ROOT / ("shared/skills/image-ad-prompting/prompting/"
                "prompt-library.md")
    section = ""
    if p.exists() and re.fullmatch(r"T\d+", template_id or ""):
        txt = p.read_text()
        m = re.search(rf"^## {template_id} — .*?(?=^## |\Z)", txt,
                      re.MULTILINE | re.DOTALL)
        if m:
            section = m.group(0)[:max_chars]
    extras = guide_text("image-ad-overview", max_chars=6000)
    return (section + "\n\n" + extras) if section else ""
