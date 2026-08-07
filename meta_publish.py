"""Publish creatives as PAUSED Meta ads — faithful port of the ad-builder
kit's meta-ad-builder deploy path (scripts/deploy-ad.py + lib/meta_api.py).

Every ad is created with status=PAUSED. Nothing spends until the user
reviews and launches it in Ads Manager — that rule is structural, not a
default: this module refuses any other status.

Credentials (Keys page / env):
  META_ACCESS_TOKEN    long-lived token with ads_management scope
  META_AD_ACCOUNT_ID   with or without the act_ prefix
  META_PAGE_ID         the Facebook Page the ad runs under
  META_API_VERSION     optional, default v23.0
"""
from __future__ import annotations

import base64
import json
import os
import re
import time

import requests

try:
    from . import store
except ImportError:  # loaded outside package context
    import store  # type: ignore

API_VERSION = os.environ.get("META_API_VERSION", "v23.0")
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

# straight from the kit's deploy-ad.py — Advantage+ enrollment matrix
CREATIVE_FEATURES_SPEC_BASE = {
    "advantage_plus_creative": {"enroll_status": "OPT_IN"},
    "creative_stickers": {"enroll_status": "OPT_IN"},
    "enhance_cta": {
        "enroll_status": "OPT_IN",
        "customizations": {"text_extraction": {"enroll_status": "OPT_IN"}},
    },
    "generate_cta": {"enroll_status": "OPT_IN"},
    "inline_comment": {"enroll_status": "OPT_IN"},
    "product_extensions": {
        "enroll_status": "OPT_OUT",
        "customizations": {"pe_carousel": {"enroll_status": "OPT_OUT"}},
    },
    "reveal_details_over_time": {"enroll_status": "OPT_IN"},
    "show_destination_blurbs": {"enroll_status": "OPT_IN"},
    "show_summary": {"enroll_status": "OPT_IN"},
    "site_extensions": {"enroll_status": "OPT_OUT"},
    "text_optimizations": {
        "enroll_status": "OPT_IN",
        "customizations": {"text_extraction": {"enroll_status": "OPT_IN"}},
    },
    "text_translation": {"enroll_status": "OPT_IN"},
}

_CTA_TYPES = {"LEARN_MORE", "SHOP_NOW", "SIGN_UP", "SUBSCRIBE",
              "GET_OFFER", "CONTACT_US", "DOWNLOAD", "APPLY_NOW",
              "BOOK_TRAVEL", "GET_QUOTE"}


def _token() -> str:
    t = (os.environ.get("META_ACCESS_TOKEN") or "").strip()
    if not t:
        raise RuntimeError("META_ACCESS_TOKEN not set — connect Meta Ads")
    return t


def account_id() -> str:
    acct = (os.environ.get("META_AD_ACCOUNT_ID") or "").strip()
    if not acct:
        raise RuntimeError("META_AD_ACCOUNT_ID not set — connect Meta Ads")
    return acct if acct.startswith("act_") else f"act_{acct}"


def page_id() -> str:
    p = (os.environ.get("META_PAGE_ID") or "").strip()
    if not p:
        raise RuntimeError("META_PAGE_ID not set — connect Meta Ads")
    return p


def is_connected() -> bool:
    return all((os.environ.get(v) or "").strip()
               for v in ("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID",
                         "META_PAGE_ID"))


def validate_account(token: str, acct: str) -> dict:
    """Cheapest sanity check: read the ad account's name with the token."""
    acct = acct if acct.startswith("act_") else f"act_{acct}"
    try:
        r = requests.get(f"{BASE_URL}/{acct}",
                         params={"access_token": token,
                                 "fields": "name,account_status"},
                         timeout=30)
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"Meta unreachable: {exc}"}
    if "error" in data:
        return {"ok": False,
                "error": str(data["error"].get("message"))[:200]}
    return {"ok": True, "name": data.get("name")}


def list_adsets() -> list:
    """Ad sets on the account, for the publish picker (newest first)."""
    r = requests.get(f"{BASE_URL}/{account_id()}/adsets",
                     params={"access_token": _token(),
                             "fields": "name,status,campaign{name}",
                             "limit": 50},
                     timeout=60)
    data = r.json()
    if "error" in data:
        raise RuntimeError(str(data["error"].get("message"))[:200])
    out = []
    for row in data.get("data") or []:
        out.append({"id": row.get("id"), "name": row.get("name"),
                    "status": row.get("status"),
                    "campaign": (row.get("campaign") or {}).get("name")})
    return out


