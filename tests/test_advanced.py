"""Advanced-studio tests — references library, KIE model catalog + video /
veo / gpt4o engines, recipes, capability gating, Meta paused publishing."""
from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

PKG = "shorts_lab_test_pkg"          # shared with test_shorts_lab
ROOT = Path(__file__).resolve().parent.parent

if PKG not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        PKG, str(ROOT / "__init__.py"),
        submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[PKG] = mod
    spec.loader.exec_module(mod)

store = importlib.import_module(f"{PKG}.store")
kie = importlib.import_module(f"{PKG}.kie")
references = importlib.import_module(f"{PKG}.references")
recipes = importlib.import_module(f"{PKG}.recipes")
analysis = importlib.import_module(f"{PKG}.analysis")
meta_publish = importlib.import_module(f"{PKG}.meta_publish")
kiedocs = importlib.import_module(f"{PKG}.kieref.loader")


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    for var in ("KIE_API_KEY", "META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID",
                "META_PAGE_ID"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


class _Resp:
    def __init__(self, status=200, payload=None, content=b""):
        self.status_code = status
        self._payload = payload or {}
        self.content = content
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


# ---------------------------------------------------------------------------
# kieref corpus
# ---------------------------------------------------------------------------

def test_corpus_complete_and_guides_load():
    for rid, files in kiedocs.GUIDES.items():
        for f in files:
            assert (kiedocs.ROOT / f).exists(), f"{rid}: missing {f}"
    txt = kiedocs.guide_text("seedance-ugc")
    assert "seedance" in txt.lower() and len(txt) > 2000
    assert kiedocs.guide_text("nope") == ""


# ---------------------------------------------------------------------------
# references library
# ---------------------------------------------------------------------------

def test_reference_save_list_delete_and_traversal_guard(home):
    rel = references.save("products", "hero shot.png", b"\x89PNG" * 50)
    assert rel == "products/hero shot.png"
    tree = references.tree()
    assert tree["products"][0]["name"] == "hero shot.png"

    rel2 = references.save("influencers/emma-test", "01-hero.jpg",
                           b"\xff\xd8\xff" + b"x" * 40)
    assert references.tree()["influencers"][0]["group"] == "emma-test"
    references.delete(rel2)
    assert references.tree()["influencers"] == []

    for bad in ("../etc/passwd", "products/../../x.jpg", "nope/x.jpg", ""):
        with pytest.raises(ValueError):
            references.path_for(bad)
    with pytest.raises(RuntimeError):
        references.save("products", "notes.txt", b"x")


def test_reference_upscales_small_images(home):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), "red").save(buf, format="PNG")
    rel = references.save("products", "tiny.png", buf.getvalue())
    saved = references.path_for(rel).read_bytes()
    img = Image.open(io.BytesIO(saved))
    assert max(img.size) == 1080          # Lanczos upscale to the floor
    assert rel.endswith(".jpg")           # re-encoded RGB JPEG


def test_starter_pack_import_maps_repo_paths(home, monkeypatch):
    fetched = []

    def fake_get(url):
        fetched.append(url)
        return _Resp(200, content=b"\xff\xd8\xffimg")

    out = references.import_starter_pack(http_get=fake_get)
    manifest = references.starter_manifest()
    assert out["imported"] == len(manifest)
    assert out["errors"] == []
    assert all(u.startswith("https://raw.githubusercontent.com/"
                            "krusemediallc/") for u in fetched)
    # hero angle of every influencer present + aesthetics + examples
    tree = references.tree()
    assert len([r for r in tree["influencers"]
                if r["name"] == "01-hero-front.jpg"]) == 13
    assert len(tree["aesthetics"]) == 5
    assert len(tree["examples"]) == 5
    # second run skips everything
    again = references.import_starter_pack(http_get=fake_get)
    assert again["imported"] == 0 and again["skipped"] == len(manifest)


# ---------------------------------------------------------------------------
# KIE engine
# ---------------------------------------------------------------------------

def test_model_catalog_capabilities():
    assert kie.model_info("bytedance/seedance-2")["audio"] is True
    assert kie.model_info("kling-3")["audio"] is False
    assert kie.model_info("gpt4o-image")["family"] == "gpt4o"
    assert kie.model_info("veo3_fast")["family"] == "veo"
    with pytest.raises(RuntimeError):
        kie.model_info("dall-e")
    videos = [m for m, v in kie.MODELS.items() if v["type"] == "video"]
    assert len(videos) >= 10


