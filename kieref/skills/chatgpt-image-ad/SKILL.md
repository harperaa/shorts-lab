---
name: chatgpt-image-ad
description: >-
  Generate one or more standalone Meta image-ad creatives via ChatGPT Image 2 (gpt-image-2) through the KIE.ai API. Auto-strips platform chrome, enforces edge-safe layouts and glyph-safety inside body text. Use when the user asks for a "gpt-image-2 ad", "ChatGPT Image ad", "Image 2 ad creative", or anchors on a need for typography-heavy / dense-text / UI-mimicry ad creatives (chat threads, comparison tables, fake search results, iOS dialogs, Slack snapshots, ChatGPT-conversation ads, Apple Notes lists). Does NOT trigger on Nano Banana cues — use nano-banana-image-ad for those.
---

# chatgpt-image-ad (KIE.ai)

Generate one or more **standalone Meta ad image creatives** via KIE.ai's **dedicated** `POST /api/v1/gpt4o-image/generate` endpoint (OpenAI 4o image / GPT-Image family). Hands the image paths off to your Meta-ad-builder skill.

> **Note:** This is *not* a `/jobs/createTask` model — KIE exposes OpenAI image generation through its own purpose-built endpoint with its own request/response shape. The script handles the differences (`size` instead of `aspect_ratio`, `filesUrl` instead of `image_input`, `successFlag` polling, `result_urls` extraction). Live-validated 2026-05-25.

## Read order

1. **This file** — KIE-specific endpoint, auth, URL-only reference flow, workflow phases.
2. **[shared/skills/chatgpt-image-ad/prompting/guide.md](../../shared/skills/chatgpt-image-ad/prompting/guide.md)** — model-specific prompting.
3. **[shared/skills/image-ad-prompting/prompting/prompt-library.md](../../shared/skills/image-ad-prompting/prompting/prompt-library.md)** — 30+ validated templates with per-model notes.
4. **[shared/skills/image-ad-prompting/prompting/safety-suffixes.md](../../shared/skills/image-ad-prompting/prompting/safety-suffixes.md)** — the 3 always-on guards.
5. **[scripts/generate_image.py](scripts/generate_image.py)** — the helper script.

## Hard rules — never relax

1. **Model defaults to `gpt-image-2`.** The script refuses any Nano Banana variant. If the user asks for nano-banana, point them at `nano-banana-image-ad`.
2. **No platform/screenshot chrome.** `NO_CHROME_SUFFIX` always on (override only with `--allow-chrome`).
3. **Edge-safe + glyph-safety suffixes always on** unless `--no-safe-zone` is explicit.
4. **Max 5 reference URLs.** gpt-image-2 cap.
5. **References are public URLs.** KIE has NO presigned-upload flow. Local files rejected at the CLI.
6. **No Meta upload from this skill.** Image generation only.
7. **Always present a credit-cost estimate** before generating (read `logs/kie-api.jsonl` for matching past calls; the first run in a repo may require asking the user for the per-call rate and recording in `MASTER_CONTEXT.md`).

## Prerequisites

