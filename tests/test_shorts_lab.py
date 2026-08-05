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

    # edit mode: source first, style refs follow, edit model
    tid = kie.submit_image("make it pop", source_url="https://h/src.jpg",
                           ref_urls=["https://h/style.jpg"])
    assert tid == "t-123"
    assert sent["body"]["model"] == "nano-banana-edit"
    assert sent["body"]["input"]["image_input"] == [
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
