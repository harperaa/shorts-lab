# Short Form (shorts-lab) — Hermes Plugin

> Aligned with the mentoring of **Dr. Allen Harper, AI Cyber Value Creator** — join the community at [AI Cyber Value Creators on Skool](https://www.skool.com/ai-cyber-value-creators).

The Attract-phase workbench for [Hermes Agent](https://github.com/NousResearch/hermes-agent): research what's winning in your competitors' short-form content and paid ads, then make your own derivatives. The generation guts are distilled from the [claude-code-ai-ad-builder-kie-ai](https://github.com/harperaa/claude-code-ai-ad-builder-kie-ai) agent skill pack (Kruse Media LLC / AI Cyber Sherpas LLC).

## The four tabs

- **Shorts Research** — pulls your monitored competitors' YouTube Shorts from the last 30 days (transcripts included) via transcriptapi.com. The competitor list is **shared with the YouTube Insights plugin** — one `channels` table, so adding or removing a channel on either page updates both. ✨ Analyze mines what's winning — hooks (quoted, with view counts), message angles, formats, and delivery styles — grounded in the digital-marketing-pro skill pack (video-script, social-strategy, creative-testing-framework) when installed.
- **Shorts Content** — turns winning patterns into derivative scripts: hook, timestamped beats, shot list, caption, hashtags. Derivative means the pattern that wins applied to *your* topic in *your* voice — never a copy. View inline, download as markdown.
- **Ads Research** — searches the Meta Ad Library (`ads_archive`) for competitor pages, monitors them, and lists their ads **longest-running first** — a long run means the ad keeps paying, so those are the ones to study. Open any creative via its snapshot link.
- **Ads Lab** — the image-ad-clone method: supply your own source image (portrait, product shot) plus a screenshot of the winning ad as the style reference, describe your offer, and the host LLM composes a style-transfer prompt that KIE.ai (Nano Banana) renders — your subject, their winning composition, your copy. Async generation with in-page polling; open/download the result when ready.

## Keys (all on the hermes Keys page)

| Env var | Powers | Where to get it |
|---|---|---|
| `TRANSCRIPT_API_KEY` | Shorts Research | transcriptapi.com (same key YouTube Insights uses) |
| `META_ACCESS_TOKEN` | Ads Research | Graph API token with Ad Library access |
| `KIE_API_KEY` | Ads Lab renders | [kie.ai/api-key](https://kie.ai/api-key) |

KIE takes reference images by public URL only, so uploaded assets are briefly hosted on a temp host (0x0.st) for the generator to fetch — the same approach the source kit recommends.

## Layout

```
plugin.yaml        manifest: key prestage, shorts_search tool
store.py           shorts/ads/creations sqlite + the shared yti channels bridge
transcripts.py     transcriptapi.com client — Shorts-only filter (inverse of yti's)
meta_ads.py        Meta Ad Library search / monitor / longest-running pulls
kie.py             KIE.ai jobs client (createTask/recordInfo) + asset hosting
analysis.py        winning-pattern analysis, derivative scripts, ad style prompts
dashboard/         the /shortform page (React via the hermes plugin SDK)
tests/             pytest suite
```

Licensed under the terms in [LICENSE](LICENSE).
