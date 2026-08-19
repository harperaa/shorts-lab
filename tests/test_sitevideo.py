"""Site Video: state, briefs, plan save, artifact resolution, kanban flow."""
import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

PKG = "shorts_lab_test_pkg"
ROOT = Path(__file__).resolve().parent.parent
if PKG not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        PKG, str(ROOT / "__init__.py"),
        submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[PKG] = mod
    spec.loader.exec_module(mod)

sitevideo = importlib.import_module(f"{PKG}.sitevideo")


@pytest.fixture()
def tmp_home(tmp_path, monkeypatch):
    home = tmp_path / "hermes-home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


@pytest.fixture()
def fake_kanban(monkeypatch):
    class FakeKB:
        def __init__(self):
            self.tasks = {}
            self.counter = 0
            self.created = []

        class _Ctx:
            def __init__(self, outer):
                self.outer = outer

            def __enter__(self):
                return self.outer

            def __exit__(self, *exc):
                return False

        def connect_closing(self):
            return FakeKB._Ctx(self)

        def create_task(self, conn, *, title, body, created_by,
                        workspace_kind, skills, assignee=None, priority=None):
            assert assignee, "tasks must be born assigned"
            self.counter += 1
            tid = f"t_sv{self.counter}"
            rec = {"id": tid, "title": title, "body": body, "skills": skills,
                   "status": "ready"}
            self.tasks[tid] = rec
            self.created.append(rec)
            return tid

        def get_task(self, conn, task_id):
            rec = self.tasks.get(task_id)
            return type("T", (), rec)() if rec else None

    fake = FakeKB()
    monkeypatch.setattr(sitevideo, "_kanban", lambda: fake)
    monkeypatch.setattr(sitevideo, "kick_dispatcher", lambda: True)
    monkeypatch.setattr(sitevideo, "resolve_kanban_assignee", lambda: "default")
    monkeypatch.setattr(sitevideo, "_find_worker_session", lambda tid: None)
    return fake


def test_state_defaults(tmp_home):
    st = sitevideo.load_state()
    assert st["defaultUrl"] == sitevideo.DEFAULT_URL
    assert st["projects"] == {}


def test_start_plan_validates_url(tmp_home, fake_kanban):
    assert "error" in sitevideo.start_plan("not-a-url")
    assert "error" in sitevideo.start_plan("")


def test_start_plan_creates_task_and_project(tmp_home, fake_kanban):
    result = sitevideo.start_plan("https://example.com/features")
    assert result["ok"]
    body = fake_kanban.created[0]["body"]
    assert "screenshot.mjs" in body
    assert "60-second" in body
    assert "plan.json" in body
    assert "remotion still" in body            # sanity-frame proof step
    assert "kanban_block" in body              # honest failure path
    assert fake_kanban.created[0]["skills"] == list(sitevideo.PLAN_SKILLS)
    st = sitevideo.load_state()
    assert st["defaultUrl"] == "https://example.com/features"
    proj = st["projects"][result["projectId"]]
    assert Path(proj["dir"]).is_dir()


def test_render_requires_plan(tmp_home, fake_kanban):
    result = sitevideo.start_plan("https://example.com")
    pid = result["projectId"]
    assert "error" in sitevideo.start_render(pid)
    plan = {"title": "T", "url": "https://example.com", "accent": "#14b8a6",
            "screenshot": "s.png", "pageWidth": 1440, "pageHeight": 3000,
            "scenes": [{"caption": "c", "seconds": 5,
                        "region": {"x": 0, "y": 0, "w": 1440, "h": 900}}],
            "outro": {"headline": "Go", "caption": ""}}
    assert sitevideo.save_plan(pid, plan)["ok"]
    r = sitevideo.start_render(pid)
    assert r["ok"]
    body = fake_kanban.created[-1]["body"]
    assert "remotion render" in body and "render.mp4" in body


def test_save_plan_rejects_bad_shapes(tmp_home, fake_kanban):
    pid = sitevideo.start_plan("https://example.com")["projectId"]
    assert "error" in sitevideo.save_plan(pid, {})
    assert "error" in sitevideo.save_plan("nope", {"scenes": [1]})


def test_public_state_shape(tmp_home, fake_kanban):
    pid = sitevideo.start_plan("https://example.com")["projectId"]
    st = sitevideo.public_state()
    assert st["defaultUrl"] == "https://example.com"
    entry = st["projects"][0]
    assert entry["id"] == pid
    assert entry["planStatus"] == "open"
    assert entry["hasPlan"] is False


def test_project_file_guard(tmp_home, fake_kanban):
    pid = sitevideo.start_plan("https://example.com")["projectId"]
    d = Path(sitevideo.load_state()["projects"][pid]["dir"])
    (d / "render.mp4").write_bytes(b"x")
    (d / "secret.txt").write_text("no")
    assert sitevideo.project_file(pid, "render.mp4") is not None
    assert sitevideo.project_file(pid, "secret.txt") is None
    assert sitevideo.project_file(pid, "../state.json") is None
    assert sitevideo.project_file("nope", "render.mp4") is None


def test_template_ships_complete(tmp_home):
    t = sitevideo.TEMPLATE_DIR
    for rel in ("package.json", "src/index.ts", "src/Root.tsx",
                "src/SiteDescriber.tsx", "scripts/screenshot.mjs",
                "tsconfig.json"):
        assert (t / rel).exists(), rel
    pkg = json.loads((t / "package.json").read_text())
    assert "remotion" in pkg["dependencies"]