def test_submit_video_jobs_family(home, monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "k")
    sent = {}

    def fake_post(url, body, timeout=60):
        sent["url"] = url
        sent["body"] = body
        return {"code": 200, "data": {"taskId": "t1"}}

    monkeypatch.setattr(kie, "_post_json", fake_post)
    out = kie.submit_video("bytedance/seedance-2", "a UGC ad",
                           aspect_ratio="9:16", duration=12,
                           image_urls=["https://h/x.jpg"])
    assert out == {"taskId": "t1", "family": "jobs"}
    assert sent["url"].endswith("/api/v1/jobs/createTask")
    assert sent["body"]["model"] == "bytedance/seedance-2"
    assert sent["body"]["input"]["image_urls"] == ["https://h/x.jpg"]
    assert sent["body"]["input"]["duration"] == 12

    # sora rejects i2v refs on the text-only model
    with pytest.raises(RuntimeError, match="text-to-video only"):
        kie.submit_video("sora-2-text-to-video", "x",
                         image_urls=["https://h/x.jpg"])
    # duration snaps to the model's enum
    kie.submit_video("sora-2-text-to-video", "x", duration=13)
    assert sent["body"]["input"]["duration"] == 12


def test_submit_video_veo_rules(home, monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "k")
    sent = {}

    def fake_post(url, body, timeout=60):
        sent["url"] = url
        sent["body"] = body
        return {"code": 200, "data": {"taskId": "v1"}}

    monkeypatch.setattr(kie, "_post_json", fake_post)
    out = kie.submit_video("veo3_fast", "animate this",
                           image_urls=["https://h/still.jpg"])
    assert out["family"] == "veo"
    assert sent["url"].endswith("/api/v1/veo/generate")
    assert sent["body"]["generationType"] == "REFERENCE_2_VIDEO"
    assert sent["body"]["imageUrls"] == ["https://h/still.jpg"]

    # REFERENCE_2_VIDEO is veo3_fast-only (kit rule)
    with pytest.raises(RuntimeError, match="veo3_fast"):
        kie.submit_video("veo3", "x", image_urls=["https://h/a.jpg"],
                         veo_mode="REFERENCE_2_VIDEO")
    # first+last needs exactly two
    with pytest.raises(RuntimeError, match="exactly 2"):
        kie.submit_video("veo3", "x", image_urls=["https://h/a.jpg"],
                         veo_mode="FIRST_AND_LAST_FRAMES_2_VIDEO")
    # two refs auto-select first+last mode
    kie.submit_video("veo3", "x",
                     image_urls=["https://h/a.jpg", "https://h/b.jpg"])
    assert sent["body"]["generationType"] == "FIRST_AND_LAST_FRAMES_2_VIDEO"


def test_check_any_families(home, monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "k")

    def veo_resp(url, timeout=30):
        return {"code": 200, "data": {"successFlag": 1, "response": {
            "resultUrls": ["https://cdn/v.mp4"], "hasAudioList": [True]}}}

    monkeypatch.setattr(kie, "_get_json", veo_resp)
    out = kie.check_any("t", "veo")
    assert out["state"] == "success" and out["url"].endswith("v.mp4")

    monkeypatch.setattr(kie, "_get_json",
                        lambda url, timeout=30: {"code": 200, "data": {
                            "successFlag": 2, "errorMessage": "moderated"}})
    assert kie.check_any("t", "veo")["state"] == "fail"

    monkeypatch.setattr(kie, "_get_json",
                        lambda url, timeout=30: {"code": 200, "data": {
                            "successFlag": 1, "response": {
                                "resultUrls": ["https://cdn/i.png"]}}})
    assert kie.check_any("t", "gpt4o")["state"] == "success"
    with pytest.raises(RuntimeError):
        kie.check_any("t", "nope")


def test_gpt4o_submit_shape(home, monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "k")
    sent = {}

    def fake_post(url, body, timeout=60):
        sent["url"] = url
        sent["body"] = body
        return {"code": 200, "data": {"taskId": "g1"}}

    monkeypatch.setattr(kie, "_post_json", fake_post)
    out = kie.submit_gpt4o_image("storyboard beat", size="3:2",
                                 files_url=["https://h/prev.jpg"] * 7)
    assert out["family"] == "gpt4o"
    assert sent["url"].endswith("/api/v1/gpt4o-image/generate")
    assert len(sent["body"]["filesUrl"]) == 5       # capped at 5
    with pytest.raises(RuntimeError, match="sizes"):
        kie.submit_gpt4o_image("x", size="4:5")


def test_generation_log_written(home, monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "k")
    monkeypatch.setattr(kie, "_post_json",
                        lambda url, body, timeout=60:
                        {"code": 200, "data": {"taskId": "t9"}})
    kie.submit_video("kling-3", "b-roll", duration=5)
    rows = kie.recent_log()
    assert rows and rows[0]["model"] == "kling-3"
    assert "prompt" not in rows[0]           # kit rule: never log prompts


# ---------------------------------------------------------------------------
# recipes
# ---------------------------------------------------------------------------

class _FakeRes:
    def __init__(self, parsed):
        self.parsed = parsed


