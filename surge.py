"""surge.sh publishing — hand finished ad packs to the editor.

Talks to surge's own REST endpoints — protocol read from the surge /
surge-sdk / surge-stream npm packages: basic auth is username "token" +
the account token, `GET /list` lists published pages, and publish is
`PUT /:domain` with a gzipped tarball whose entries are prefixed with a
directory name; the NDJSON response only counts as success when a
`type:"info"` event arrives. No node runtime needed in the container. The published page is a single self-contained
index.html plus the ad images: each selected creation renders its image
beside the three post-copy variants (hook / content / CTA blocks) with
one-click copy buttons for the editor.
"""
from __future__ import annotations

import html
import io
import json
import os
import re
import tarfile
import time

import requests

try:
    from . import store
except ImportError:  # loaded outside package context
    import store  # type: ignore

BASE_URL = os.environ.get("SURGE_BASE_URL", "https://surge.surge.sh")
_TIMEOUT = 60


_CLI_VERSION = "0.41.2"     # the CLI release whose protocol this mirrors


def token() -> str:
    return (os.environ.get("SURGE_TOKEN") or "").strip()


def _auth(tok: str = "") -> tuple:
    # surge basic auth is the literal username "token" + the account token
    return ("token", tok or token())


def is_connected() -> bool:
    return bool(token())


def login(email: str, password: str) -> dict:
    """Mint an account token from email + password — surge's own login
    call (POST /token, basic auth email:password). A NEW email creates
    the account on the spot, exactly like `surge login`. The password is
    used for this one request and never stored or logged."""
    email = (email or "").strip()
    if not email or "@" not in email:
        return {"ok": False, "error": "a valid email is required"}
    if not (password or ""):
        return {"ok": False, "error": "a password is required"}
    try:
        r = requests.post(f"{BASE_URL}/token", auth=(email, password),
                          json={"msg": "login from hermes shorts-lab"},
                          timeout=_TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"surge unreachable: {exc}"}
    if r.status_code == 401:
        return {"ok": False,
                "error": "wrong password for an existing surge account"}
    if r.status_code >= 300:
        return {"ok": False,
                "error": f"surge login failed (HTTP {r.status_code})"}
    try:
        tok = (r.json() or {}).get("token") or ""
    except ValueError:
        tok = ""
    if not tok:
        return {"ok": False, "error": "surge returned no token"}
    return {"ok": True, "token": tok}


def default_email() -> str:
    """Best-known email to prefill the connect form — the stored surge
    login first, then common instance-identity env vars, then git."""
    for var in ("SURGE_LOGIN", "MENTEE_EMAIL", "HERMES_USER_EMAIL", "EMAIL"):
        v = (os.environ.get(var) or "").strip()
        if "@" in v:
            return v
    try:
        import subprocess
        v = subprocess.run(["git", "config", "user.email"],
                           capture_output=True, text=True,
                           timeout=5).stdout.strip()
        if "@" in v:
            return v
    except Exception:  # noqa: BLE001
        pass
    return ""


def validate(tok: str) -> dict:
    """Cheapest possible auth check: the account's project list."""
    try:
        r = requests.get(f"{BASE_URL}/list", auth=_auth(tok),
                         timeout=_TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"surge unreachable: {exc}"}
    if r.status_code == 200:
        return {"ok": True}
    return {"ok": False,
            "error": f"surge rejected the token (HTTP {r.status_code})"}


def list_pages() -> list:
    """Published pages on the account, newest first."""
    if not token():
        raise RuntimeError("surge.sh is not connected")
    r = requests.get(f"{BASE_URL}/list", auth=_auth(),
                     timeout=_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"surge list failed (HTTP {r.status_code})")
    pages = []
    for row in (r.json() or []):
        domain = row.get("domain") or ""
        if not domain:
            continue
        pages.append({"domain": domain,
                      "url": f"https://{domain}",
                      "timeAgo": row.get("timeAgo") or "",
                      "rev": row.get("rev")})
    return pages


# ---------------------------------------------------------------------------
# Page build
# ---------------------------------------------------------------------------

def _fetch_image(result_url: str) -> tuple:
    """(bytes, extension) for a creation's image — plugin-served assets are
    read straight from disk, remote URLs (xai CDN, FAL, KIE) are fetched."""
    m = re.match(r"^/api/plugins/shorts-lab/asset/([A-Za-z0-9_.-]+)$",
                 result_url or "")
    if m:
        path = store.assets_dir() / m.group(1)
        if not path.exists():
            raise RuntimeError(f"asset {m.group(1)} missing")
        ext = path.suffix.lstrip(".") or "png"
        return path.read_bytes(), ext
    r = requests.get(result_url, timeout=_TIMEOUT)
    r.raise_for_status()
    payload = r.content
    if len(payload) > 20 * 1024 * 1024:
        raise RuntimeError("image too large to publish")
    ctype = (r.headers.get("content-type") or "").lower()
    ext = ("jpg" if "jpeg" in ctype else
           "webp" if "webp" in ctype else "png")
    return payload, ext


