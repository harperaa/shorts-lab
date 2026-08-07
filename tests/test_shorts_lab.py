"""shorts-lab tests — shared channel bridge, shorts fetch, meta ads, kie,
analysis, creations."""
from __future__ import annotations

import importlib
import importlib.util
import json
import sqlite3
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

store = importlib.import_module(f"{PKG}.store")
transcripts = importlib.import_module(f"{PKG}.transcripts")
meta_ads = importlib.import_module(f"{PKG}.meta_ads")
kie = importlib.import_module(f"{PKG}.kie")
analysis = importlib.import_module(f"{PKG}.analysis")
imagegen = importlib.import_module(f"{PKG}.imagegen")
surge = importlib.import_module(f"{PKG}.surge")


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    for var in ("TRANSCRIPT_API_KEY", "META_ACCESS_TOKEN", "KIE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


# ---------------------------------------------------------------------------
# Shared competitor list (the YouTube Insights bridge)
# ---------------------------------------------------------------------------

def test_channel_bridge_shares_yti_db(home):
    assert store.list_channels() == []
    store.add_channel("somecreator")          # normalizes to @somecreator
    store.add_channel("@another")
    assert store.list_channels() == ["@somecreator", "@another"]

    # the rows live in the YouTube Insights database — same source of truth
    yti_db = home / "plugins-data" / "youtube-insights" / "data.db"
    assert yti_db.exists()
    conn = sqlite3.connect(yti_db)
    rows = [r[0] for r in
            conn.execute("SELECT handle FROM channels ORDER BY added_at")]
    conn.close()
    assert rows == ["@somecreator", "@another"]

    # and edits made by youtube-insights show up here
    conn = sqlite3.connect(yti_db)
    conn.execute("INSERT OR IGNORE INTO channels(handle, added_at) "
                 "VALUES ('@fromyti', '2026-01-01T00:00:00')")
    conn.commit()
    conn.close()
    assert "@fromyti" in store.list_channels()

    store.remove_channel("somecreator")
    assert "@somecreator" not in store.list_channels()


# ---------------------------------------------------------------------------
# Shorts store + fetch
# ---------------------------------------------------------------------------

def test_upsert_short_refresh_keeps_transcript(home):
    created = store.upsert_short("v1", "@c", "Hook talk", "l", None, 45.0,
                                 100, "", "the transcript")
    assert created is True
    again = store.upsert_short("v1", "@c", "Hook talk v2", "l", None, 45.0,
                               250, "", "")
    assert again is False
    s = store.list_shorts(9999)[0]
    assert s["title"] == "Hook talk v2"
    assert s["view_count"] == 250
    assert s["transcript"] == "the transcript"     # empty never clobbers


def test_fetch_shorts_keeps_only_shorts(home, monkeypatch):
    import time as _time
    store.add_channel("@creator")
    now = _time.time()
    recent = __import__("datetime").datetime.fromtimestamp(
        now - 3600, __import__("datetime").timezone.utc).isoformat()

    def fake_get(url, headers):
        assert headers["Authorization"] == "Bearer test-key"
        if "channel/latest" in url:
            return 200, {"results": [
                {"videoId": "sh1", "title": "A short", "published": recent,
                 "link": "https://youtube.com/shorts/sh1", "viewCount": 5000},
                {"videoId": "long1", "title": "A long video",
                 "published": recent,
                 "link": "https://youtube.com/watch?v=long1",
                 "viewCount": 900},
                {"videoId": "sneaky", "title": "Unlabeled short",
                 "published": recent,
                 "link": "https://youtube.com/watch?v=sneaky",
                 "viewCount": 700},
            ]}
        if "video_url=sh1" in url:
            return 200, {"transcript": [
                {"start": 0, "duration": 3, "text": "stop scrolling"},
                {"start": 40, "duration": 5, "text": "the hook pays off"}]}
        if "video_url=long1" in url:
            return 200, {"transcript": [
                {"start": 0, "duration": 4, "text": "welcome back"},
                {"start": 600, "duration": 5, "text": "outro"}]}
        if "video_url=sneaky" in url:
            return 200, {"transcript": [
                {"start": 0, "duration": 3, "text": "quick tip"},
                {"start": 50, "duration": 4, "text": "done"}]}
        return 404, {"error": "unknown"}

    monkeypatch.setenv("TRANSCRIPT_API_KEY", "test-key")
    summary = transcripts.fetch_shorts(http_get=fake_get, sleep=lambda s: None)
    assert summary["shorts"] == 2          # sh1 (link) + sneaky (duration)
    assert summary["new"] == 2
    ids = {s["video_id"] for s in store.list_shorts(30)}
    assert ids == {"sh1", "sneaky"}
    sh1 = [s for s in store.list_shorts(30) if s["video_id"] == "sh1"][0]
    assert "stop scrolling" in sh1["transcript"]
    assert sh1["duration_seconds"] == 45.0


# ---------------------------------------------------------------------------
# Meta ads
# ---------------------------------------------------------------------------

def test_meta_ads_pull_and_longest_running(home, monkeypatch):
    monkeypatch.setenv("META_ACCESS_TOKEN", "tok")
    calls = []

    def fake_get(url, params=None, retries=3):
        calls.append((url, params))
        return {"data": [
            {"id": "a1", "page_id": "77", "page_name": "Acme",
             "ad_snapshot_url": "https://fb.com/a1",
             "ad_delivery_start_time": "2026-01-01",
             "ad_delivery_stop_time": None,
             "publisher_platforms": ["facebook", "instagram"]},
            {"id": "a2", "page_id": "77", "page_name": "Acme",
             "ad_snapshot_url": "https://fb.com/a2",
             "ad_delivery_start_time": "2026-06-01",
             "ad_delivery_stop_time": "2026-06-20",
             "publisher_platforms": ["facebook"]},
        ]}

    monkeypatch.setattr(meta_ads, "_get", fake_get)
    ads, new = meta_ads.pull_page_ads("77")
    assert len(ads) == 2 and new == 2
    assert calls[0][1]["sort_by"] == "longest_running"

    stored = store.list_ads()
    # active long-runner first, ended one after
    assert stored[0]["archive_id"] == "a1"
    assert stored[0]["active"] == 1
    assert stored[0]["daysRunning"] > stored[1]["daysRunning"]
    assert stored[1]["daysRunning"] == 19
    # monitored page recorded with its resolved name
    pages = store.list_ad_pages()
    assert pages[0]["page_id"] == "77" and pages[0]["name"] == "Acme"


def test_meta_ads_search_ranks_pages(home, monkeypatch):
    monkeypatch.setenv("META_ACCESS_TOKEN", "tok")

    def fake_get(url, params=None, retries=3):
        return {"data": [{"page_id": "1", "page_name": "Big Brand"}] * 5 +
                        [{"page_id": "2", "page_name": "Small Brand"}] * 2}

    monkeypatch.setattr(meta_ads, "_get", fake_get)
    results = meta_ads.search_pages("brand")
    assert results[0]["pageId"] == "1" and results[0]["adCount"] == 5
    assert results[1]["adCount"] == 2


# ---------------------------------------------------------------------------
# KIE
# ---------------------------------------------------------------------------

def test_kie_submit_shapes(home, monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "k")
    sent = {}

    def fake_post(url, body, timeout=60):
        sent["url"] = url
        sent["body"] = body
        return {"code": 200, "data": {"taskId": "t-123"}}

    monkeypatch.setattr(kie, "_post_json", fake_post)

    # edit mode: source first, style refs follow — live-verified strings
    tid = kie.submit_image("make it pop", source_url="https://h/src.jpg",
                           ref_urls=["https://h/style.jpg"])
    assert tid == "t-123"
    assert sent["body"]["model"] == "google/nano-banana-edit"
    assert sent["body"]["input"]["image_urls"] == [
        "https://h/src.jpg", "https://h/style.jpg"]

    # fresh mode: aspect ratio, default model
    kie.submit_image("fresh ad", aspect_ratio="9:16")
    assert sent["body"]["model"] == "nano-banana-2"
    assert sent["body"]["input"]["aspect_ratio"] == "9:16"


def test_kie_check_task_parses_result_json(home, monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "k")

    def fake_get(url, timeout=30):
        return {"data": {"state": "success",
                         "resultJson": json.dumps(
                             {"resultUrls": ["https://cdn/img.png"]})}}

    monkeypatch.setattr(kie, "_get_json", fake_get)
    tick = kie.check_task("t-1")
    assert tick == {"state": "success", "url": "https://cdn/img.png"}


def test_save_asset_validates(home):
    aid = kie.save_asset("me.png", b"x" * 100)
    assert (store.assets_dir() / aid).exists()
    with pytest.raises(RuntimeError):
        kie.save_asset("notes.txt", b"x")
    with pytest.raises(RuntimeError):
        kie.save_asset("big.jpg", b"x" * (16 * 1024 * 1024))


# ---------------------------------------------------------------------------
# Analysis (fake LLM)
# ---------------------------------------------------------------------------

class _FakeRes:
    def __init__(self, parsed):
        self.parsed = parsed


class _FakeLlm:
    def __init__(self, parsed):
        self._parsed = parsed

    def complete_structured(self, **kw):
        return _FakeRes(self._parsed)


def test_marketing_context_loads_skills(home, tmp_path, monkeypatch):
    skills = tmp_path / "skills"
    (skills / "video-script").mkdir(parents=True)
    (skills / "video-script" / "SKILL.md").write_text("# Hooks first\nAlways")
    monkeypatch.setenv("SHORTS_LAB_SKILLS_DIR", str(skills))
    ctx = analysis.marketing_context()
    assert "Hooks first" in ctx and "MARKETING FRAMEWORKS" in ctx


def test_analyze_shorts_saves_kv(home, monkeypatch):
    store.upsert_short("v1", "@c", "Winner", "l", None, 40.0, 90000, "",
                       "stop scrolling this is the hook")
    parsed = {"summary": "s", "channels": [], "winningHooks": ["h1"],
              "winningMessages": [], "winningFormats": ["f1"],
              "winningStyles": [], "topShorts": [], "opportunities": ["o1"]}
    monkeypatch.setattr(analysis, "_llm", lambda: _FakeLlm(parsed))
    out = analysis.analyze_shorts()
    assert out["winningHooks"] == ["h1"] and out["shortCount"] == 1
    assert store.kv_get("shortsAnalysis")["winningFormats"] == ["f1"]


def test_create_derivative_builds_markdown(home, monkeypatch):
    parsed = {"title": "My Short", "hook": "Stop scrolling",
              "script": "[0:00] Stop scrolling…", "shotList": ["talking head"],
              "caption": "watch this", "hashtags": ["ai", "#cyber"],
              "patternUsed": "cold-open claim (from @c)"}
    monkeypatch.setattr(analysis, "_llm", lambda: _FakeLlm(parsed))
    cid = analysis.create_derivative("teach ai security tips")
    c = store.get_creation(cid)
    assert c["kind"] == "short-script" and c["status"] == "ready"
    assert "# My Short" in c["content"]
    assert "#ai #cyber" in c["content"]
    assert c["source"]["pattern"].startswith("cold-open")


def test_build_ad_prompt(home, monkeypatch):
    parsed = {"title": "Bootcamp ad", "generationPrompt": "recreate…",
              "adCopy": "Join now", "notes": "kept the layout"}
    monkeypatch.setattr(analysis, "_llm", lambda: _FakeLlm(parsed))
    plan = analysis.build_ad_prompt("ai bootcamp", "winning acme ad")
    assert plan["generationPrompt"] == "recreate…"


def test_shorts_search_tool(home):
    store.upsert_short("v1", "@c", "AI hooks masterclass", "l", None, 40.0,
                       500, "", "here is how hooks work")
    found = json.loads(analysis.tool_shorts_search({"query": "hooks"}))
    assert found["count"] == 1
    assert found["shorts"][0]["videoId"] == "v1"
    nothing = json.loads(analysis.tool_shorts_search({"query": "zzz"}))
    assert nothing["count"] == 0


def test_store_key_and_validate_token(home, monkeypatch):
    meta_ads.store_key("META_ACCESS_TOKEN", " EAAB-token-123 ")
    env_file = (home / ".env").read_text()
    assert "META_ACCESS_TOKEN=EAAB-token-123" in env_file
    import os
    assert os.environ["META_ACCESS_TOKEN"] == "EAAB-token-123"
    # replace, never duplicate
    meta_ads.store_key("META_ACCESS_TOKEN", "EAAB-token-456")
    env_file = (home / ".env").read_text()
    assert env_file.count("META_ACCESS_TOKEN=") == 1
    assert "EAAB-token-456" in env_file
    with pytest.raises(ValueError):
        meta_ads.store_key("RANDOM_VAR", "x")
    with pytest.raises(ValueError):
        meta_ads.store_key("META_ACCESS_TOKEN", "two\nlines")

    def fake_get(url, params=None, retries=3):
        assert "/me" in url
        if params["access_token"] == "good":
            return {"id": "1", "name": "Allen"}
        return {"error": {"message": "Invalid OAuth access token"}}

    monkeypatch.setattr(meta_ads, "_get", fake_get)
    assert meta_ads.validate_token("good") == {"ok": True, "name": "Allen"}
    bad = meta_ads.validate_token("bad")
    assert bad["ok"] is False and "Invalid" in bad["error"]


def test_apify_pull_normalizes_and_source_routing(home, monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_api_x")
    captured = {}

    class FakeResp:
        def __init__(self, payload):
            self._p = payload

        def read(self):
            return json.dumps(self._p).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=280):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        return FakeResp([
            {"adArchiveID": "111", "pageID": "77", "pageName": "Acme",
             "startDate": 1735689600, "endDate": None, "isActive": True,
             "publisherPlatform": ["FACEBOOK"]},
            {"adArchiveId": "222", "pageId": "77", "pageName": "Acme",
             "startDate": "2026-06-01", "endDate": "2026-06-20",
             "isActive": False, "publisherPlatform": ["INSTAGRAM"]},
        ])

    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", fake_urlopen)

    items, new = meta_ads.apify_pull_page_ads("77", limit=10)
    assert len(items) == 2 and new == 2
    assert "acts/apify~facebook-ads-scraper/run-sync-get-dataset-items" \
        in captured["url"]
    assert "view_all_page_id=77" in captured["body"]["startUrls"][0]["url"]

    stored = {a["archive_id"]: a for a in store.list_ads()}
    assert stored["111"]["active"] == 1
    assert stored["111"]["snapshot_url"].endswith("?id=111")
    assert stored["222"]["active"] == 0 and stored["222"]["daysRunning"] == 19

    # source routing: apify key present -> apify; explicit choice wins
    assert meta_ads.get_ads_source() == "apify"
    meta_ads.set_ads_source("meta")
    assert meta_ads.get_ads_source() == "meta"
    with pytest.raises(ValueError):
        meta_ads.set_ads_source("bogus")


def test_apify_token_validation(home, monkeypatch):
    class FakeResp:
        def read(self):
            return json.dumps({"data": {"username": "allen"}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=20: FakeResp())
    assert meta_ads.validate_apify_token("t")["ok"] is True


def test_apify_keyword_search_and_routing(home, monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_api_x")
    captured = {}

    class FakeResp:
        def __init__(self, payload):
            self._p = payload

        def read(self):
            return json.dumps(self._p).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=280):
        captured["body"] = json.loads(req.data.decode())
        return FakeResp([
            {"pageID": "77", "pageName": "Lifestyle Founders Group"},
            {"pageID": "77", "pageName": "Lifestyle Founders Group"},
            {"pageID": "88", "pageName": "Other Brand"},
        ])

    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", fake_urlopen)

    results = meta_ads.apify_search_pages("Lifestyle Founders Group")
    url0 = captured["body"]["startUrls"][0]["url"]
    assert "q=Lifestyle%20Founders%20Group" in url0
    assert "keyword_exact_phrase" in url0     # multi-word -> exact phrase
    assert "active_status=active" in url0     # search covers active ads only
    assert captured["body"]["activeStatus"] == "active"
    assert results[0]["pageId"] == "77"
    assert results[0]["name"] == "Lifestyle Founders Group"
    assert results[0]["nameMatch"] is True

    # source routing: apify key present -> keyword search goes via apify
    assert meta_ads.get_ads_source() == "apify"
    routed = meta_ads.search_pages_any("Lifestyle Founders Group")
    assert routed[0]["pageId"] == "77"


def test_search_ranks_name_match_over_volume(home):
    from collections import Counter
    counts = Counter({"999": 50, "77": 2})
    names = {"999": "Content Creator.com", "77": "AI Cyber Value Creator"}
    ranked = meta_ads._rank_pages(counts, names, "AI Cyber Value Creator")
    # the page actually NAMED that beats the noisy high-volume page
    assert ranked[0]["pageId"] == "77" and ranked[0]["nameMatch"] is True
    assert ranked[1]["pageId"] == "999" and ranked[1]["nameMatch"] is False


def test_apify_pull_stores_creative_and_requests_active(home, monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_api_x")
    captured = {}

    class FakeResp:
        def __init__(self, payload):
            self._p = payload

        def read(self):
            return json.dumps(self._p).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=280):
        captured["body"] = json.loads(req.data.decode())
        return FakeResp([{
            "adArchiveID": "111", "pageID": "77", "pageName": "Acme",
            "startDate": 1735689600, "isActive": True,
            "publisherPlatform": ["FACEBOOK"],
            "impressionsWithIndex": {"impressionsText": "<100",
                                     "impressionsIndex": -1},
            "snapshot": {
                "body": {"text": "You're technical. You know how systems work."},
                "title": "Join the program", "ctaText": "Learn More",
                "videos": [{"videoPreviewImageUrl": "https://cdn/v.jpg"}],
                "pageProfilePictureUrl": "https://cdn/p.jpg",
                "linkUrl": "https://example.com"},
        }])

    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", fake_urlopen)
    meta_ads.apify_pull_page_ads("77", limit=10)

    assert captured["body"]["activeStatus"] == "active"
    assert "active_status=active" in captured["body"]["startUrls"][0]["url"]
    ad = store.list_ads()[0]
    cr = ad["creative"]
    assert cr["body"].startswith("You're technical")
    assert cr["image"] == "https://cdn/v.jpg" and cr["video"] is True
    assert cr["cta"] == "Learn More"
    assert cr["profile"] == "https://cdn/p.jpg"
    assert cr["impressions"] == "<100"


def test_twice_daily_sync_jobs_are_separate_and_idempotent(home, monkeypatch):
    import types
    sync_job = importlib.import_module(f"{PKG}.sync_job")
    created, updated = [], []
    jobs_by_ref = {}

    fake_jobs = types.ModuleType("cron.jobs")

    def resolve_job_ref(ref):
        return jobs_by_ref.get(ref)

    def create_job(prompt, schedule, name=None, deliver=None,
                   script=None, no_agent=False, **kw):
        job = {"id": f"job-{len(created) + 1}", "name": name,
               "schedule": schedule, "script": script, "no_agent": no_agent}
        jobs_by_ref[job["id"]] = job
        jobs_by_ref[name] = job
        created.append(job)
        return job

    def update_job(job_id, updates):
        jobs_by_ref[job_id].update(updates)
        updated.append(updates)
        return jobs_by_ref[job_id]

    fake_jobs.resolve_job_ref = resolve_job_ref
    fake_jobs.create_job = create_job
    fake_jobs.update_job = update_job
    fake_cron = types.ModuleType("cron")
    fake_cron.jobs = fake_jobs
    monkeypatch.setitem(sys.modules, "cron", fake_cron)
    monkeypatch.setitem(sys.modules, "cron.jobs", fake_jobs)

    a = sync_job.ensure_ads_job()
    b = sync_job.ensure_shorts_job()
    assert len(created) == 2                      # two SEPARATE crons
    assert a["jobId"] != b["jobId"]
    assert a["schedule"] == "0 */12 * * *"        # twice a day
    assert b["schedule"] == "30 */12 * * *"       # staggered
    assert all(j["no_agent"] for j in created)

    # generated scripts exist and compile
    for name in ("shorts-lab-ads-sync.py", "shorts-lab-shorts-sync.py"):
        p = home / "scripts" / name
        assert p.exists()
        compile(p.read_text(), str(p), "exec")

    # idempotent: re-ensure updates, never duplicates
    sync_job.ensure_ads_job()
    assert len(created) == 2 and updated


def test_autosync_toggle_off_by_default_and_disables(home, monkeypatch):
    import types
    sync_job = importlib.import_module(f"{PKG}.sync_job")
    assert sync_job.is_enabled() is False        # OFF by default

    jobs_by_ref = {}
    updates_log = []
    fake_jobs = types.ModuleType("cron.jobs")
    fake_jobs.resolve_job_ref = lambda ref: jobs_by_ref.get(ref)

    def create_job(prompt, schedule, name=None, **kw):
        job = {"id": "j-" + name, "name": name, "schedule": schedule,
               "enabled": True}
        jobs_by_ref[job["id"]] = job
        jobs_by_ref[name] = job
        return job

    def update_job(job_id, updates):
        jobs_by_ref[job_id].update(updates)
        updates_log.append((job_id, updates))
        return jobs_by_ref[job_id]

    removed = []

    def remove_job(job_id):
        job = jobs_by_ref.pop(job_id, None)
        if job:
            jobs_by_ref.pop(job["name"], None)
            removed.append(job_id)
        return True

    fake_jobs.create_job = create_job
    fake_jobs.update_job = update_job
    fake_jobs.remove_job = remove_job
    fake_cron = types.ModuleType("cron")
    fake_cron.jobs = fake_jobs
    monkeypatch.setitem(sys.modules, "cron", fake_cron)
    monkeypatch.setitem(sys.modules, "cron.jobs", fake_jobs)

    out = sync_job.set_enabled(True)
    assert out["enabled"] is True and sync_job.is_enabled() is True
    assert "j-shorts-lab-ads-sync" in jobs_by_ref
    assert "j-shorts-lab-shorts-sync" in jobs_by_ref

    out = sync_job.set_enabled(False)
    assert out["enabled"] is False and sync_job.is_enabled() is False
    # OFF deletes — no zombie disabled jobs left behind
    assert len(removed) == 2
    assert "j-shorts-lab-ads-sync" not in jobs_by_ref
    assert "j-shorts-lab-shorts-sync" not in jobs_by_ref

    # ON again recreates cleanly
    out = sync_job.set_enabled(True)
    assert "j-shorts-lab-ads-sync" in jobs_by_ref
    sync_job.set_enabled(False)


def test_build_ad_prompt_variants(home, monkeypatch):
    captured = {}

    class FakeRes:
        parsed = {"title": "Bootcamp ad", "generationPrompt": "base prompt",
                  "variantPrompts": ["take 1", "take 2", "take 3"],
                  "copyVariants": ["copy A", "copy B", "copy C"],
                  "adCopy": "Join now", "notes": "kept the layout"}

    class FakeLlm:
        def complete_structured(self, **kw):
            captured["payload"] = kw["input"][0]["text"]
            return FakeRes()

    monkeypatch.setattr(analysis, "_llm", lambda: FakeLlm())
    plan = analysis.build_ad_prompt("ai bootcamp", "winning ad", variants=3)
    assert "VARIANTS REQUESTED: 3" in captured["payload"]
    # the winning copy must be treated as raw material, not背景 noise
    assert "RAW MATERIAL" in captured["payload"]
    assert "improved descendant" in captured["payload"]
    assert plan["variantPrompts"] == ["take 1", "take 2", "take 3"]
    assert plan["copyVariants"] == ["copy A", "copy B", "copy C"]
    # single ad: no variant instruction
    analysis.build_ad_prompt("ai bootcamp", "winning ad", variants=1)
    assert "VARIANTS REQUESTED" not in captured["payload"]


def test_spellcheck_image_parses_verdict(home, monkeypatch):
    captured = {}

    class FakeRes:
        parsed = {"textOk": False, "readText": "Skip the jbo line",
                  "issues": ["'jbo' should be 'job'"]}

    class FakeLlm:
        def complete_structured(self, **kw):
            captured["input"] = kw["input"]
            return FakeRes()

    monkeypatch.setattr(analysis, "_llm", lambda: FakeLlm())
    v = analysis.spellcheck_image("https://cdn/ad.png", "Skip the job line")
    assert captured["input"][0]["type"] == "image"
    assert captured["input"][0]["url"] == "https://cdn/ad.png"
    assert len(captured["input"]) == 1      # no portrait -> single image
    assert v["ok"] is False and "jbo" in v["issues"][0]
    assert v["personOk"] is True            # absent personMatch defaults ok


def test_qa_checks_person_against_source_portrait(home, monkeypatch):
    """Correct spelling but a DIFFERENT person than the supplied portrait
    must fail the gate (this is what triggers the auto-retry)."""
    captured = {}

    class FakeRes:
        parsed = {"textOk": True, "personMatch": False,
                  "readText": "Enroll now",
                  "issues": ["person mismatch: different woman than portrait"]}

    class FakeLlm:
        def complete_structured(self, **kw):
            captured["input"] = kw["input"]
            captured["instructions"] = kw["instructions"]
            return FakeRes()

    monkeypatch.setattr(analysis, "_llm", lambda: FakeLlm())
    v = analysis.spellcheck_image("https://cdn/ad.png", "Enroll now",
                                  source_url="data:image/png;base64,AAA")
    assert [i["url"] for i in captured["input"]] == [
        "https://cdn/ad.png", "data:image/png;base64,AAA"]
    assert "reference portrait" in captured["instructions"]
    assert v["ok"] is False and v["personOk"] is False
    assert "person mismatch" in v["issues"][0]


def test_build_ad_prompt_carries_identity_mandate(home, monkeypatch):
    captured = {}

    class FakeRes:
        parsed = {"title": "t", "generationPrompt": "p", "adCopy": "c",
                  "notes": "n"}

    class FakeLlm:
        def complete_structured(self, **kw):
            captured["input"] = kw["input"]
            return FakeRes()

    monkeypatch.setattr(analysis, "_llm", lambda: FakeLlm())
    analysis.build_ad_prompt("my offer", "", variants=2,
                             has_source_image=True)
    text = captured["input"][0]["text"]
    assert "IDENTITY IS NON-NEGOTIABLE" in text
    captured.clear()
    analysis.build_ad_prompt("my offer", "", variants=1,
                             has_source_image=False)
    assert "IDENTITY IS NON-NEGOTIABLE" not in captured["input"][0]["text"]


def test_creation_source_updates_persist(home):
    cid = store.create_creation("image-ad", "Ad", "brief", "c",
                                status="generating",
                                source={"prompt": "p", "retries": 0})
    store.update_creation(cid, source={"prompt": "p", "retries": 1,
                                       "lastIssues": ["x"]})
    c = store.get_creation(cid)
    assert c["source"]["retries"] == 1 and c["source"]["lastIssues"] == ["x"]


# ---------------------------------------------------------------------------
# image backend selection (instance model vs KIE)
# ---------------------------------------------------------------------------

def test_backend_defaults_to_kie_without_image_model(home, monkeypatch):
    monkeypatch.setattr(imagegen, "hermes_status",
                        lambda: {"available": False, "model": None,
                                 "canEdit": False})
    assert imagegen.get_backend() == "kie"


def test_backend_auto_prefers_loaded_model(home, monkeypatch):
    monkeypatch.setattr(imagegen, "hermes_status",
                        lambda: {"available": True, "model": "Grok Image",
                                 "canEdit": True})
    assert imagegen.get_backend() == "hermes"
    # explicit KIE choice wins over the loaded model
    imagegen.set_backend("kie")
    assert imagegen.get_backend() == "kie"
    imagegen.set_backend("auto")
    assert imagegen.get_backend() == "hermes"


def test_backend_hermes_choice_falls_back_when_unloaded(home, monkeypatch):
    imagegen.set_backend("hermes")
    monkeypatch.setattr(imagegen, "hermes_status",
                        lambda: {"available": False, "model": None,
                                 "canEdit": False})
    assert imagegen.get_backend() == "kie"
    with pytest.raises(ValueError):
        imagegen.set_backend("dall-e")


def test_asset_data_uri_no_hosting_needed(home):
    aid = kie.save_asset("photo.png", b"\x89PNG-fake-bytes" * 10)
    uri = imagegen.asset_data_uri(aid)
    assert uri.startswith("data:image/png;base64,")
    with pytest.raises(RuntimeError):
        imagegen.asset_data_uri("missing.png")


def test_hermes_generate_parses_tool_json(home, monkeypatch):
    import types
    calls = {}

    def fake_tool(prompt, aspect_ratio="1:1", image_url=None,
                  reference_image_urls=None):
        calls.update(prompt=prompt, image_url=image_url,
                     refs=reference_image_urls)
        return json.dumps({"success": True, "image": "https://fal/x.png"})

    fake_pkg = types.ModuleType("tools")
    fake_mod = types.ModuleType("tools.image_generation_tool")
    fake_mod.image_generate_tool = fake_tool
    # no plugin provider configured — dispatch falls through to FAL path
    fake_mod._dispatch_to_plugin_provider = lambda *a, **k: None
    fake_pkg.image_generation_tool = fake_mod
    monkeypatch.setitem(sys.modules, "tools", fake_pkg)
    monkeypatch.setitem(sys.modules, "tools.image_generation_tool", fake_mod)
    # never let the credential probe reach the real registry from tests
    monkeypatch.setattr(imagegen, "_probe_unconfigured_provider",
                        lambda: None)

    url = imagegen.hermes_generate("neon ad", source_url="data:image/png;a",
                                   ref_urls=["https://style.png", ""])
    assert url == "https://fal/x.png"
    assert calls["image_url"] == "data:image/png;a"
    assert calls["refs"] == ["https://style.png"]

    fake_mod.image_generate_tool = lambda **k: json.dumps(
        {"success": False, "error": "FAL_KEY is not set"})
    with pytest.raises(RuntimeError, match="FAL_KEY"):
        imagegen.hermes_generate("neon ad")

    # a configured plugin provider (grok / gpt-image) short-circuits FAL
    fake_mod._dispatch_to_plugin_provider = lambda *a, **k: json.dumps(
        {"success": True, "image": "/opt/data/cache/images/grok_1.png"})
    assert imagegen.hermes_generate("neon ad").endswith("grok_1.png")


def test_status_reports_configured_plugin_provider(home, monkeypatch):
    import types
    fake_pkg = types.ModuleType("tools")
    fake_mod = types.ModuleType("tools.image_generation_tool")
    fake_mod.check_image_generation_requirements = lambda: True
    fake_mod._active_image_capabilities = lambda: {
        "provider": "xAI", "model": "grok-imagine-image",
        "modalities": ["text"], "max_reference_images": 0}
    fake_pkg.image_generation_tool = fake_mod
    monkeypatch.setitem(sys.modules, "tools", fake_pkg)
    monkeypatch.setitem(sys.modules, "tools.image_generation_tool", fake_mod)
    st = imagegen.hermes_status()
    assert st == {"available": True, "provider": "xAI",
                  "model": "grok-imagine-image", "canEdit": False}


class _FakeGrokProvider:
    """Registry provider double — the grok-loaded-but-unconfigured case."""
    name = "xai"
    display_name = "xAI (Grok)"

    def is_available(self):
        return True

    def capabilities(self):
        return {"modalities": ["text", "image"], "max_reference_images": 2}

    def default_model(self):
        return "grok-imagine-image"

    def list_models(self):
        return [{"id": "grok-imagine-image", "display": "Grok Imagine Image"}]

    def generate(self, prompt, aspect_ratio="1:1", image_url=None,
                 reference_image_urls=None):
        self.last = {"prompt": prompt, "image_url": image_url,
                     "refs": reference_image_urls}
        return {"success": True, "image": "/opt/data/cache/images/g.png"}


def test_probe_lights_up_grok_without_config(home, monkeypatch):
    """grok 4.5 loaded + image_gen.provider unset -> Ads Lab still routes
    to Grok Imagine (the config opt-in is hermes-core policy, not ours)."""
    import types
    fake_pkg = types.ModuleType("tools")
    fake_mod = types.ModuleType("tools.image_generation_tool")
    fake_mod.check_image_generation_requirements = lambda: False
    fake_mod._active_image_capabilities = lambda: {}
    fake_mod._dispatch_to_plugin_provider = lambda *a, **k: None
    fake_mod.check_fal_api_key = lambda: False
    fake_mod.image_generate_tool = lambda **k: json.dumps(
        {"success": False, "error": "no backend"})
    fake_pkg.image_generation_tool = fake_mod
    monkeypatch.setitem(sys.modules, "tools", fake_pkg)
    monkeypatch.setitem(sys.modules, "tools.image_generation_tool", fake_mod)

    prov = _FakeGrokProvider()
    monkeypatch.setattr(imagegen, "_probe_unconfigured_provider",
                        lambda: prov)

    st = imagegen.hermes_status()
    assert st == {"available": True, "provider": "xAI (Grok)",
                  "model": "Grok Imagine Image", "canEdit": True}
    assert imagegen.get_backend() == "hermes"

    url = imagegen.hermes_generate("ad please", source_url="data:x",
                                   ref_urls=["https://s.png"])
    assert url == "/opt/data/cache/images/g.png"
    assert prov.last == {"prompt": "ad please", "image_url": "data:x",
                         "refs": ["https://s.png"]}


def test_import_result_serves_local_plugin_output(home, tmp_path):
    # remote URLs pass through untouched
    pub, spell = imagegen.import_result("https://fal/x.png")
    assert pub == spell == "https://fal/x.png"
    # local files (xAI / gpt-image save to the hermes cache) get copied
    # into the asset store and served from the plugin API
    src = tmp_path / "grok_out.png"
    src.write_bytes(b"\x89PNG-fake" * 8)
    pub, spell = imagegen.import_result(str(src))
    assert pub.startswith("/api/plugins/shorts-lab/asset/")
    assert spell.startswith("data:image/png;base64,")
    with pytest.raises(RuntimeError):
        imagegen.import_result(str(tmp_path / "gone.png"))


# ---------------------------------------------------------------------------
# surge.sh ad-pack publishing
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, status=200, payload=None, content=b"", headers=None):
        self.status_code = status
        self._payload = payload
        self.content = content
        self.text = ""
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_surge_page_has_variants_and_copy_buttons(home):
    creations = [{"id": 7, "title": "Bootcamp hero",
                  "source": {"postCopy": [
                      {"hook": "H1 🚨", "content": "Body with ✅ bullet",
                       "cta": "Tap now"},
                      {"hook": "H2", "content": "B2", "cta": "C2"},
                      {"hook": "H3", "content": "B3", "cta": "C3"}],
                      "copyTakes": ["Take one", "Take two"]}}]
    page = surge.build_page(creations, {7: "ad-7.png"})
    assert 'src="ad-7.png"' in page
    assert page.count("Variant ") == 3
    assert "Body with ✅ bullet" in page
    assert page.count("⧉ copy") >= 5          # hook/content/cta + takes
    assert "Copy whole variant" in page
    assert "showTab(7,1)" in page
    # html injection from copy text stays escaped
    creations[0]["source"]["postCopy"][0]["hook"] = "<script>alert(1)</script>"
    page = surge.build_page(creations, {7: "ad-7.png"})
    assert "<script>alert(1)" not in page


def test_surge_publish_tars_files_and_records(home, monkeypatch):
    import io, tarfile
    monkeypatch.setenv("SURGE_TOKEN", "tok123")
    aid = kie.save_asset("hero.png", b"\x89PNG-fake" * 5)
    cid = store.create_creation(
        "image-ad", "Hero ad", "brief", "content", status="ready",
        source={"postCopy": [{"hook": "H", "content": "C", "cta": "T"}],
                "copyTakes": ["take"]})
    store.update_creation(cid, status="ready",
                          result_url=f"/api/plugins/shorts-lab/asset/{aid}")

    sent = {}

    def fake_put(url, data=None, auth=None, headers=None, timeout=None):
        sent["url"] = url
        sent["auth"] = auth
        sent["headers"] = headers
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            sent["names"] = sorted(m.name for m in tar.getmembers())
        resp = _FakeResp(200)
        resp.text = ('{"type":"progress","written":10}\n'
                     '{"type":"info","domain":"my-pack.surge.sh"}\n')
        return resp

    monkeypatch.setattr(surge.requests, "put", fake_put)
    entry = surge.publish([cid], domain="my-pack")
    assert entry["url"] == "https://my-pack.surge.sh"
    assert sent["auth"] == ("token", "tok123")   # surge's literal username
    assert sent["url"].endswith("/my-pack.surge.sh")
    assert sent["headers"]["Content-Type"] == "application/gzip"
    assert sent["headers"]["file-count"] == "2"
    assert sent["names"] == [f"my-pack/ad-{cid}.png", "my-pack/index.html"]
    assert (store.kv_get("surgePages") or [])[0]["domain"] == "my-pack.surge.sh"

    with pytest.raises(RuntimeError, match="no ready ads"):
        surge.publish([99999])


def test_surge_publish_requires_info_event(home, monkeypatch):
    monkeypatch.setenv("SURGE_TOKEN", "tok123")
    aid = kie.save_asset("h2.png", b"\x89PNG" * 9)
    cid = store.create_creation("image-ad", "Ad2", "b", "c", status="ready",
                                source={})
    store.update_creation(cid, status="ready",
                          result_url=f"/api/plugins/shorts-lab/asset/{aid}")

    def fake_put(url, data=None, auth=None, headers=None, timeout=None):
        resp = _FakeResp(200)
        resp.text = '{"type":"error","message":"quota exceeded"}\n'
        return resp

    monkeypatch.setattr(surge.requests, "put", fake_put)
    with pytest.raises(RuntimeError, match="quota exceeded"):
        surge.publish([cid])


def test_surge_login_mints_token(home, monkeypatch):
    """email+password -> POST /token (surge's own login; new emails create
    the account). Only the minted token survives — never the password."""
    sent = {}

    def fake_post(url, auth=None, json=None, timeout=None):
        sent["url"] = url
        sent["auth"] = auth
        sent["body"] = json
        return _FakeResp(201, payload={"token": "minted-tok"})

    monkeypatch.setattr(surge.requests, "post", fake_post)
    out = surge.login("mentee@example.com", "hunter2")
    assert out == {"ok": True, "token": "minted-tok"}
    assert sent["url"].endswith("/token")
    assert sent["auth"] == ("mentee@example.com", "hunter2")
    assert "msg" in sent["body"]

    monkeypatch.setattr(surge.requests, "post",
                        lambda url, auth=None, json=None, timeout=None:
                        _FakeResp(401))
    out = surge.login("mentee@example.com", "wrong")
    assert out["ok"] is False and "wrong password" in out["error"]
    assert surge.login("", "x")["ok"] is False
    assert surge.login("a@b.c", "")["ok"] is False


def test_surge_list_and_validate(home, monkeypatch):
    monkeypatch.setenv("SURGE_TOKEN", "tok")

    monkeypatch.setattr(surge.requests, "get",
                        lambda url, auth=None, timeout=None: _FakeResp(
                            200, payload=[{"domain": "pack1.surge.sh",
                                           "timeAgo": "2 days ago"},
                                          {"domain": "pack2.surge.sh"}]))
    pages = surge.list_pages()
    assert [p["url"] for p in pages] == ["https://pack1.surge.sh",
                                        "https://pack2.surge.sh"]
    assert surge.validate("tok")["ok"] is True

    monkeypatch.setattr(surge.requests, "get",
                        lambda url, auth=None, timeout=None: _FakeResp(401))
    assert surge.validate("bad")["ok"] is False