def _fake_llm(parsed):
    class L:
        def complete_structured(self, **kw):
            _fake_llm.last = kw
            return _FakeRes(parsed)
    return L()


def test_build_prompts_grounds_in_guide(home, monkeypatch):
    monkeypatch.setattr(analysis, "_llm", lambda: _fake_llm(
        {"title": "UGC", "prompts": ["p1", "p2"], "notes": "n"}))
    out = recipes.build_prompts("seedance-ugc", "sell my bootcamp", n=2)
    assert out["prompts"] == ["p1", "p2"]
    sent = _fake_llm.last["input"][0]["text"]
    assert "GUIDE (authoritative)" in sent
    assert "seedance" in sent.lower()


def test_start_video_needs_video_recipe_and_fires_n(home, monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "k")
    monkeypatch.setattr(analysis, "_llm", lambda: _fake_llm(
        {"title": "T", "prompts": ["a", "b"], "notes": ""}))
    calls = []
    monkeypatch.setattr(kie, "submit_video",
                        lambda *a, **k: calls.append((a, k)) or
                        {"taskId": f"t{len(calls)}", "family": "jobs"})
    cids = recipes.start_video("seedance-ugc", "brief", variants=2)
    assert len(cids) == 2 and len(calls) == 2
    c = store.get_creation(cids[0])
    assert c["kind"] == "video-ad"
    assert (c["source"] or {})["family"] == "jobs"
    with pytest.raises(RuntimeError):
        recipes.start_video("ugc-selfie", "brief")


def test_sora_duration_auto_from_script(home, monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "k")
    monkeypatch.setattr(analysis, "_llm", lambda: _fake_llm(
        {"title": "T", "prompts": ["a"], "notes": ""}))
    seen = {}

    def fake_submit(model, prompt, aspect_ratio="9:16", duration=None,
                    image_urls=None, veo_mode=""):
        seen["duration"] = duration
        return {"taskId": "t", "family": "jobs"}

    monkeypatch.setattr(kie, "submit_video", fake_submit)
    words = " ".join(["word"] * 30)          # 30 words / 2.5 = 12s
    recipes.start_video("sora-video", words,
                        model="sora-2-text-to-video")
    assert seen["duration"] == 12


def test_analyze_video_stores_template(home, monkeypatch):
    monkeypatch.setattr(analysis, "_llm", lambda: _fake_llm(
        {"name": "Kitchen UGC", "template": "A {person} in a kitchen…",
         "parameters": ["person", "product"], "notes": "n"}))
    tpl = recipes.analyze_video("https://x/v.mp4", "woman reviews gummies")
    assert tpl["name"] == "Kitchen UGC"
    saved = store.kv_get("videoTemplates")
    assert saved[0]["parameters"] == ["person", "product"]


def test_character_sheet_pipeline_sequences_angles(home, monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "k")
    monkeypatch.setattr(analysis, "_llm", lambda: _fake_llm(
        {"title": "Sheet", "prompts": ["hero prompt"], "notes": ""}))
    submits = []
    monkeypatch.setattr(kie, "submit_jobs_image",
                        lambda model, prompt, aspect_ratio="2:3",
                        image_input=None:
                        submits.append({"refs": list(image_input or [])}) or
                        {"taskId": f"t{len(submits)}", "family": "jobs"})
    monkeypatch.setattr(recipes, "_poll_until",
                        lambda tid, fam, timeout_s=900:
                        f"https://cdn/{tid}.jpg")
    import urllib.request as ur
    monkeypatch.setattr(ur, "urlopen",
                        lambda url, timeout=120: __import__("io").BytesIO(
                            b"\xff\xd8\xffimg"))
    cid = recipes.start_character_sheet("Emma Test", "22yo, freckles")
    # worker is a thread — wait for it
    import time as _t
    for _ in range(100):
        c = store.get_creation(cid)
        if c["status"] in ("ready", "failed"):
            break
        _t.sleep(0.05)
    assert c["status"] == "ready", c.get("error")
    assert len(submits) == 10
    assert submits[0]["refs"] == []                    # hero: no refs
    assert submits[1]["refs"] == ["https://cdn/t1.jpg"]  # angles: hero ref
    tree = references.tree()
    assert len([r for r in tree["influencers"]
                if r["group"] == "emma-test"]) == 10