- `.env` containing `KIE_API_KEY` (and optionally `CHATGPT_IMAGE_MODEL` if you've already confirmed the marketplace string)
- Reference images hosted at PUBLIC URLs

## Configuration

- **Base URL:** `https://api.kie.ai` (or `KIE_BASE_URL`).
- **Auth:** `Authorization: Bearer $KIE_API_KEY`.
- **Submit:** `POST /api/v1/gpt4o-image/generate` with `{prompt, size, filesUrl?, maskUrl?, nVariants, isEnhance?, enableFallback?, callBackUrl?}`.
- **Poll:** `GET /api/v1/gpt4o-image/record-info?taskId=<id>` until `data.successFlag == 1` (`0` = in progress, `2` = failed).
- **Result:** `data.response.result_urls` is a list of public CDN URLs. Result URLs expire ~20 min after generation; download promptly. (KIE also exposes `POST /api/v1/gpt4o-image/download-url` to refresh expired URLs.)
- **No model string** — the endpoint itself selects the model. There's no `--model` flag.

## Generation modes

| Mode | When to use | Required | Optional |
|---|---|---|---|
| `image` (default) | Brand-new ad image. | `--prompt`, `--aspect-ratio` | `--image-url` (up to 5 → `filesUrl`) |
| `image_edit` | Modify a `--source-url` image (inpaint with `--mask-url`). | `--prompt`, `--source-url`, `--aspect-ratio` | `--mask-url`, `--image-url` (up to 5 total in `filesUrl`) |

## Supported aspect ratios (`--aspect-ratio` → API `size`)

**Only `1:1`, `3:2`, `2:3`.** The `/gpt4o-image` endpoint accepts no other values. `9:16`, `16:9`, `4:5` will fail at argparse. For wide / tall placements, use `nano-banana-image-ad` (full Meta ratio set) or render `2:3` and post-crop.

## Variants per request (`--n` → API `nVariants`)

`/gpt4o-image` returns multiple variants from a single request (built-in batching). `--n` must be `1`, `2`, or `4` — those are the only nVariants the endpoint accepts. Each variant is downloaded to its own file.

## Workflow

### Phase 1: Preflight

1. `.env` exists with `KIE_API_KEY`.
2. (First-run-only) confirm the ChatGPT Image model string at [kie.ai/market](https://kie.ai/market) and record in `MASTER_CONTEXT.md` or `.env`.
3. Health-check: a `GET /api/v1/jobs/recordInfo?taskId=test` returns a recognized auth response.
4. Reference URLs reachable (the script HEAD-probes them unless `--skip-url-check`).

### Phase 2: Gather inputs

Collect: seed prompt, mode, source URL (if edit), reference URLs (up to 5), variant count, aspect ratio.

If user has local files only, stop and ask: "Where do you host these?" Record in `MASTER_CONTEXT.md`.

### Phase 3: Prompt rewrite

Read [shared/skills/image-ad-prompting/prompting/prompt-library.md](../../shared/skills/image-ad-prompting/prompting/prompt-library.md). Match a template (check `Model notes` block — only proceed if `gpt-image-2` is clean or preferred). Fill placeholders. Show the user. Ask for approval.

For fresh prompts: follow [shared/skills/chatgpt-image-ad/prompting/guide.md § Phase 3b](../../shared/skills/chatgpt-image-ad/prompting/guide.md).

### Phase 4: Credit cost confirmation (MANDATORY)

Present the estimate. Wait for explicit confirmation. If first run and no rate data, ask the user to confirm per-image credits and record in `MASTER_CONTEXT.md`.

### Phase 5: Generate

```bash
~/.claude/skills/chatgpt-image-ad/scripts/generate_image.py \
  --prompt "<rewritten>" \
  --aspect-ratio <ratio> \
  --n <N> \
  --image-url https://<your-host>/product.jpg \
  [--image-url https://<your-host>/style-board.jpg] \
  --out ./generated \
  --env-file .env

# Edit run:
~/.claude/skills/chatgpt-image-ad/scripts/generate_image.py \
  --mode image_edit \
  --prompt "<edit-instruction>" \
  --source-url https://<your-host>/existing.png \
  [--image-url https://<your-host>/guidance.png] \
  --n <N> \
  --out ./generated \
  --env-file .env
```

Each line on stdout is one JSON variant.

Log each call to `logs/kie-api.jsonl` per `kie-external-api` SKILL.md conventions.

### Phase 6: Visual QA (MANDATORY)

For each variant, **read the image** and inspect for: garbled small text, wrong text count, UI proportion drift, wordmark drift.

If defects: regenerate with a revised prompt per [shared/skills/chatgpt-image-ad/prompting/guide.md § Retry mode](../../shared/skills/chatgpt-image-ad/prompting/guide.md). Cap at 2 retries.

### Phase 7: Confirm and hand off

Show all paths. Ask "Use all / use these specific ones / regenerate / cancel." Selected variants ready for your Meta-ad-builder skill.

## Out of scope

- **Meta upload** — different skill.
- **Nano Banana** — use `nano-banana-image-ad`.
- **Video / carousel / DCO** — image only.
- **Editing the shared library** — use `image-ad-clone` (asks which backend at Phase 1).

## Common errors

- **401/403** — `KIE_API_KEY` invalid.
- **400 model not found / unsupported** — the KIE marketplace string for ChatGPT Image 2 differs from `gpt-image-2`. Verify at [kie.ai/market](https://kie.ai/market) and pass via `--model` or set `CHATGPT_IMAGE_MODEL` in `.env`.
- **400 validation** — usually a URL reachability issue; check `--image-url` returns 200.
- **422** — moderation; tighten prompt.
- **429** — rate-limited.

## Files this skill owns

- `~/.claude/skills/chatgpt-image-ad/SKILL.md` — this file
- `~/.claude/skills/chatgpt-image-ad/scripts/generate_image.py` — KIE ChatGPT-Image caller

## See also

- **[shared/skills/chatgpt-image-ad/prompting/guide.md](../../shared/skills/chatgpt-image-ad/prompting/guide.md)** — model-specific prompting
- **[shared/skills/image-ad-prompting/prompting/prompt-library.md](../../shared/skills/image-ad-prompting/prompting/prompt-library.md)** — shared template library
- **[image-ad-clone skill](../image-ad-clone/SKILL.md)** — single backend-agnostic skill that reverse-engineers an existing ad into a reusable library entry
- **[kie-external-api skill](../kie-external-api/SKILL.md)** — KIE conventions
- **[nano-banana-image-ad skill](../nano-banana-image-ad/SKILL.md)** — sibling skill for photoreal templates