def upload_image(payload: bytes, name: str) -> str:
    """Image bytes -> /adimages (base64) -> image hash (kit's uploader)."""
    r = requests.post(
        f"{BASE_URL}/{account_id()}/adimages",
        data={"access_token": _token(),
              "bytes": base64.b64encode(payload).decode(),
              "name": re.sub(r"[^A-Za-z0-9 _.-]", "", name)[:90] or "ad"},
        timeout=120)
    data = r.json()
    if "images" in data:
        return list(data["images"].values())[0].get("hash")
    err = (data.get("error") or {}).get("message") or str(data)[:200]
    raise RuntimeError(f"adimage upload failed: {err}")


def build_image_creative(image_hash: str, page: str, link: str, cta: str,
                         bodies: list, titles: list,
                         descriptions: list) -> dict:
    """The kit's image creative: object_story_spec + asset_feed_spec +
    degrees-of-freedom enrollment."""
    cta = cta if cta in _CTA_TYPES else "LEARN_MORE"
    spec = {
        "optimization_type": "DEGREES_OF_FREEDOM",
        "bodies": [{"text": b} for b in bodies if b][:5],
        "titles": [{"text": t} for t in titles if t][:5],
        "descriptions": [{"text": d} for d in descriptions if d][:5],
        "call_to_action_types": [cta],
        "link_urls": [{"website_url": link}],
    }
    return {
        "object_story_spec": {
            "page_id": page,
            "link_data": {
                "link": link,
                "image_hash": image_hash,
                "call_to_action": {"type": cta, "value": {"link": link}},
            },
        },
        "asset_feed_spec": spec,
        "degrees_of_freedom_spec": {
            "degrees_of_freedom_type": "USER_ENROLLED",
            "text_transformation_types": ["TEXT_LIQUIDITY"],
            "creative_features_spec": CREATIVE_FEATURES_SPEC_BASE,
        },
        "contextual_multi_ads": {"enroll_status": "OPT_IN"},
    }


def create_ad(adset_id: str, ad_name: str, creative: dict) -> str:
    """Create the ad — ALWAYS PAUSED, with the kit's transient-error
    retry/backoff. Returns the ad id."""
    payload = {
        "access_token": _token(),
        "adset_id": adset_id,
        "name": ad_name[:120],
        "status": "PAUSED",          # structural: never any other status
        "creative": json.dumps(creative),
    }
    last_err = "unknown"
    for attempt in range(1, 5):
        r = requests.post(f"{BASE_URL}/{account_id()}/ads", data=payload,
                          timeout=120)
        data = r.json()
        if "error" not in data:
            return data["id"]
        err = data["error"]
        last_err = str(err.get("message") or err)[:250]
        if err.get("is_transient") and attempt < 4:
            time.sleep(min(60, 5 * (2 ** (attempt - 1))))
            continue
        break
    raise RuntimeError(f"ad creation failed: {last_err}")


def publish_creation(creation: dict, adset_id: str, link: str,
                     cta: str = "LEARN_MORE",
                     image_bytes: bytes = None) -> dict:
    """One creation -> one PAUSED ad. Copy comes from the creation's
    post-copy variants (hooks -> titles, contents -> bodies, CTA lines ->
    descriptions), matching the kit's copy-file shape."""
    src = creation.get("source") or {}
    posts = src.get("postCopy") or []
    bodies = [p.get("content") for p in posts if p.get("content")] or \
        [creation.get("brief") or creation.get("title") or "See more."]
    titles = [p.get("hook") for p in posts if p.get("hook")] or \
        [creation.get("title") or "Our latest"]
    descriptions = [p.get("cta") for p in posts if p.get("cta")]

    image_hash = upload_image(image_bytes, creation.get("title") or "ad")
    creative = build_image_creative(
        image_hash, page_id(), link, cta, bodies, titles, descriptions)
    ad_id = create_ad(adset_id, creation.get("title") or "Shorts Lab ad",
                      creative)
    entry = {"adId": ad_id, "creationId": creation.get("id"),
             "adsetId": adset_id, "at": time.time(), "status": "PAUSED"}
    log = store.kv_get("metaPublished") or []
    log.insert(0, entry)
    store.kv_set("metaPublished", log[:50])
    return entry
