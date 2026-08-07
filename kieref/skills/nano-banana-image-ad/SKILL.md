---
name: nano-banana-image-ad
description: >-
  Generate one or more standalone Meta image-ad creatives via Nano Banana 2 / Nano Banana Pro (Gemini Flash Image family) through the KIE.ai API. Locks the model family, auto-strips platform chrome, enforces edge-safe layouts. Use when the user asks for a "Nano Banana ad", "Gemini image ad", "nano-banana-2 ad creative", or anchors on a need for photoreal / lifestyle / multi-reference / handheld-object / clay-texture ad creatives (sticky-note flatlays, held-whiteboard signs, lifestyle portraits, ingredient collages, OOH photography). Does NOT trigger on ChatGPT Image cues — use chatgpt-image-ad for those.
---

# nano-banana-image-ad (KIE.ai)

Generate one or more **standalone Meta ad image creatives** via KIE.ai's `POST /api/v1/jobs/createTask` with the Nano Banana model family (default `nano-banana-2`). Hands the image paths off to your Meta-ad-builder skill — this skill does not upload to Meta itself.

## Read order

1. **This file** — KIE-specific endpoint, auth, URL-only reference flow, workflow phases.
2. **[shared/skills/nano-banana-image-ad/prompting/guide.md](../../shared/skills/nano-banana-image-ad/prompting/guide.md)** — model-specific prompting.
3. **[shared/skills/image-ad-prompting/prompting/prompt-library.md](../../shared/skills/image-ad-prompting/prompting/prompt-library.md)** — 30+ validated templates with per-model notes.
4. **[shared/skills/image-ad-prompting/prompting/safety-suffixes.md](../../shared/skills/image-ad-prompting/prompting/safety-suffixes.md)** — the 3 always-on guards.
5. **[scripts/generate_image.py](scripts/generate_image.py)** — the helper script (Python stdlib only).

## Hard rules — never relax

1. **Model is in the Nano Banana family.** Accepts `nano-banana-2` (default), `nano-banana-pro`, `nano-banana-edit`, or `nano-banana` (legacy). Anything else is refused.
2. **No platform/screenshot chrome.** `NO_CHROME_SUFFIX` always on.
3. **Edge-safe + glyph-safety suffixes always on** unless `--no-safe-zone` is explicit.
4. **Max 14 reference URLs.** KIE's `input.image_input` cap.
5. **References are public URLs.** KIE has NO presigned-upload flow. Local files are rejected at the CLI. Host on R2 / S3 / Cloudinary / your CDN first.
6. **No Meta upload from this skill.** Image generation only.
7. **Always present a credit-cost estimate** before generating (read `logs/kie-api.jsonl` or `MASTER_CONTEXT.md` rates; `nano-banana-pro` > `nano-banana-2`).

## Prerequisites

- `.env` containing `KIE_API_KEY`
- Reference images hosted at PUBLIC URLs (R2 / S3 / Cloudinary / Imgur / GitHub raw / etc.)
- If you only have local files, see `MASTER_CONTEXT.md` § Image hosting for the user's chosen hosting strategy

## Configuration

- **Base URL:** `https://api.kie.ai` (or `KIE_BASE_URL`).
- **Auth:** `Authorization: Bearer $KIE_API_KEY`.
- **Submit:** `POST /api/v1/jobs/createTask` with `{model: "nano-banana-2", input: {prompt, image_input?, aspect_ratio}}`.
- **Poll:** `GET /api/v1/jobs/recordInfo?taskId=<id>` until `data.state == "success"`. Result URLs in `data.resultJson` (JSON-encoded string).

## Generation modes

| Mode | When to use | Required | Optional |
|---|---|---|---|
| `image` (default) | Brand-new ad image. | `--prompt`, `--aspect-ratio` | `--image-url` (up to 14) |
| `image_edit` | Modify a `--source-url` image. | `--prompt`, `--source-url` | `--image-url` (up to 14 additional refs) |

## Supported aspect ratios

`1:1`, `4:5`, `5:4`, `2:3`, `3:2`, `9:16`, `16:9`, `3:4`, `4:3`, `21:9`.

**Default to `4:5` for Meta feed-portrait** — Nano Banana renders this natively. `chatgpt-image-ad` can't on either backend without post-cropping.

## Model variants (`--model`)

- **`nano-banana-2`** (default) — Gemini 2.5 Flash Image.
- **`nano-banana-pro`** — Gemini 3 Pro Image. Use for hero stills, identity continuity, material-realism critical shots.
- **`nano-banana-edit`** — inpaint-focused. Use only with `--mode image_edit`.
- **`nano-banana`** — legacy.

Confirm with user before first call in a session if not already in `MASTER_CONTEXT.md`.

## Workflow

### Phase 1: Preflight

