"""Site Video — 60-second Remotion describer videos for a URL.

The Shorts Lab "Site Video" tab drives this module:

1. PLAN: a kanban worker captures the page (full-page screenshot + candidate
   section regions via the bundled Remotion headless chrome), reviews the
   content, and writes a multi-phase 60s describer plan — intro, 5-8 scenes
   that pan/zoom to the page regions being described, outro CTA.
2. EDIT: the tab previews the plan (camera math mirrored in CSS) and lets
   the user edit captions, durations, and regions; plan.json is the single
   source of truth (it is exactly Remotion's input props).
3. RENDER: a second worker runs `npx remotion render` in a cached copy of
   the bundled template; the mp4 lands in the project folder for download.

Projects live at $HERMES_HOME/plugins-data/shorts-lab/sitevideo/<id>/
(plan.json, screenshot.png, page.json, render.mp4). The Remotion template
ships with the plugin at <plugin>/remotion-site-video/.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    from . import store
except ImportError:  # standalone import (dashboard plugin_api path)
    import store  # type: ignore

PLUGIN_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = PLUGIN_DIR / "remotion-site-video"
STALE_MINUTES = 45
DEFAULT_URL = "https://www.skool.com/ai-cyber-value-creators"

PLAN_SKILLS = (
    "shorts-lab:remotion-best-practices",
    "shorts-lab:remotion-create",
)
RENDER_SKILLS = (
    "shorts-lab:remotion-best-practices",
    "shorts-lab:remotion-render",
)

_OPEN_KANBAN_STATUSES = {"triage", "ready", "running", "blocked", "in_review"}


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def sitevideo_dir() -> Path:
    d = store.data_dir() / "sitevideo"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state_path() -> Path:
    return sitevideo_dir() / "state.json"


def load_state() -> dict:
    try:
        data = json.loads(_state_path().read_text())
        if isinstance(data, dict):
            data.setdefault("defaultUrl", DEFAULT_URL)
            data.setdefault("projects", {})
            return data
    except (OSError, ValueError):
        pass
    return {"defaultUrl": DEFAULT_URL, "projects": {}}


def save_state(state: dict) -> None:
    _state_path().write_text(json.dumps(state, indent=1, sort_keys=True))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(url: str) -> str:
    s = re.sub(r"^https?://", "", (url or "").strip().lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:48] or "site"
    return f"{s}-{time.strftime('%Y%m%d-%H%M%S')}"


# ---------------------------------------------------------------------------
# Kanban plumbing (same contract as the suite's other worker flows)
# ---------------------------------------------------------------------------

def _kanban():
    try:
        from hermes_cli import kanban_db
        return kanban_db
    except ImportError:
        return None


def _task_open(kb, conn_kb, task_id: str) -> bool:
    try:
        task = kb.get_task(conn_kb, task_id)
    except Exception:
        return False
    if task is None:
        return False
    status = getattr(task, "status", None) or (
        task.get("status") if isinstance(task, dict) else None)
    return str(status) in _OPEN_KANBAN_STATUSES


def resolve_kanban_assignee() -> str:
    try:
        from hermes_cli.config import load_config
        val = ((load_config() or {}).get("kanban", {}) or {}).get(
            "default_assignee")
        if isinstance(val, str) and val.strip():
            return val.strip()
    except Exception:
        pass
    return "default"


def kick_dispatcher() -> bool:
    try:
        kb = _kanban()
        with kb.connect_closing() as conn:
            kb.dispatch_once(conn, max_spawn=1,
                             default_assignee=resolve_kanban_assignee())
        return True
    except Exception:
        return False


def _find_worker_session(kanban_task_id: str) -> Optional[str]:
    try:
        import sqlite3
        try:
            from hermes_constants import get_hermes_home
            db = str(get_hermes_home() / "state.db")
        except ImportError:
            db = os.path.expanduser(os.path.join(
                os.environ.get("HERMES_HOME", "~/.hermes"), "state.db"))
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT session_id FROM messages WHERE role = 'user' "
                "AND content = ? ORDER BY id DESC LIMIT 1",
                (f"work kanban task {kanban_task_id}",)).fetchone()
        finally:
            conn.close()
        return row[0] if row else None
    except Exception:
        return None


def _age_minutes(created_at: Optional[str]) -> Optional[float]:
    if not created_at:
        return None
    try:
        t = datetime.fromisoformat(created_at)
        return (datetime.now(timezone.utc) - t).total_seconds() / 60.0
    except ValueError:
        return None


def _task_state(kb, conn_kb, task_id: str, created_at: Optional[str]) -> str:
    task = kb.get_task(conn_kb, task_id)
    if task is None:
        return "gone"
    status = getattr(task, "status", None) or (
        task.get("status") if isinstance(task, dict) else "")
    if str(status) == "done":
        return "done"
    age = _age_minutes(created_at)
    if age is not None and age >= STALE_MINUTES:
        return "stale"
    return "open"


# ---------------------------------------------------------------------------
# Briefs
# ---------------------------------------------------------------------------

def _setup_lines(workdir: Path) -> list[str]:
    return [
        "### Workspace setup (idempotent — run first, every time)",
        f"The Remotion template ships at {TEMPLATE_DIR}. Work in a CACHED",
        f"copy at {workdir} so npm installs survive between runs:",
        f"  mkdir -p {workdir}",
        f"  rsync -a --exclude node_modules --exclude out {TEMPLATE_DIR}/ {workdir}/",
        f"  cd {workdir} && npm install --no-audit --no-fund",
        "npm install is cached after the first run. If `npx remotion` later",
        "reports a missing browser, run `npx remotion browser ensure` once.",
        "",
    ]


def build_plan_brief(url: str, project_dir: Path, workdir: Path) -> str:
    plan_path = project_dir / "plan.json"
    return "\n".join([
        "## MANDATORY: Plan a 60-second site describer video for ONE URL.",
        "",
        f"**URL:** {url}",
        f"**Project directory:** {project_dir}",
        f"**Deliverable:** {plan_path} (+ screenshot.png + page.json)",
        "",
        "You do ALL steps yourself in this session. Load the",
        "`shorts-lab:remotion-best-practices` and `shorts-lab:remotion-create`",
        "skills for grounding on the composition this plan drives.",
        "",
        *_setup_lines(workdir),
        "### Step 1 — Capture the page",
        f"  cd {workdir} && node scripts/screenshot.mjs '{url}' '{project_dir}'",
        "This writes screenshot.png (full page) and page.json (title, page",
        "dimensions, and candidate SECTION REGIONS with their visible text).",
        "If the capture fails (site unreachable, bot-blocked), kanban_block",
        "with kind needs_input explaining exactly what failed — do not fake.",
        "",
        "### Step 1.5 — Stage the screenshot for Remotion",
        "Remotion serves local assets from the project's public/ dir:",
        f"  mkdir -p {workdir}/public",
        f"  cp {project_dir}/screenshot.png {workdir}/public/{project_dir.name}.png",
        "",
        "### Step 2 — Review the site and write the describer plan",
        f"Read {project_dir}/page.json. Using the section texts and regions,",
        "write the video plan: a 60-second guided tour that DESCRIBES the",
        "site's features while the camera pans/zooms to the region being",
        "described. Structure:",
        "- intro (title card, ~2.5s, automatic) — pick a punchy `title`",
        "- 5-8 scenes, `seconds` between 5 and 10, TOTALING 50-55s: each has",
        "  a short `headline` (2-4 words), a spoken-style `caption` (one",
        "  conversational sentence, 12-22 words, describing what the viewer",
        "  is seeing and why it matters), and a `region` — copy the rect of",
        "  the page.json section being described (adjust to frame it well;",
        "  scene 1 should be the top of the page / hero).",
        "- outro (~4s, automatic): `outro.headline` = the site's core CTA,",
        "  `outro.caption` = one closing line.",
        f"Write EXACTLY this JSON shape to {plan_path}:",
        "```json",
        "{",
        '  "title": "…", "url": "' + url + '", "accent": "#14b8a6",',
        '  "screenshot": "' + project_dir.name + '.png",',
        '  "pageWidth": <from page.json>, "pageHeight": <from page.json>,',
        '  "scenes": [{"headline": "…", "caption": "…", "seconds": 7,',
        '              "region": {"x": 0, "y": 0, "w": 1440, "h": 900}}],',
        '  "outro": {"headline": "…", "caption": "…"}',
        "}",
        "```",
        "Validate: `node -e \"JSON.parse(require('fs').readFileSync(process."
        "argv[1]))\" " + str(plan_path) + "`",
        "",
        "### Step 3 — Sanity-render one frame (proof the plan drives video)",
        f"  cd {workdir} && npx remotion still src/index.ts SiteDescriber",
        f"    {project_dir}/preview-frame.png --frame=120 --props={plan_path}",
        "If the still fails, fix plan.json (schema mismatch is the usual",
        "cause) and retry until it renders.",
        "",
        "### Step 4 — Publish",
        "Attach plan.json and preview-frame.png to THIS kanban task with",
        "`kanban_attach`, then `kanban_complete` summarizing the scene list",
        "(headline + seconds each) and total runtime.",
        "",
        "### CRITICAL RULES",
        f"- Every output file goes under exactly {project_dir}/ — no other paths.",
        "- Captions are spoken-style, concrete, about THIS site's visible",
        "  content — never generic filler like 'this section shows content'.",
        "- Scene regions must come from page.json rects (framed sensibly),",
        "  so the camera genuinely lands on what the caption describes.",
    ])


def build_render_brief(project_dir: Path, workdir: Path) -> str:
    plan_path = project_dir / "plan.json"
    out_path = project_dir / "render.mp4"
    return "\n".join([
        "## MANDATORY: Render ONE site describer video from its plan.",
        "",
        f"**Plan:** {plan_path}",
        f"**Output:** {out_path}",
        "",
        "Load the `shorts-lab:remotion-render` skill.",
        "",
        *_setup_lines(workdir),
        "### Stage the screenshot (idempotent)",
        f"  mkdir -p {workdir}/public",
        f"  cp {project_dir}/screenshot.png {workdir}/public/{project_dir.name}.png",
        "",
        "### Render",
        f"  cd {workdir} && npx remotion render src/index.ts SiteDescriber",
        f"    {out_path} --props={plan_path} --codec=h264",
        "First render downloads Remotion's headless chrome (~2 min) — that",
        "is normal. If rendering fails on missing shared libraries, run",
        "`npx remotion browser ensure` and read its output for the apt",
        "packages it names.",
        "",
        "### Verify + publish",
        f"- `test -s {out_path}` and check the reported duration is ~55-65s.",
        "- Attach render.mp4 to THIS kanban task with `kanban_attach`, then",
        "  `kanban_complete` with the file path, duration, and size.",
    ])


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------

def _create_task(title: str, body: str, skills: tuple[str, ...]) -> str:
    kb = _kanban()
    if kb is None:
        raise RuntimeError("kanban unavailable")
    with kb.connect_closing() as conn_kb:
        task_id = kb.create_task(
            conn_kb,
            title=title,
            body=body,
            assignee=resolve_kanban_assignee(),
            created_by="shorts-lab",
            workspace_kind="scratch",
            skills=list(skills),
            priority=10,
        )
    kick_dispatcher()
    return task_id


def start_plan(url: str) -> dict[str, Any]:
    url = (url or "").strip()
    if not re.match(r"^https?://[^\s]+$", url):
        return {"error": "enter a valid http(s) URL"}
    state = load_state()
    state["defaultUrl"] = url
    pid = _slug(url)
    project_dir = sitevideo_dir() / pid
    project_dir.mkdir(parents=True, exist_ok=True)
    workdir = sitevideo_dir() / "_workdir"
    try:
        task_id = _create_task(
            f"Site Video plan: {url[:60]}",
            build_plan_brief(url, project_dir, workdir),
            PLAN_SKILLS)
    except RuntimeError as exc:
        return {"error": str(exc)}
    state["projects"][pid] = {
        "url": url, "dir": str(project_dir), "createdAt": _now_iso(),
        "planTaskId": task_id, "planCreatedAt": _now_iso(),
    }
    save_state(state)
    return {"ok": True, "projectId": pid, "taskId": task_id}


def start_render(project_id: str) -> dict[str, Any]:
    state = load_state()
    proj = state["projects"].get(project_id)
    if not proj:
        return {"error": f"unknown project: {project_id}"}
    project_dir = Path(proj["dir"])
    if not (project_dir / "plan.json").exists():
        return {"error": "no plan.json yet — generate the plan first"}
    workdir = sitevideo_dir() / "_workdir"
    try:
        task_id = _create_task(
            f"Site Video render: {proj.get('url', project_id)[:60]}",
            build_render_brief(project_dir, workdir),
            RENDER_SKILLS)
    except RuntimeError as exc:
        return {"error": str(exc)}
    proj["renderTaskId"] = task_id
    proj["renderCreatedAt"] = _now_iso()
    save_state(state)
    return {"ok": True, "taskId": task_id}


def save_plan(project_id: str, plan: dict) -> dict[str, Any]:
    state = load_state()
    proj = state["projects"].get(project_id)
    if not proj:
        return {"error": f"unknown project: {project_id}"}
    if not isinstance(plan, dict) or not plan.get("scenes"):
        return {"error": "plan must be an object with a scenes list"}
    (Path(proj["dir"]) / "plan.json").write_text(json.dumps(plan, indent=1))
    return {"ok": True}


def public_state() -> dict[str, Any]:
    state = load_state()
    kb = _kanban()
    projects = []
    with (kb.connect_closing() if kb else _NullCtx()) as conn_kb:
        for pid, proj in sorted(state["projects"].items(),
                                key=lambda kv: kv[1].get("createdAt") or "",
                                reverse=True)[:12]:
            d = Path(proj["dir"])
            entry: dict[str, Any] = {
                "id": pid, "url": proj.get("url"),
                "createdAt": proj.get("createdAt"),
                "hasPlan": (d / "plan.json").exists(),
                "hasScreenshot": (d / "screenshot.png").exists(),
                "hasRender": (d / "render.mp4").exists(),
            }
            if entry["hasPlan"]:
                try:
                    entry["plan"] = json.loads((d / "plan.json").read_text())
                except ValueError:
                    entry["plan"] = None
            if kb and proj.get("planTaskId"):
                entry["planStatus"] = _task_state(
                    kb, conn_kb, proj["planTaskId"], proj.get("planCreatedAt"))
                entry["planSession"] = _find_worker_session(proj["planTaskId"])
            if kb and proj.get("renderTaskId"):
                entry["renderStatus"] = _task_state(
                    kb, conn_kb, proj["renderTaskId"],
                    proj.get("renderCreatedAt"))
                entry["renderSession"] = _find_worker_session(
                    proj["renderTaskId"])
            if entry["hasRender"]:
                entry["renderBytes"] = (d / "render.mp4").stat().st_size
            projects.append(entry)
    return {"defaultUrl": state.get("defaultUrl") or DEFAULT_URL,
            "projects": projects}


class _NullCtx:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


def project_file(project_id: str, name: str) -> Optional[Path]:
    """Resolve a downloadable artifact inside one project dir (no traversal)."""
    if name not in ("render.mp4", "screenshot.png", "preview-frame.png",
                    "plan.json"):
        return None
    state = load_state()
    proj = state["projects"].get(project_id)
    if not proj:
        return None
    p = Path(proj["dir"]) / name
    return p if p.exists() else None
