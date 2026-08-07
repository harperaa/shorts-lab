---
name: image-ad-clone
description: Use when the user wants to reverse-engineer an existing image ad into a reusable prompt template. Validates via KIE.ai — picks gpt-image-2 (`/gpt4o-image/generate`) or Nano Banana (`/jobs/createTask`) at Phase 1. Triggers on "clone this ad as a template", "reverse engineer this ad", "turn this ad into a prompt", "extract a template", "make this ad reusable", "add to my prompt library", "study this ad and make a template". Input is an EXISTING ad image (must be at a public URL); does NOT trigger for fresh generation (use chatgpt-image-ad or nano-banana-image-ad).
---

# image-ad-clone (KIE.ai)

Take an existing image ad and turn it into a reusable, parameterizable prompt template that gets appended to the shared **37-template image-ad library**. The template is validated by round-tripping through one of the KIE.ai image-ad generators — **ChatGPT Image 2** (typography / UI-mimicry templates) or **Nano Banana** (photoreal / lifestyle / multi-reference templates).

This skill replaces the older Uni1-locked `image-ad-clone` (which only worked with Luma uni-1). It's backend-agnostic: at Phase 1 the agent asks you (or auto-detects from the reference) whether to validate against gpt-image-2 or Nano Banana, then routes through the matching generator script in this repo.

## Read order

1. **This file** — KIE-specific generator paths, model-choice decision, what's locked at the per-repo layer.
2. **[shared/skills/image-ad-clone/prompting/guide.md](../../shared/skills/image-ad-clone/prompting/guide.md)** — the full model-agnostic 10-phase workflow.
3. **[shared/skills/image-ad-prompting/prompting/template-format.md](../../shared/skills/image-ad-prompting/prompting/template-format.md)** — entry skeleton.
4. **[shared/skills/image-ad-prompting/prompting/prompt-library.md](../../shared/skills/image-ad-prompting/prompting/prompt-library.md)** — destination for the new entry.

## Hard rules

Inherits all 6 hard rules from the shared guide. Plus per-repo:

7. **Backend is one of: ChatGPT Image 2 (via KIE's dedicated `/gpt4o-image/generate` endpoint) OR Nano Banana (via `/jobs/createTask`).** Never uni-1.

## Picking the right backend in Phase 1

Pick by what the reference ad is showing — most templates fall into one clear bucket.

**Use `chatgpt-image-ad` when the reference is:**
- Typography-heavy / UI mimicry (Apple Notes lists, fake Google search, fake Slack threads, ChatGPT-conversation ads, iMessage screenshots, comparison tables, fake AirDrop dialogs, Hinge-style cards, calendar UI, weather forecast UI, magazine masthead)
- Brutalist / editorial typography heros
- Dense small text inside UI elements

**Use `nano-banana-image-ad` when the reference is:**
- Photoreal handheld objects (whiteboards, napkins, sticky notes, letter boards, scratch-off tickets)
- Aspirational lifestyle photography (sunset, kitchen at golden hour, OOH / transit)
- Multi-image reference blending (logo + product + style + character all in one)
- Clay / claymation / Pixar-adjacent textures

**If the reference straddles both**, clone twice (once per backend) and ship the template with `Model notes` saying which renders cleaner. The agent offers this in Phase 8.

If the user explicitly says "clone this with gpt-image-2" or "with Nano Banana", honor that.

## Dependencies

This skill uses the matching generator script in the SAME repo:
- For gpt-image-2 validation: `skills/chatgpt-image-ad/scripts/generate_image.py` (hits KIE's dedicated `/api/v1/gpt4o-image/generate` endpoint)
- For Nano Banana validation: `skills/nano-banana-image-ad/scripts/generate_image.py` (hits `/jobs/createTask` with `nano-banana-2`/`-pro`/`-edit`)

Fail Phase 1 with a fix-it message if neither generator is installed in this repo.

Also required:
- `.env` with `KIE_API_KEY`
- Reference ad image hosted at a **public URL** (KIE has no presigned-upload flow). The agent will stop and ask for hosting if you pass a local path with no host configured in `MASTER_CONTEXT.md`.
- Python 3.12+

## Where this skill's generator lives

When the [shared guide](../../shared/skills/image-ad-clone/prompting/guide.md) Phase 1 tells you to locate the companion generator, look here in order based on the model choice:

For gpt-image-2:
1. `~/.claude/skills/chatgpt-image-ad/scripts/generate_image.py`
2. `<repo>/skills/chatgpt-image-ad/scripts/generate_image.py`
3. If neither: stop and ask the user to install `chatgpt-image-ad` first.

For Nano Banana:
1. `~/.claude/skills/nano-banana-image-ad/scripts/generate_image.py`
2. `<repo>/skills/nano-banana-image-ad/scripts/generate_image.py`
3. If neither: stop and ask the user to install `nano-banana-image-ad` first.

## Reference image hosting

KIE only accepts public URLs as references. Before any generation in this workflow:

1. The reference ad image must already be at a public URL, OR
2. The user has configured an image-hosting strategy in `MASTER_CONTEXT.md` under "Image hosting" (R2 / S3 / Cloudinary / imgur / 0x0.st / etc.)

If neither, **stop at Phase 1** and ask the user how to host. Record their answer in `MASTER_CONTEXT.md` for future runs.

The generator scripts HEAD-probe the URL before submitting; pass `--skip-url-check` if your host blocks HEAD requests.

## Aspect ratio mapping per backend

Each KIE backend has different native aspect-ratio support. When measuring the original ad's aspect (Phase 2):

**`chatgpt-image-ad` (KIE `/gpt4o-image/generate`):** accepts only `1:1`, `3:2`, `2:3`.
- `4:5` ad → use `2:3` (taller; document the map)
- `1.91:1` ad → use `3:2`
- `9:16` / `16:9` ads → NOT supported on this backend; consider Nano Banana for those

**`nano-banana-image-ad` (KIE `/jobs/createTask`):** accepts the full Meta ratio set — `1:1`, `4:5`, `5:4`, `2:3`, `3:2`, `9:16`, `16:9`, `3:4`, `4:3`, `21:9`. **Default to `4:5` for Meta feed-portrait** — KIE Nano Banana renders it natively.

If your reference ad's native ratio isn't supported by the backend you want, the choice is:
1. Switch backends (most ratios work on Nano Banana)
2. Render at the closest supported ratio and document the fallback in the `Aspect ratio:` field
3. (For very narrow / very tall ads) Consider the Arcads repo's `image-ad-clone` instead

## Workflow phases (model-agnostic, see shared guide for full detail)

1. **Phase 1: Preflight + model choice + hosting check.** Reference URL reachable; `.env` has `KIE_API_KEY`; both generators detected. **Ask the user which model to validate against** (or auto-detect from the reference). Confirm reference image is at a public URL.
2. **Phase 2: Visual analysis.** Describe the reference structurally — aspect ratio, format type, layout, typography, color palette, photography style, every text string verbatim, decorative elements, chrome to strip.
3. **Phase 3: Draft v1 prompt** (brand-specifics intact).
4. **Phase 4: Generate with reference** using the matching generator script. Pass `--image-url <reference_url>` and the matched aspect ratio.
5. **Phase 5: Compare and iterate.** Refine prompt based on deltas. Cap 4 iterations.
6. **Phase 6: Generalize into placeholders.**
7. **Phase 7: Test the generalized template** against a DIFFERENT brand (need a different brand's product photo hosted at a public URL).
8. **Phase 8: Cross-model validation (recommended).** Run the same template through the OTHER backend in this repo. Document deltas in the `Model notes` block.
9. **Phase 9: Document the template** using `template-format.md`. Required `Model notes` for both backends.
10. **Phase 10: Save and confirm.** Append to `shared/skills/image-ad-prompting/prompting/prompt-library.md`.

## Iteration directory layout

```
<cwd>/iterations/clone-2026-05-26/
  T40-lifestyle-hero/
    prompt.txt
    v1.png, v2.png, …                # against the source ref (chosen backend)
    test-fill-v1.png, …              # Phase 7 generalization test
    cross-{other-backend}/v1.png     # Phase 8 cross-model validation
    notes.md
```

## See also

- **[shared/skills/image-ad-clone/prompting/guide.md](../../shared/skills/image-ad-clone/prompting/guide.md)** — full 10-phase workflow
- **[shared/skills/image-ad-prompting/OVERVIEW.md](../../shared/skills/image-ad-prompting/OVERVIEW.md)** — ecosystem context
- **[chatgpt-image-ad skill](../chatgpt-image-ad/SKILL.md)** — gpt-image-2 generator
- **[nano-banana-image-ad skill](../nano-banana-image-ad/SKILL.md)** — Nano Banana generator
- **[kie-external-api skill](../kie-external-api/SKILL.md)** — KIE conventions (async polling, URL refs, marketplace strings)