1. `.env` exists with `KIE_API_KEY`.
2. Health-check: a quick `GET /api/v1/jobs/recordInfo?taskId=test` returns a recognized auth response (any 4xx other than 401 means auth is good).
3. Reference URLs reachable (`curl -I <url>` returns 200) — the script does this automatically unless `--skip-url-check`.

### Phase 2: Gather inputs

Collect: seed prompt, mode, source URL (if edit), reference URLs (up to 14), variant count, aspect ratio, model variant.

If user has local files only, stop and ask: "Where do you host these (R2 / S3 / Cloudinary / etc.)?" Document the answer in `MASTER_CONTEXT.md` so future runs don't re-ask.

### Phase 3: Prompt rewrite

Read [shared/skills/image-ad-prompting/prompting/prompt-library.md](../../shared/skills/image-ad-prompting/prompting/prompt-library.md). Match a template (check `Model notes` block — only proceed if `nano-banana` is preferred or clean). Fill placeholders. Show the user. Ask for approval.

For fresh prompts: follow the [shared/skills/nano-banana-image-ad/prompting/guide.md § Phase 3b](../../shared/skills/nano-banana-image-ad/prompting/guide.md) structure.

### Phase 4: Credit cost confirmation (MANDATORY)

Present the estimate (read `logs/kie-api.jsonl` for matching past calls, or KIE pricing page). Wait for explicit confirmation.

### Phase 5: Generate

```bash
~/.claude/skills/nano-banana-image-ad/scripts/generate_image.py \
  --prompt "<rewritten>" \
  --aspect-ratio <ratio> \
  --n <N> \
  --image-url https://<your-host>/product.jpg \
  [--image-url https://<your-host>/character.jpg] \
  --out ./generated \
  --env-file .env

# Higher-stakes hero shot:
~/.claude/skills/nano-banana-image-ad/scripts/generate_image.py \
  --model nano-banana-pro \
  --prompt "<rewritten>" \
  --aspect-ratio <ratio> \
  --n <N> \
  --image-url https://<your-host>/product.jpg \
  --out ./generated \
  --env-file .env

# Edit run (inpaint):
~/.claude/skills/nano-banana-image-ad/scripts/generate_image.py \
  --mode image_edit \
  --model nano-banana-edit \
  --prompt "<edit-instruction>" \
  --source-url https://<your-host>/existing.png \
  [--image-url https://<your-host>/guidance.png] \
  --n <N> \
  --out ./generated \
  --env-file .env
```

Each line on stdout is one JSON variant (`variant`, `path`, `task_id`, `width`, `height`, `prompt`, `mode`, `aspect_ratio`, `model`).

Log each call to `logs/kie-api.jsonl` per the `kie-external-api` SKILL.md conventions.

### Phase 6: Visual QA (MANDATORY)

For each variant, **read the image** and inspect for: garbled small text, extra fingers / wrong limb count, wordmark drift, character identity drift across variants.

If defects: regenerate with a revised prompt per [shared/skills/nano-banana-image-ad/prompting/guide.md § Retry mode](../../shared/skills/nano-banana-image-ad/prompting/guide.md). Cap at 2 retries per variant.

### Phase 7: Confirm and hand off

Show all paths. Ask "Use all / use these specific ones / regenerate / cancel."

Selected variants ready for your Meta-ad-builder skill.

## Out of scope

- **Meta upload** — different skill.
- **ChatGPT Image 2** — use `chatgpt-image-ad`.
- **Video / carousel / DCO** — image only.
- **Editing the shared library** — use `image-ad-clone` (asks which backend at Phase 1).

## Common errors

- **401/403** — fix `KIE_API_KEY` in `.env`.
- **400 validation** — usually a reachable-URL problem; check `--image-url` returns 200.
- **422** — moderation; tighten prompt.
- **429** — rate-limited (>20 req/10s). Reduce `--n` parallelism.
- **500** — retry once; if persistent, file issue.

## Files this skill owns

- `~/.claude/skills/nano-banana-image-ad/SKILL.md` — this file
- `~/.claude/skills/nano-banana-image-ad/scripts/generate_image.py` — KIE Nano Banana caller

## See also

- **[shared/skills/nano-banana-image-ad/prompting/guide.md](../../shared/skills/nano-banana-image-ad/prompting/guide.md)** — model-specific prompting
- **[shared/skills/image-ad-prompting/prompting/prompt-library.md](../../shared/skills/image-ad-prompting/prompting/prompt-library.md)** — shared template library
- **[image-ad-clone skill](../image-ad-clone/SKILL.md)** — single backend-agnostic skill that reverse-engineers an existing ad into a reusable library entry
- **[kie-external-api skill](../kie-external-api/SKILL.md)** — KIE conventions (sessions, credit cost, QA, logs)
- **[chatgpt-image-ad skill](../chatgpt-image-ad/SKILL.md)** — sibling skill for typography-heavy / UI-mimicry templates