_PAGE_CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: #0d0d17; color: #e8e8f0;
       font: 15px/1.55 -apple-system, "Segoe UI", Roboto, sans-serif; }
.wrap { max-width: 1080px; margin: 0 auto; padding: 28px 20px 60px; }
.eyebrow { letter-spacing: 3px; font-size: 12px; color: #14b8a6;
           font-weight: 800; }
h1 { margin: 4px 0 26px; font-size: 26px; }
.ad { display: flex; gap: 22px; flex-wrap: wrap; align-items: flex-start;
      background: #16162a; border: 1px solid #2b2b44; border-radius: 14px;
      padding: 20px; margin-bottom: 26px; }
.ad img { max-width: 440px; width: 100%; border-radius: 10px;
          flex: 0 1 440px; }
.side { flex: 1 1 300px; min-width: 280px; }
.ad h2 { margin: 0 0 12px; font-size: 17px; }
.tabs { display: flex; gap: 6px; margin-bottom: 12px; }
.tab { border: 1px solid #2b2b44; background: transparent; color: #e8e8f0;
       border-radius: 999px; padding: 5px 14px; font-size: 12.5px;
       font-weight: 700; cursor: pointer; }
.tab.on { color: #14b8a6; border-color: #14b8a680; background: #14b8a61a; }
.block { display: flex; gap: 10px; align-items: flex-start;
         background: #13131f; border: 1px solid #2b2b44; border-radius: 8px;
         padding: 10px 12px; margin-bottom: 8px; font-size: 13.5px;
         white-space: pre-wrap; }
.lbl { flex-shrink: 0; color: #9aa0b4; font-size: 11.5px; font-weight: 800;
       text-transform: uppercase; letter-spacing: 1px; padding-top: 2px;
       width: 64px; }
.txt { flex: 1; }
.copy { border: 1px solid #2b2b44; background: transparent; color: #e8e8f0;
        border-radius: 6px; padding: 2px 9px; font-size: 11.5px;
        cursor: pointer; flex-shrink: 0; }
.copy:hover { border-color: #14b8a6; color: #14b8a6; }
.copyall { margin: 2px 0 14px; }
.takes { margin-top: 16px; }
.takes h3 { margin: 0 0 8px; font-size: 13px; color: #9aa0b4; }
.foot { color: #9aa0b4; font-size: 12px; margin-top: 30px; }
"""

_PAGE_JS = """
function cp(btn, text) {
  var done = function () {
    var t = btn.textContent; btn.textContent = "copied!";
    setTimeout(function () { btn.textContent = t; }, 1200);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done, function () { fallback(); });
  } else { fallback(); }
  function fallback() {
    var ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); done(); } catch (e) {}
    document.body.removeChild(ta);
  }
}
function showTab(adId, idx) {
  var panes = document.querySelectorAll('[data-pane="' + adId + '"]');
  panes.forEach(function (p) {
    p.style.display = p.getAttribute("data-idx") == idx ? "" : "none";
  });
  document.querySelectorAll('[data-tab="' + adId + '"]').forEach(function (t) {
    t.classList.toggle("on", t.getAttribute("data-idx") == idx);
  });
}
"""


def _esc(t: str) -> str:
    return html.escape(str(t or ""), quote=True)


def _js_str(t: str) -> str:
    return json.dumps(str(t or ""))


def build_page(creations: list, images: dict) -> str:
    """creations: store rows; images: creation id -> image filename."""
    sections = []
    for c in creations:
        cid = c["id"]
        src = c.get("source") or {}
        posts = src.get("postCopy") or []
        takes = src.get("copyTakes") or []
        tabs, panes = [], []
        for j, p in enumerate(posts[:3]):
            full = "\n\n".join(x for x in
                               [p.get("hook"), p.get("content"),
                                p.get("cta")] if x)
            tabs.append(
                f'<button class="tab{" on" if j == 0 else ""}" '
                f'data-tab="{cid}" data-idx="{j}" '
                f'onclick="showTab({cid},{j})">Variant {j + 1}</button>')
            blocks = []
            for lbl, key in (("Hook", "hook"), ("Content", "content"),
                             ("CTA", "cta")):
                val = p.get(key) or ""
                if not val:
                    continue
                blocks.append(
                    f'<div class="block"><span class="lbl">{lbl}</span>'
                    f'<span class="txt">{_esc(val)}</span>'
                    f'<button class="copy" onclick="cp(this,{_esc_attr_js(val)})">'
                    f'⧉ copy</button></div>')
            hide = "" if j == 0 else ' style="display:none"'
            panes.append(
                f'<div data-pane="{cid}" data-idx="{j}"{hide}>'
                f'<button class="copy copyall" '
                f'onclick="cp(this,{_esc_attr_js(full)})">'
                f'⧉ Copy whole variant</button>' + "".join(blocks) + '</div>')
        takes_html = ""
        if takes:
            rows = "".join(
                f'<div class="block"><span class="lbl">{i + 1}.</span>'
                f'<span class="txt">{_esc(t)}</span>'
                f'<button class="copy" onclick="cp(this,{_esc_attr_js(t)})">'
                f'⧉ copy</button></div>' for i, t in enumerate(takes))
            takes_html = (f'<div class="takes"><h3>In-image headline takes'
                          f'</h3>{rows}</div>')
        sections.append(f'''
<section class="ad">
  <img src="{images[cid]}" alt="{_esc(c["title"])}">
  <div class="side">
    <h2>{_esc(c["title"])}</h2>
    <div class="tabs">{"".join(tabs)}</div>
    {"".join(panes) or '<div class="block">No post copy on this ad.</div>'}
    {takes_html}
  </div>
</section>''')
    when = time.strftime("%B %d, %Y")
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Ad pack — {when}</title>
<style>{_PAGE_CSS}</style></head>
<body><div class="wrap">
<div class="eyebrow">AI CYBER VALUE CREATOR™</div>
<h1>Ad pack — {when}</h1>
{"".join(sections)}
<div class="foot">Each variant tab holds the post copy that runs WITH the
ad (hook, content, CTA) — use the copy buttons. The headline takes under it
are the short lines rendered inside the image.</div>
</div><script>{_PAGE_JS}</script></body></html>'''


def _esc_attr_js(val: str) -> str:
    """JS string literal safe inside an HTML onclick attribute."""
    return _esc(_js_str(val))


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

def _default_domain() -> str:
    return time.strftime("aicvc-ads-%Y%m%d-%H%M%S") + ".surge.sh"


def publish(creation_ids: list, domain: str = "") -> dict:
    if not token():
        raise RuntimeError("surge.sh is not connected — add your surge "
                           "token first")
    creations = []
    for cid in creation_ids:
        c = store.get_creation(int(cid))
        if c and c.get("result_url") and c.get("status") == "ready":
            creations.append(c)
    if not creations:
        raise RuntimeError("no ready ads selected")

    files: dict = {}
    images: dict = {}
    for c in creations:
        payload, ext = _fetch_image(c["result_url"])
        name = f"ad-{c['id']}.{ext}"
        files[name] = payload
        images[c["id"]] = name
    files["index.html"] = build_page(creations, images).encode()

    domain = (domain or "").strip() or _default_domain()
    if not domain.endswith(".surge.sh") and "." not in domain:
        domain += ".surge.sh"

    # tar entries ride under a directory prefix, exactly like the CLI's
    # tar.c({portable, mtime: epoch}, ["dirname/file", ...])
    prefix = re.sub(r"[^a-z0-9-]", "-", domain.split(".")[0]) or "adpack"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, payload in files.items():
            info = tarfile.TarInfo(name=f"{prefix}/{name}")
            info.size = len(payload)
            info.mtime = 0
            tar.addfile(info, io.BytesIO(payload))
    buf.seek(0)
    body = buf.getvalue()

    r = requests.put(
        f"{BASE_URL}/{domain}", data=body, auth=_auth(),
        headers={"Content-Type": "application/gzip",
                 "Accept": "application/x-ndjson",
                 "version": _CLI_VERSION,
                 "file-count": str(len(files)),
                 "project-size": str(len(body)),
                 "timestamp": str(int(time.time()))},
        timeout=300)
    if r.status_code >= 300:
        raise RuntimeError(
            f"surge publish failed (HTTP {r.status_code}): "
            f"{(r.text or '')[:200]}")
    # NDJSON stream: only a type:"info" event means the deploy landed
    ok = False
    err_msg = ""
    for line in (r.text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except ValueError:
            continue
        if evt.get("type") == "info":
            ok = True
        if evt.get("type") in ("error", "fail"):
            err_msg = str(evt.get("message") or evt)[:200]
    if not ok:
        raise RuntimeError("surge publish did not confirm: "
                           + (err_msg or "no info event in response"))

    entry = {"domain": domain, "url": f"https://{domain}",
             "at": time.time(), "ads": [c["id"] for c in creations]}
    pages = store.kv_get("surgePages") or []
    pages = [p for p in pages if p.get("domain") != domain]
    pages.insert(0, entry)
    store.kv_set("surgePages", pages[:50])
    return entry