def test_storyboard_pipeline_chains_prior_frame(home, monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "k")
    monkeypatch.setattr(analysis, "_llm", lambda: _fake_llm(
        {"title": "Pixar", "prompts": ["b1", "b2", "b3"], "notes": ""}))
    subs = []
    monkeypatch.setattr(kie, "submit_gpt4o_image",
                        lambda prompt, size="3:2", files_url=None:
                        subs.append(list(files_url or [])) or
                        {"taskId": f"s{len(subs)}", "family": "gpt4o"})
    monkeypatch.setattr(recipes, "_poll_until",
                        lambda tid, fam, timeout_s=900:
                        f"https://cdn/{tid}.png")
    cid = recipes.start_storyboard("pixar", "mascot ad", beats=3)
    import time as _t
    for _ in range(100):
        c = store.get_creation(cid)
        if c["status"] in ("ready", "failed"):
            break
        _t.sleep(0.05)
    assert c["status"] == "ready", c.get("error")
    assert subs[0] == []                       # beat 1: fresh
    assert subs[1] == ["https://cdn/s1.png"]   # beat 2 refs beat 1
    assert subs[2] == ["https://cdn/s2.png"]   # beat 3 refs beat 2

    # stage 2: animate each finished beat
    vids = []
    monkeypatch.setattr(kie, "submit_video",
                        lambda model, prompt, aspect_ratio="16:9",
                        duration=None, image_urls=None, veo_mode="":
                        vids.append(list(image_urls or [])) or
                        {"taskId": f"v{len(vids)}", "family": "jobs"})
    made = recipes.animate_storyboard(cid)
    assert made == 3
    assert vids[0] == ["https://cdn/s1.png"]


# ---------------------------------------------------------------------------
# Meta paused publishing (kit deploy path)
# ---------------------------------------------------------------------------

def test_meta_publish_always_paused_and_call_order(home, monkeypatch):
    monkeypatch.setenv("META_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "12345")   # act_ added
    monkeypatch.setenv("META_PAGE_ID", "777")
    calls = []

    def fake_post(url, data=None, files=None, timeout=None):
        calls.append({"url": url, "data": dict(data or {})})
        if url.endswith("/adimages"):
            return _Resp(200, {"images": {"x": {"hash": "H1"}}})
        if url.endswith("/ads"):
            return _Resp(200, {"id": "AD9"})
        return _Resp(400, {"error": {"message": "unexpected"}})

    monkeypatch.setattr(meta_publish.requests, "post", fake_post)
    creation = {"id": 5, "title": "Bootcamp hero", "brief": "b",
                "source": {"postCopy": [
                    {"hook": "H", "content": "C", "cta": "T"}]}}
    entry = meta_publish.publish_creation(
        creation, "ADSET1", "https://example.com", cta="SHOP_NOW",
        image_bytes=b"\xff\xd8\xffimg")
    assert entry["adId"] == "AD9" and entry["status"] == "PAUSED"

    assert calls[0]["url"].endswith("/act_12345/adimages")
    ad_call = calls[1]
    assert ad_call["url"].endswith("/act_12345/ads")
    assert ad_call["data"]["status"] == "PAUSED"       # structural
    creative = json.loads(ad_call["data"]["creative"])
    spec = creative["object_story_spec"]
    assert spec["page_id"] == "777"
    assert spec["link_data"]["image_hash"] == "H1"
    assert spec["link_data"]["call_to_action"]["type"] == "SHOP_NOW"
    assert creative["asset_feed_spec"]["bodies"] == [{"text": "C"}]
    assert creative["asset_feed_spec"]["titles"] == [{"text": "H"}]
    assert creative["degrees_of_freedom_spec"][
        "degrees_of_freedom_type"] == "USER_ENROLLED"
    assert (store.kv_get("metaPublished") or [])[0]["adId"] == "AD9"


def test_meta_transient_error_retries_then_fails(home, monkeypatch):
    monkeypatch.setenv("META_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "act_9")
    monkeypatch.setenv("META_PAGE_ID", "7")
    monkeypatch.setattr(meta_publish.time, "sleep", lambda s: None)
    n = {"count": 0}

    def flaky(url, data=None, files=None, timeout=None):
        n["count"] += 1
        return _Resp(200, {"error": {"message": "busy",
                                     "is_transient": True, "code": 2}})

    monkeypatch.setattr(meta_publish.requests, "post", flaky)
    with pytest.raises(RuntimeError, match="busy"):
        meta_publish.create_ad("A", "name", {"x": 1})
    assert n["count"] == 4                     # kit's 4-attempt backoff

    assert meta_publish.is_connected() is True
    monkeypatch.delenv("META_PAGE_ID")
    assert meta_publish.is_connected() is False


def test_meta_validate_account(home, monkeypatch):
    monkeypatch.setattr(meta_publish.requests, "get",
                        lambda url, params=None, timeout=None:
                        _Resp(200, {"name": "AICVC", "account_status": 1}))
    out = meta_publish.validate_account("tok", "123")
    assert out == {"ok": True, "name": "AICVC"}
    monkeypatch.setattr(meta_publish.requests, "get",
                        lambda url, params=None, timeout=None:
                        _Resp(200, {"error": {"message": "bad token"}}))
    assert meta_publish.validate_account("tok", "123")["ok"] is False
