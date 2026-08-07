/**
 * Shorts Lab — Hermes Dashboard Plugin
 *
 * Attract-phase workbench, four tabs:
 *   1. Shorts Research — monitored competitors' recent YouTube Shorts
 *      (channel list SHARED with YouTube Insights — one source of truth),
 *      with a winning-pattern analysis: hooks, message, format, style.
 *   2. Shorts Content — derivative scripts from those winning patterns,
 *      viewable and downloadable.
 *   3. Ads Research — Meta Ad Library competitor search + monitoring,
 *      longest-running winners first.
 *   4. Ads Lab — convert your own assets into the style of a winning ad
 *      via KIE.ai (image-ad-clone method).
 *
 * Plain IIFE, no build step. window.__HERMES_PLUGIN_SDK__ for React.
 */
(function () {
  "use strict";

  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;

  // -------------------------------------------------------------------------
  // Ambient FX (standalone installs; yields when the acvc bundle is present)
  // -------------------------------------------------------------------------
  (function ambientBackground() {
    var ROUTES = { "/shortform": 1 };
    var canvas = null, tintEl = null, raf = 0, stars = null;
    var pointer = { x: 0, y: 0 }, eased = { x: 0, y: 0 };
    var theme = { r: 20, g: 184, b: 166 }, fore = { r: 230, g: 230, b: 240 };
    var lightTheme = false, moteBase = 255, dpr = 1;
    var probeCanvas = null;

    function parseColor(col, fallback) {
      if (!probeCanvas) { probeCanvas = document.createElement("canvas"); probeCanvas.width = probeCanvas.height = 1; }
      var x = probeCanvas.getContext("2d", { willReadFrequently: true });
      x.fillStyle = fallback; x.fillStyle = col;
      x.clearRect(0, 0, 1, 1); x.fillRect(0, 0, 1, 1);
      var d = x.getImageData(0, 0, 1, 1).data;
      return { r: d[0], g: d[1], b: d[2] };
    }
    function resolveVar(name, fallback) {
      var probe = document.createElement("span");
      probe.style.color = "var(" + name + ", " + fallback + ")";
      probe.style.display = "none";
      document.body.appendChild(probe);
      var col = getComputedStyle(probe).color;
      probe.remove();
      return parseColor(col, fallback);
    }
    function refreshPalette() {
      theme = resolveVar("--color-primary", "#14b8a6");
      fore = parseColor(getComputedStyle(document.body).color, "#e6e6f0");
      var card = resolveVar("--color-card", "#16162a");
      var lum = 0.2126 * card.r + 0.7152 * card.g + 0.0722 * card.b;
      lightTheme = lum > 140;
      moteBase = lightTheme ? 0 : 255;
    }
    function effectsOff() {
      try { return localStorage.getItem("vcl-effects-off") === "1"; }
      catch (e) { return false; }
    }
    function resize() {
      if (!canvas) return;
      dpr = window.devicePixelRatio || 1;
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
    }
    function onMove(e) {
      pointer.x = (e.clientX / window.innerWidth - 0.5) * 2;
      pointer.y = (e.clientY / window.innerHeight - 0.5) * 2;
    }
    function frame(t) {
      if (!canvas) return;
      var ctx = canvas.getContext("2d");
      var w = canvas.width, hgt = canvas.height;
      if (effectsOff()) { ctx.clearRect(0, 0, w, hgt); raf = requestAnimationFrame(frame); return; }
      eased.x += (pointer.x - eased.x) * 0.03;
      eased.y += (pointer.y - eased.y) * 0.03;
      ctx.clearRect(0, 0, w, hgt);
      var lx = (0.5 + 0.34 * Math.sin(t * 0.000041)) * w;
      var ly = (0.42 + 0.30 * Math.sin(t * 0.000029 + 1.7)) * hgt;
      var lr = Math.max(w, hgt) * 0.42;
      var glow = ctx.createRadialGradient(lx, ly, 0, lx, ly, lr);
      glow.addColorStop(0, "rgba(" + theme.r + "," + theme.g + "," + theme.b + ",0.34)");
      glow.addColorStop(0.55, "rgba(" + theme.r + "," + theme.g + "," + theme.b + ",0.13)");
      glow.addColorStop(1, "rgba(" + theme.r + "," + theme.g + "," + theme.b + ",0)");
      ctx.fillStyle = glow; ctx.fillRect(0, 0, w, hgt);
      var l2x = (0.5 - 0.38 * Math.sin(t * 0.000033 + 0.6)) * w;
      var l2y = (0.55 + 0.28 * Math.cos(t * 0.000047)) * hgt;
      var g2 = ctx.createRadialGradient(l2x, l2y, 0, l2x, l2y, lr * 0.7);
      g2.addColorStop(0, "rgba(" + fore.r + "," + fore.g + "," + fore.b + "," + (lightTheme ? 0.09 : 0.13) + ")");
      g2.addColorStop(1, "rgba(" + fore.r + "," + fore.g + "," + fore.b + ",0)");
      ctx.fillStyle = g2; ctx.fillRect(0, 0, w, hgt);
      for (var i = 0; i < stars.length; i++) {
        var st = stars[i];
        st.x += 0.000012 * (0.3 + st.depth);
        st.y -= 0.0000048 * (0.3 + st.depth);
        if (st.x > 1.02) st.x = -0.02;
        if (st.y < -0.02) st.y = 1.02;
        var px = (st.x + eased.x * 0.012 * st.depth) * w;
        var py = (st.y + eased.y * 0.012 * st.depth) * hgt;
        var a = (0.10 + 0.16 * st.depth) *
          (0.7 + 0.3 * Math.sin(t * 0.00045 * st.twinkle + st.phase));
        var base = st.themed ? theme : fore;
        var cr = Math.round(base.r * 0.45 + moteBase * 0.55);
        var cg = Math.round(base.g * 0.45 + moteBase * 0.55);
        var cb = Math.round(base.b * 0.45 + moteBase * 0.55);
        ctx.beginPath();
        ctx.fillStyle = "rgba(" + cr + "," + cg + "," + cb + "," + a + ")";
        ctx.arc(px, py, (0.5 + st.depth * 0.9) * dpr, 0, Math.PI * 2);
        ctx.fill();
      }
      raf = requestAnimationFrame(frame);
    }
    function mount() {
      if (canvas) return;
      stars = [];
      for (var i = 0; i < 140; i++) {
        stars.push({ x: Math.random(), y: Math.random(),
          depth: 0.35 + Math.random() * 0.65,
          phase: Math.random() * Math.PI * 2,
          twinkle: 0.4 + Math.random() * 0.8,
          themed: Math.random() < 0.45 });
      }
      tintEl = document.createElement("div");
      tintEl.className = "sl-ambient-tint";
      canvas = document.createElement("canvas");
      canvas.className = "sl-ambient-canvas";
      canvas.style.opacity = "0.95";
      document.body.appendChild(tintEl);
      document.body.appendChild(canvas);
      refreshPalette(); resize();
      window.addEventListener("resize", resize);
      window.addEventListener("mousemove", onMove);
      raf = requestAnimationFrame(frame);
    }
    function unmount() {
      if (!canvas) return;
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMove);
      canvas.remove(); tintEl.remove();
      canvas = null; tintEl = null;
    }
    function check() {
      var acvcOwns = !!document.getElementById("acvc-sidebar-order");
      if (ROUTES[window.location.pathname] && !acvcOwns) mount(); else unmount();
    }
    try {
      new MutationObserver(function () { refreshPalette(); })
        .observe(document.documentElement, { attributes: true, attributeFilter: ["class", "style", "data-theme"] });
    } catch (e) {}
    setInterval(refreshPalette, 3000);
    window.addEventListener("popstate", check);
    setInterval(check, 800);
    check();
  })();

  var React = SDK.React;
  var h = React.createElement;
  var hooks = SDK.hooks;
  var useState = hooks.useState;
  var useEffect = hooks.useEffect;
  var useCallback = hooks.useCallback;
  var useRef = hooks.useRef;

  var API = "/api/plugins/shorts-lab";

  function api(path, options) {
    return SDK.fetchJSON(API + path, options);
  }

  function postJSON(path, body) {
    return api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
  }

  var MUTED = "var(--color-muted-foreground, #9aa0b4)";

  function fmtViews(n) {
    n = Number(n) || 0;
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
    return String(n);
  }
  function fmtWhen(ts) {
    if (!ts) return "";
    return new Date(ts * 1000).toLocaleDateString(undefined,
      { month: "short", day: "numeric" });
  }
  function downloadText(name, text) {
    var blob = new Blob([text], { type: "text/markdown" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  function slug(s) {
    return String(s || "short").toLowerCase()
      .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "short";
  }

  // -------------------------------------------------------------------------
  // Tab 1 — Shorts Research
  // -------------------------------------------------------------------------
  function ShortsResearchTab(props) {
    var st = props.st;
    var addSt = useState("");
    var newHandle = addSt[0], setNewHandle = addSt[1];
    var busySt = useState(null);
    var busy = busySt[0], setBusy = busySt[1];
    var errSt = useState(null);
    var err = errSt[0], setErr = errSt[1];

    var sync = st.shortsSync || {};
    var analysis = st.shortsAnalysis;

    function addChannel() {
      var v = newHandle.trim();
      if (!v) return;
      setBusy("chan"); setErr(null);
      postJSON("/channels", { handle: v, action: "add" })
        .then(function (r) { props.onState(r.state); setNewHandle(""); })
        .catch(function (e) { setErr(String((e && e.message) || e)); })
        .finally(function () { setBusy(null); });
    }
    function removeChannel(handle) {
      postJSON("/channels", { handle: handle, action: "remove" })
        .then(function (r) { props.onState(r.state); })
        .catch(function (e) { setErr(String((e && e.message) || e)); });
    }
    function doSync() {
      setBusy("sync"); setErr(null);
      postJSON("/shorts/sync", {})
        .then(function (r) { props.onState(r.state); })
        .catch(function (e) { setErr(String((e && e.message) || e)); })
        .finally(function () { setBusy(null); });
    }
    function doAnalyze() {
      setBusy("analyze"); setErr(null);
      postJSON("/shorts/analyze", {})
        .then(function (r) { props.onState(r.state); })
        .catch(function (e) { setErr(String((e && e.message) || e)); })
        .finally(function () { setBusy(null); });
    }

    function analList(title, items) {
      if (!items || !items.length) return null;
      return h("div", null,
        h("div", { className: "sl-h" }, title),
        h("ul", { className: "sl-list" }, items.map(function (x, i) {
          return h("li", { key: i }, x);
        })));
    }

    return h("div", null,
      h("div", { className: "sl-card" },
        h("div", { style: { fontWeight: 800, marginBottom: 8 } },
          "Monitored competitors"),
        h("div", { className: "sl-note", style: { marginBottom: 10 } },
          "One list, two pages — this is the same competitor list YouTube " +
          "Insights tracks. Add or remove here and it updates there too."),
        h("div", { style: { display: "flex", gap: 8, flexWrap: "wrap",
                            alignItems: "center" } },
          (st.channels || []).map(function (c) {
            return h("span", { key: c, className: "sl-tag" }, c,
              h("button", { title: "Stop monitoring " + c,
                  onClick: function () { removeChannel(c); } }, "✕"));
          }),
          h("input", {
            className: "sl-input", style: { maxWidth: 220, display: "inline-block" },
            placeholder: "@channelhandle", value: newHandle,
            onChange: function (e) { setNewHandle(e.target.value); },
            onKeyDown: function (e) { if (e.key === "Enter") addChannel(); },
          }),
          h("button", { className: "sl-btn", disabled: busy !== null,
                        onClick: addChannel }, "＋ Add")),
        h("div", { style: { display: "flex", gap: 10, alignItems: "center",
                            flexWrap: "wrap", marginTop: 12 } },
          h("button", { className: "sl-btn sl-btn-primary",
              disabled: busy !== null || !!sync.running,
              title: "Pull the last 30 days of Shorts for every monitored channel",
              onClick: doSync },
            sync.running ? "Syncing…" : "⟳ Sync shorts (30 days)"),
          (st.shorts || []).length
            ? h("button", { className: "sl-btn", disabled: busy !== null,
                  title: "Mine the winning hooks, messages, formats, and styles",
                  onClick: doAnalyze },
                busy === "analyze" ? "Analyzing…" : "✨ Analyze what's winning")
            : null,
          sync.running
            ? h("span", { className: "sl-busy" },
                h("span", { className: "sl-spin" }, "◐"),
                " Pulling shorts + transcripts — safe to leave or refresh")
            : null,
          !sync.running && sync.summary
            ? h("span", { className: "sl-note" },
                "Last sync: " + (sync.summary.shorts || 0) + " shorts across " +
                (sync.summary.channels || 0) + " channel(s)" +
                ((sync.summary.errors || []).length
                  ? " · " + sync.summary.errors.length + " error(s)"
                  : ""))
            : null,
          !sync.running && sync.error
            ? h("span", { className: "sl-err" }, sync.error) : null),
        !st.keys.transcript
          ? h("div", { className: "sl-err", style: { marginTop: 8 } },
              "TRANSCRIPT_API_KEY is not set — add it on the Keys page " +
              "(same key YouTube Insights uses).")
          : null,
        err ? h("div", { className: "sl-err" }, err) : null,
        (sync.summary && (sync.summary.errors || []).length)
          ? h("div", { className: "sl-note", style: { marginTop: 6 } },
              sync.summary.errors.join(" · "))
          : null),

      analysis
        ? h("div", { className: "sl-card" },
            h("div", { style: { fontWeight: 800, marginBottom: 4 } },
              "🏆 What's winning" ,
              h("span", { className: "sl-note", style: { fontWeight: 400,
                  marginLeft: 8 } },
                analysis.shortCount + " shorts · last " + (analysis.days || 30) +
                " days")),
            h("p", { style: { fontSize: 13.5, margin: "6px 0 4px" } },
              analysis.summary),
            h("div", { className: "sl-anal-grid" },
              analList("Winning hooks", analysis.winningHooks),
              analList("Winning messages", analysis.winningMessages),
              analList("Winning formats", analysis.winningFormats),
              analList("Winning styles", analysis.winningStyles)),
            (analysis.channels || []).length
              ? h("div", null,
                  h("div", { className: "sl-h" }, "Per channel"),
                  h("ul", { className: "sl-list" },
                    analysis.channels.map(function (c, i) {
                      return h("li", { key: i },
                        h("b", null, c.channel + ": "),
                        c.whatIsWorking + " ",
                        h("span", { style: { color: MUTED } },
                          "hook: " + c.hookStyle + " · format: " + c.format));
                    })))
              : null,
            (analysis.opportunities || []).length
              ? h("div", null,
                  h("div", { className: "sl-h" }, "Your next derivatives"),
                  h("ul", { className: "sl-list" },
                    analysis.opportunities.map(function (o, i) {
                      return h("li", { key: i }, o, " ",
                        h("button", { className: "sl-btn",
                            style: { fontSize: 11, padding: "2px 10px" },
                            title: "Draft this on the Shorts Lab tab",
                            onClick: function () { props.onDraft(o); } },
                          "✍️ Draft this"));
                    })))
              : null)
        : null,

      h("div", { style: { fontWeight: 800, margin: "4px 0 10px" } },
        "Recent shorts",
        h("span", { className: "sl-note", style: { fontWeight: 400,
            marginLeft: 8 } },
          (st.shorts || []).length + " in the last 30 days")),
      (st.shorts || []).length === 0
        ? h("div", { className: "sl-card sl-note" },
            (st.channels || []).length
              ? "No shorts pulled yet — hit ⟳ Sync."
              : "Add a competitor channel above, then Sync.")
        : h("div", { className: "sl-grid" },
            st.shorts.map(function (s) {
              return h("div", { key: s.videoId, className: "sl-short" },
                s.thumbnail
                  ? h("a", { href: s.link, target: "_blank", rel: "noreferrer" },
                      h("img", { src: s.thumbnail, alt: "", loading: "lazy" }))
                  : null,
                h("div", { className: "sl-short-body" },
                  h("a", { href: s.link, target: "_blank", rel: "noreferrer",
                           style: { color: "inherit", textDecoration: "none" } },
                    h("div", { className: "sl-short-title" }, s.title)),
                  h("div", { className: "sl-short-meta" },
                    h("span", { className: "sl-views" },
                      fmtViews(s.viewCount) + " views"),
                    h("span", null, s.channel),
                    s.durationSeconds
                      ? h("span", null, Math.round(s.durationSeconds) + "s")
                      : null,
                    s.published ? h("span", null, fmtWhen(s.published)) : null,
                    s.hasTranscript
                      ? h("span", { title: "transcript captured" }, "📝")
                      : null)));
            })));
  }

  // -------------------------------------------------------------------------
  // Tab 2 — Shorts Content
  // -------------------------------------------------------------------------
  function ShortsContentTab(props) {
    var st = props.st;
    var briefSt = useState(props.draftBrief || "");
    var brief = briefSt[0], setBrief = briefSt[1];
    var patternSt = useState("");
    var pattern = patternSt[0], setPattern = patternSt[1];
    var busySt = useState(false);
    var busy = busySt[0], setBusy = busySt[1];
    var errSt = useState(null);
    var err = errSt[0], setErr = errSt[1];
    var openSt = useState(null);
    var open = openSt[0], setOpen = openSt[1];
    var contentSt = useState({});
    var contents = contentSt[0], setContents = contentSt[1];
    var postSelSt = useState({});      // creationId -> active post-copy tab
    var postSel = postSelSt[0], setPostSel = postSelSt[1];
    var selSt = useState({});          // creationId -> checked for publish
    var sel = selSt[0], setSel = selSt[1];
    var pubBusySt = useState(false);
    var pubBusy = pubBusySt[0], setPubBusy = pubBusySt[1];
    var pubDoneSt = useState(null);    // {url} after a publish
    var pubDone = pubDoneSt[0], setPubDone = pubDoneSt[1];
    var pagesSt = useState(null);      // null=closed, "loading", [] = list
    var pages = pagesSt[0], setPages = pagesSt[1];
    var metaModSt = useState(false);   // meta publish modal open
    var metaMod = metaModSt[0], setMetaMod = metaModSt[1];
    var adsetsSt = useState(null);
    var adsets = adsetsSt[0], setAdsets = adsetsSt[1];
    var adsetSt = useState("");
    var adsetId = adsetSt[0], setAdsetId = adsetSt[1];
    var linkSt = useState("");
    var metaLink = linkSt[0], setMetaLink = linkSt[1];
    var ctaSt = useState("LEARN_MORE");
    var metaCta = ctaSt[0], setMetaCta = ctaSt[1];
    var metaBusySt = useState(false);
    var metaBusy = metaBusySt[0], setMetaBusy = metaBusySt[1];
    var metaDoneSt = useState(null);
    var metaDone = metaDoneSt[0], setMetaDone = metaDoneSt[1];

    function openMetaPublish() {
      if (!st.keys.metaAds) { setShowConnect("metaads"); return; }
      var ids = Object.keys(sel).filter(function (k) { return sel[k]; });
      if (!ids.length) {
        setErr("Tick the ads to publish first (checkbox on each card).");
        return;
      }
      setMetaMod(true); setMetaDone(null);
      if (adsets === null) {
        setAdsets("loading");
        api("/adlab/meta/adsets")
          .then(function (r) { setAdsets(r.adsets || []); })
          .catch(function (e) {
            setAdsets([]);
            setErr(String((e && e.message) || e));
          });
      }
    }

    function runMetaPublish() {
      if (metaBusy) return;
      var ids = Object.keys(sel).filter(function (k) { return sel[k]; })
        .map(Number);
      setMetaBusy(true); setMetaDone(null);
      postJSON("/adlab/meta/publish", {
        ids: ids, adsetId: adsetId, link: metaLink, cta: metaCta })
        .then(function (r) {
          setMetaDone(r.published || []);
          setSel({});
          props.onState(r.state);
        })
        .catch(function (e) { setMetaDone(String((e && e.message) || e)); })
        .finally(function () { setMetaBusy(false); });
    }

    function toggleSel(id) {
      var next = {};
      Object.keys(sel).forEach(function (k) { next[k] = sel[k]; });
      next[id] = !next[id];
      setSel(next);
    }

    function publishSurge() {
      if (pubBusy) return;
      if (!st.keys.surge) { setShowConnect("surge"); return; }
      var ids = Object.keys(sel).filter(function (k) { return sel[k]; })
        .map(Number);
      if (!ids.length) {
        setErr("Tick the ads to publish first (checkbox on each card).");
        return;
      }
      setPubBusy(true); setErr(null); setPubDone(null);
      postJSON("/adlab/surge/publish", { ids: ids })
        .then(function (r) {
          setPubDone(r.page);
          setSel({});
          props.onState(r.state);
        })
        .catch(function (e) { setErr(String((e && e.message) || e)); })
        .finally(function () { setPubBusy(false); });
    }

    function loadPages() {
      if (!st.keys.surge) { setShowConnect("surge"); return; }
      setPages("loading");
      api("/adlab/surge/pages")
        .then(function (r) { setPages(r.pages || []); })
        .catch(function (e) {
          setPages([]);
          setErr(String((e && e.message) || e));
        });
    }

    useEffect(function () {
      if (props.draftBrief) setBrief(props.draftBrief);
    }, [props.draftBrief]);

    var analysis = st.shortsAnalysis;
    var patterns = [];
    if (analysis) {
      (analysis.winningFormats || []).forEach(function (f) { patterns.push(f); });
      (analysis.winningHooks || []).slice(0, 5).forEach(function (f) {
        patterns.push("Hook: " + f);
      });
    }

    var briefRef = useRef(null);
    function generate() {
      if (busy) return;
      if (!brief.trim()) {
        setErr("Describe the short first — one sentence about the topic is enough.");
        if (briefRef.current) briefRef.current.focus();
        return;
      }
      setBusy(true); setErr(null);
      postJSON("/derivative", { brief: brief, pattern: pattern })
        .then(function (r) {
          props.onState(r.state);
          setOpen(r.creationId);
          loadContent(r.creationId);
        })
        .catch(function (e) { setErr(String((e && e.message) || e)); })
        .finally(function () { setBusy(false); });
    }
    function loadContent(id) {
      if (contents[id]) return;
      api("/creation/" + id).then(function (c) {
        setContents(function (prev) {
          var next = Object.assign({}, prev);
          next[id] = c.content || "";
          return next;
        });
      }).catch(function () {});
    }
    function remove(id) {
      postJSON("/creations/delete", { id: id })
        .then(function (r) { props.onState(r.state); })
        .catch(function () {});
    }

    var scripts = (st.creations || []).filter(function (c) {
      return c.kind === "short-script";
    });

    return h("div", null,
      h("div", { className: "sl-card" },
        h("div", { style: { fontWeight: 800, marginBottom: 6 } },
          "✍️ New derivative short"),
        h("div", { className: "sl-note", style: { marginBottom: 10 } },
          "A derivative borrows the PATTERN that's winning — hook mechanics, " +
          "structure, pacing — and applies it to your topic in your voice. " +
          (analysis ? "The current winning-pattern analysis rides into every draft."
                    : "Run ✨ Analyze on Shorts Research first for pattern-grounded drafts.")),
        h("textarea", {
          className: "sl-input", rows: 3, ref: briefRef,
          placeholder: "What is this short about? Topic, audience, the one thing viewers should take away…",
          value: brief,
          onChange: function (e) { setBrief(e.target.value); },
        }),
        patterns.length
          ? h("select", {
              className: "sl-input", style: { marginTop: 8, width: "auto",
                maxWidth: "100%" },
              value: pattern,
              onChange: function (e) { setPattern(e.target.value); },
            },
            [h("option", { key: "", value: "" }, "Pattern: let the writer pick")]
              .concat(patterns.map(function (p, i) {
                return h("option", { key: i, value: p },
                  p.length > 90 ? p.slice(0, 90) + "…" : p);
              })))
          : null,
        h("div", { style: { marginTop: 10 } },
          h("button", { className: "sl-btn sl-btn-primary",
              disabled: busy, onClick: generate },
            busy ? "Writing…" : "✨ Write the script")),
        err ? h("div", { className: "sl-err" }, err) : null),

      h("div", { style: { fontWeight: 800, margin: "4px 0 10px" } },
        "Your scripts",
        h("span", { className: "sl-note",
            style: { fontWeight: 400, marginLeft: 8 } },
          scripts.length + " draft(s)")),
      scripts.length === 0
        ? h("div", { className: "sl-card sl-note" },
            "Nothing yet — describe a short above and hit ✨.")
        : scripts.map(function (c) {
            var isOpen = open === c.id;
            return h("div", { key: c.id, className: "sl-card sl-creation" },
              h("div", { className: "sl-creation-head",
                  onClick: function () {
                    setOpen(isOpen ? null : c.id);
                    if (!isOpen) loadContent(c.id);
                  } },
                c.status === "ready" && c.kind === "image-ad"
                  ? h("input", { type: "checkbox",
                      checked: !!sel[c.id],
                      title: "Include in the surge.sh ad pack",
                      style: { accentColor: "var(--color-primary, #14b8a6)",
                               cursor: "pointer" },
                      onClick: function (e) { e.stopPropagation(); },
                      onChange: function () { toggleSel(c.id); } })
                  : null,
                h("span", { className: "sl-chev" + (isOpen ? " sl-chev-open" : "") }, "▸"),
                h("span", { style: { fontWeight: 700, flex: 1 } }, c.title),
                c.pattern
                  ? h("span", { className: "sl-chip",
                      title: c.pattern }, "pattern")
                  : null,
                h("button", { className: "sl-btn", style: { fontSize: 12 },
                    title: "Download as markdown",
                    onClick: function (e) {
                      e.stopPropagation();
                      var text = contents[c.id];
                      if (text) { downloadText(slug(c.title) + ".md", text); return; }
                      api("/creation/" + c.id).then(function (d) {
                        downloadText(slug(c.title) + ".md", d.content || "");
                      }).catch(function () {});
                    } }, "⬇ Download"),
                h("button", { className: "sl-btn", style: { fontSize: 12 },
                    onClick: function (e) { e.stopPropagation(); remove(c.id); } },
                  "🗑"),
                h("span", { className: "sl-note" }, fmtWhen(c.createdAt))),
              isOpen
                ? h("pre", { className: "sl-md" },
                    contents[c.id] || "Loading…")
                : null);
          }));
  }

  // -------------------------------------------------------------------------
  // Tab 3 — Ads Research
  // -------------------------------------------------------------------------
  var AD_LIB = "https://www.facebook.com/ads/library/";
  function libPageUrl(pageId) {
    return AD_LIB + "?active_status=all&ad_type=all&country=US" +
      "&search_type=page&view_all_page_id=" + encodeURIComponent(pageId);
  }
  function libTermUrl(term) {
    return AD_LIB + "?active_status=all&ad_type=all&country=US" +
      "&q=" + encodeURIComponent(term) + "&search_type=keyword_unordered";
  }
  // accepts a raw numeric page id or a pasted Ad Library URL
  function extractPageId(text) {
    text = String(text || "").trim();
    var m = text.match(/view_all_page_id=(\d{5,})/);
    if (m) return m[1];
    if (/^\d{5,}$/.test(text)) return text;
    return null;
  }

  // brand-mark platform icons, inline SVG (no external assets) — the same
  // row the Ad Library shows under "Platforms"
  function platIcon(key, i) {
    var S = { width: 18, height: 18, viewBox: "0 0 24 24", key: i };
    var title = key.toLowerCase().replace(/_/g, " ");
    function wrap(bg, children) {
      return h("svg", Object.assign({}, S, { style: { display: "block" } }),
        h("title", null, title),
        h("circle", { cx: 12, cy: 12, r: 12, fill: bg }),
        children);
    }
    if (key === "FACEBOOK") {
      return wrap("#1877F2",
        h("path", { fill: "#fff",
          d: "M13.4 21v-6.9h2.3l.35-2.7h-2.65V9.6c0-.78.22-1.31 1.34-1.31" +
             "h1.43V5.9c-.25-.03-1.1-.11-2.09-.11-2.07 0-3.48 1.26-3.48 " +
             "3.58v2h-2.33v2.7h2.33V21z" }));
    }
    if (key === "INSTAGRAM") {
      return wrap("#E4405F", h("g", { stroke: "#fff", fill: "none",
          strokeWidth: 1.6 },
        h("rect", { x: 6.6, y: 6.6, width: 10.8, height: 10.8, rx: 3.4 }),
        h("circle", { cx: 12, cy: 12, r: 2.7 }),
        h("circle", { cx: 15.6, cy: 8.4, r: 0.4, fill: "#fff" })));
    }
    if (key === "MESSENGER") {
      return wrap("#0084FF",
        h("path", { fill: "#fff",
          d: "M6.2 14.6l4.1-4.4 2.2 2.1 5.3-2.9-4.1 4.4-2.2-2.1z" }));
    }
    if (key === "WHATSAPP") {
      return wrap("#25D366",
        h("path", { fill: "#fff",
          d: "M8.6 7.2c.35-.8 1.55-1 2-.3l.85 1.4c.24.4.1.9-.25 1.2l-.6." +
             "55c.55 1.15 1.5 2.1 2.65 2.65l.55-.6c.3-.35.8-.5 1.2-.25l1" +
             ".4.85c.7.45.5 1.65-.3 2-.95.4-2.2.3-3.85-.65-1.7-1-2.85-2." +
             "15-3.6-3.85-.5-1.15-.4-2.1-.05-3z" }));
    }
    if (key === "THREADS") {
      return h("svg", Object.assign({}, S, { style: { display: "block" } }),
        h("title", null, title),
        h("circle", { cx: 12, cy: 12, r: 11.2, fill: "#000",
            stroke: "#fff", strokeWidth: 1.6 }),
        h("text", { x: 12, y: 16.4, textAnchor: "middle", fontSize: 12.5,
            fill: "#fff", fontWeight: 700, fontFamily: "inherit" }, "@"));
    }
    // Audience Network (and anything new Meta adds)
    return wrap("#0668E1",
      h("text", { x: 12, y: 15.8, textAnchor: "middle", fontSize: 8,
          fill: "#fff", fontWeight: 800,
          fontFamily: "inherit" },
        key === "AUDIENCE_NETWORK" ? "AN" : key.slice(0, 2)));
  }
  function platBadges(platforms) {
    return h("span", { className: "sl-plats" },
      (platforms || []).map(function (p, i) {
        return platIcon(String(p || "").toUpperCase(), i);
      }));
  }

  function extLink(href, label) {
    return h("a", { href: href, target: "_blank", rel: "noreferrer",
      className: "sl-link" }, label || href.replace(/^https?:\/\//, ""));
  }

  // Steps verified against the live consoles, Aug 2026.
  function ApifySteps() {
    return h("ol", { className: "sl-list", style: { fontSize: 13 } },
      h("li", null, "Create a free Apify account at ",
        extLink("https://apify.com", "apify.com"),
        " — the free plan includes monthly platform credit; no Meta " +
        "account or app review involved."),
      h("li", null, "Open ",
        extLink("https://console.apify.com/settings/integrations",
          "Console → Settings → API & Integrations"),
        " and copy your Personal API token."),
      h("li", null, "Paste it below. Pulls run the official ",
        extLink("https://apify.com/apify/facebook-ads-scraper",
          "Facebook Ads Library Scraper"),
        " actor against each monitored page's public Ad Library — " +
        "pay-per-result, a few cents per sync."));
  }

  function MetaSteps() {
    return h("ol", { className: "sl-list", style: { fontSize: 13 } },
      h("li", null, "Heads-up: Meta's official Ad Library API is the " +
        "heavyweight path — it requires a business-linked account and " +
        "app review. If you just want competitor ads, Connect Apify " +
        "instead (2 minutes)."),
      h("li", null, "Create an app of type Business at ",
        extLink("https://developers.facebook.com/apps",
          "developers.facebook.com/apps"), "."),
      h("li", null, "In App Review → Permissions and Features, request ",
        h("b", null, "ads_read"),
        " (written use case + data-handling notes; review typically " +
        "takes 5–10 business days) and complete ",
        extLink("https://business.facebook.com/settings/security",
          "Business Verification"), "."),
      h("li", null, "Accept the Ad Library API terms at ",
        extLink("https://www.facebook.com/ads/library/api",
          "facebook.com/ads/library/api"), "."),
      h("li", null, "In the ",
        extLink("https://developers.facebook.com/tools/explorer",
          "Graph API Explorer"),
        ", pick your app, add the ads_read permission, and click " +
        "Generate Access Token."),
      h("li", null, "Extend it to long-lived (~60 days) in the ",
        extLink("https://developers.facebook.com/tools/debug/accesstoken",
          "Access Token Debugger"),
        " ('Extend Access Token'), then paste the extended token below."),
      h("li", null, "Tokens expire in ~60 days — repeat the last two " +
        "steps to renew."));
  }

  function KieSteps() {
    return h("ol", { className: "sl-list", style: { fontSize: 13 } },
      h("li", null, "Create an account at ",
        extLink("https://kie.ai", "kie.ai"),
        " — pay-as-you-go credits power the ad generation."),
      h("li", null, "Open ",
        extLink("https://kie.ai/api-key", "kie.ai/api-key"),
        " and copy your API key."),
      h("li", null, "Paste it below — it's verified against your credit " +
        "balance before saving."));
  }

  function ImgbbSteps() {
    return h("ol", { className: "sl-list", style: { fontSize: 13 } },
      h("li", null, "Create a free account at ",
        extLink("https://imgbb.com", "imgbb.com"), "."),
      h("li", null, "Open ",
        extLink("https://api.imgbb.com", "api.imgbb.com"),
        " and click Get API key — it shows instantly, no review."),
      h("li", null, "Paste it below. Your uploaded reference images are " +
        "hosted here at public URLs so the generator can fetch them " +
        "(KIE takes URLs only)."));
  }

  function SurgeSteps() {
    return h("ol", { className: "sl-steps" },
      h("li", null, "surge.sh (",
        extLink("https://surge.sh", "surge.sh"),
        ") is the free static-hosting service your ad packs publish to."),
      h("li", null, "Enter an email and a password below — a NEW email " +
        "creates your surge account on the spot; an existing account " +
        "just signs in. The password is used once to mint your access " +
        "token and is never stored."),
      h("li", null, "Published pages live at https://<name>.surge.sh — " +
        "share the link with your editor."),
      h("li", null, h("i", null, "Already have a surge token? Leave the " +
        "email empty and paste the token in the second field.")));
  }

  function MetaAdsSteps() {
    return h("ol", { className: "sl-steps" },
      h("li", null, "You need three values — a token with ads_management, ",
        "your ad account id, and the Facebook Page the ads run under."),
      h("li", null, "Token: in ",
        extLink("https://developers.facebook.com/tools/explorer/",
          "Graph API Explorer"),
        " pick your app, add permissions ", h("code", null, "ads_management"),
        " + ", h("code", null, "pages_show_list"),
        ", Generate Access Token, then extend it to long-lived in ",
        extLink("https://developers.facebook.com/tools/debug/accesstoken/",
          "Access Token Debugger"),
        " (or mint a permanent System User token in ",
        extLink("https://business.facebook.com/settings/system-users",
          "Business settings → System users"), ")."),
      h("li", null, "Ad account id: ",
        extLink("https://adsmanager.facebook.com/adsmanager/manage/accounts",
          "Ads Manager → Accounts"),
        " — the number after act_ (paste with or without the prefix)."),
      h("li", null, "Page id: ",
        extLink("https://www.facebook.com/pages/?category=your_pages",
          "Your Pages"),
        " → open the Page → About → Page transparency (or Settings → " +
        "Page setup) shows the numeric Page ID."),
      h("li", null, "Ads publish as ", h("b", null, "PAUSED drafts"),
        " — nothing spends until you launch them in Ads Manager."));
  }

  var CONNECT_KINDS = {
    apify: { env: "APIFY_API_TOKEN", title: "🔗 Connect Apify (easy path)",
             steps: ApifySteps, ph: "Paste your Apify API token (apify_api_…)" },
    meta: { env: "META_ACCESS_TOKEN", title: "🔗 Connect Meta (official API)",
            steps: MetaSteps, ph: "Paste the long-lived token (EAAB…)" },
    kie: { env: "KIE_API_KEY", title: "🔗 Connect KIE (the generator)",
           steps: KieSteps, ph: "Paste your KIE API key" },
    imgbb: { env: "IMGBB_API_KEY", title: "🔗 Connect imgBB (image hosting)",
             steps: ImgbbSteps, ph: "Paste your imgBB API key" },
    surge: { env: "SURGE_TOKEN", title: "🔗 Connect surge.sh (ad-pack pages)",
             steps: SurgeSteps,
             ph: "Password (new account or existing) — or a surge token",
             loginPh: "Email — new address creates the account",
             loginOptional: true },
    metaads: { env: "META_AD_ACCOUNT_ID",
               title: "📣 Connect Meta Ads (paused-draft publishing)",
               steps: MetaAdsSteps,
               ph: "Access token (ads_management scope)",
               loginPh: "Ad account id (with or without act_)",
               extraPh: "Facebook Page id (numeric)" },
  };

  function ConnectModal(props) {
    var keySt = useState("");
    var keyVal = keySt[0], setKeyVal = keySt[1];
    var loginSt = useState(props.defaultLogin || "");
    var loginVal = loginSt[0], setLoginVal = loginSt[1];
    var extraSt = useState("");
    var extraVal = extraSt[0], setExtraVal = extraSt[1];
    var busySt = useState(false);
    var busy = busySt[0], setBusy = busySt[1];
    var errSt = useState(null);
    var err = errSt[0], setErr = errSt[1];
    var spec = CONNECT_KINDS[props.kind] || CONNECT_KINDS.meta;

    function save() {
      if (!keyVal.trim() || busy) return;
      setBusy(true); setErr(null);
      postJSON("/connect", {
        env: spec.env,
        key: keyVal.trim(),
        login: loginVal.trim(),
        extra: extraVal.trim(),
      })
        .then(function (r) { props.onState(r.state); props.onClose(); })
        .catch(function (e) { setErr(String((e && e.message) || e)); })
        .finally(function () { setBusy(false); });
    }

    return h("div", { className: "sl-modal", onClick: function (e) {
          if (e.target === e.currentTarget) props.onClose();
        } },
      h("div", { className: "sl-modal-box" },
        h("div", { style: { fontWeight: 800, fontSize: 15, marginBottom: 8 } },
          spec.title),
        h(spec.steps),
        spec.loginPh
          ? h("input", {
              className: "sl-input",
              type: spec.extraPh ? "text" : "email",
              placeholder: spec.loginPh, value: loginVal,
              style: { marginTop: 10 },
              onChange: function (e) { setLoginVal(e.target.value); },
            })
          : null,
        spec.extraPh
          ? h("input", {
              className: "sl-input", type: "text",
              placeholder: spec.extraPh, value: extraVal,
              style: { marginTop: 10 },
              onChange: function (e) { setExtraVal(e.target.value); },
            })
          : null,
        h("input", {
          className: "sl-input", type: "password", autoFocus: true,
          placeholder: spec.ph,
          value: keyVal, style: { marginTop: 10 },
          onChange: function (e) { setKeyVal(e.target.value); },
          onKeyDown: function (e) { if (e.key === "Enter") save(); },
        }),
        err ? h("div", { className: "sl-err" }, err) : null,
        h("div", { className: "sl-modal-row" },
          h("button", { className: "sl-btn", onClick: props.onClose },
            "Cancel"),
          h("button", { className: "sl-btn sl-btn-primary",
              disabled: busy || !keyVal.trim() ||
                (spec.loginPh && !spec.loginOptional && !loginVal.trim()) ||
                (spec.extraPh && !extraVal.trim()),
              onClick: save },
            busy ? "Verifying…" : "Verify & save"))));
  }

  function AdsResearchTab(props) {
    var st = props.st;
    var qSt = useState("");
    var q = qSt[0], setQ = qSt[1];
    var resultsSt = useState(null);
    var results = resultsSt[0], setResults = resultsSt[1];
    var busySt = useState(null);
    var busy = busySt[0], setBusy = busySt[1];
    var errSt = useState(null);
    var err = errSt[0], setErr = errSt[1];

    var sync = st.adsSync || {};
    var connectSt = useState(false);
    var showConnect = connectSt[0], setShowConnect = connectSt[1];
    var endedSt = useState(false);
    var showEnded = endedSt[0], setShowEnded = endedSt[1];
    var pageFilterSt = useState({});      // page_id -> true (multi-select)
    var pageFilter = pageFilterSt[0], setPageFilter = pageFilterSt[1];
    function togglePageFilter(pid) {
      setPageFilter(function (prev) {
        var next = Object.assign({}, prev);
        if (next[pid]) delete next[pid]; else next[pid] = true;
        return next;
      });
    }
    var moreSt = useState({});        // archive_id -> full text shown
    var moreMap = moreSt[0], setMoreMap = moreSt[1];
    var playSt = useState({});        // archive_id -> video playing
    var playMap = playSt[0], setPlayMap = playSt[1];
    function toggleMap(setter, id) {
      setter(function (prev) {
        var next = Object.assign({}, prev);
        next[id] = !prev[id];
        return next;
      });
    }

    function search() {
      if (busy) return;
      if (!q.trim()) { setErr("Type a brand or keyword — or paste an Ad Library URL / page id."); return; }
      var pid = extractPageId(q);
      if (pid) {              // pasted page id or library URL — no API needed
        monitor(pid, "Page " + pid);
        setQ("");
        return;
      }
      setBusy("search"); setErr(null);
      postJSON("/ads/search", { term: q.trim() })
        .then(function (r) { setResults(r.results || []); })
        .catch(function (e) { setErr(String((e && e.message) || e)); })
        .finally(function () { setBusy(null); });
    }
    function monitor(pid, name) {
      setBusy("mon"); setErr(null);
      postJSON("/ads/monitor", { pageId: pid, name: name })
        .then(function (r) { props.onState(r.state); })
        .catch(function (e) { setErr(String((e && e.message) || e)); })
        .finally(function () { setBusy(null); });
    }
    function unmonitor(pid) {
      postJSON("/ads/unmonitor", { pageId: pid })
        .then(function (r) { props.onState(r.state); })
        .catch(function () {});
    }
    function doSync() {
      setBusy("sync"); setErr(null);
      postJSON("/ads/sync", {})
        .then(function (r) { props.onState(r.state); })
        .catch(function (e) { setErr(String((e && e.message) || e)); })
        .finally(function () { setBusy(null); });
    }

    var monitored = {};
    (st.adPages || []).forEach(function (p) { monitored[p.page_id] = true; });

    return h("div", null,
      h("div", { className: "sl-card" },
        h("div", { style: { display: "flex", alignItems: "center", gap: 10,
                            flexWrap: "wrap", marginBottom: 6 } },
          h("div", { style: { fontWeight: 800, flex: 1 } },
            "🔎 Find competitors in the Meta Ad Library"),
          h("button", {
              className: "sl-tag",
              style: st.keys.apify
                ? { color: "var(--color-primary, #14b8a6)",
                    borderColor: "color-mix(in srgb, var(--color-primary, #14b8a6) 60%, transparent)",
                    cursor: "pointer" }
                : { cursor: "pointer" },
              title: st.keys.apify
                ? "Apify connected — click to replace the token"
                : "2-minute signup, scrapes the public Ad Library — the easy path",
              onClick: function () { setShowConnect("apify"); },
            }, st.keys.apify ? "✓ Apify connected" : "🔗 Connect Apify"),
          h("span", { className: "sl-note" }, "or"),
          h("button", {
              className: "sl-tag",
              style: st.keys.meta
                ? { color: "var(--color-primary, #14b8a6)",
                    borderColor: "color-mix(in srgb, var(--color-primary, #14b8a6) 60%, transparent)",
                    cursor: "pointer" }
                : { cursor: "pointer" },
              title: st.keys.meta
                ? "Meta connected — click to replace the token"
                : "The official API — business verification + app review required",
              onClick: function () { setShowConnect("meta"); },
            }, st.keys.meta ? "✓ Meta connected" : "🔗 Connect Meta"),
          st.keys.apify && st.keys.meta
            ? h("span", { style: { display: "inline-flex", gap: 4 } },
                [["apify", "Apify"], ["meta", "Meta"]].map(function (o) {
                  return h("button", { key: o[0],
                    className: "sl-tab" +
                      (st.adsSource === o[0] ? " sl-tab-on" : ""),
                    style: { fontSize: 11, padding: "3px 10px" },
                    title: "Pull ads via " + o[1],
                    onClick: function () {
                      postJSON("/ads/source", { source: o[0] })
                        .then(function (r) { props.onState(r.state); })
                        .catch(function () {});
                    } }, o[1]);
                }))
            : null),
        h("div", { style: { display: "flex", gap: 8, flexWrap: "wrap" } },
          h("input", {
            className: "sl-input", style: { maxWidth: 360 },
            placeholder: "Brand, competitor, or niche term…", value: q,
            onChange: function (e) { setQ(e.target.value); },
            onKeyDown: function (e) { if (e.key === "Enter") search(); },
          }),
          h("button", { className: "sl-btn sl-btn-primary",
              disabled: busy !== null, onClick: search },
            busy === "search"
              ? (st.adsSource === "apify" ? "Searching (Apify, ~1 min)…"
                                          : "Searching…")
              : "Search"),
          q.trim() && !extractPageId(q)
            ? h("a", { className: "sl-link", href: libTermUrl(q.trim()),
                target: "_blank", rel: "noreferrer",
                style: { alignSelf: "center" } }, "Open in Ad Library ↗")
            : null),
        h("div", { className: "sl-note", style: { marginTop: 8 } },
          (st.keys.meta || st.keys.apify)
            ? "Pulls run via " +
              (st.adsSource === "apify" ? "Apify (public Ad Library scrape)"
                                        : "the official Meta API") +
              ". You can also paste an Ad Library URL or page id to " +
              "monitor directly." +
              (st.adsSource === "apify"
                ? " Name search runs the Apify actor too — expect ~30-90s."
                : " Name search uses the Meta token.")
            : "No key needed to browse: hit ↗ to open the public Ad " +
              "Library, find the competitor's page, then paste its library " +
              "URL (or view_all_page_id number) here to monitor it. " +
              "Connect Apify (2 minutes) or Meta above to pull their ads " +
              "into this tab with longest-running ranking."),

        err ? h("div", { className: "sl-err" }, err) : null,
        results
          ? (results.length
              ? h("div", { style: { marginTop: 10 } },
                  results.map(function (r) {
                    return h("div", { key: r.pageId,
                        style: { display: "flex", gap: 10, alignItems: "center",
                                 padding: "6px 0", flexWrap: "wrap" } },
                      h("span", { style: { fontWeight: 700 } }, r.name),
                      h("span", { className: "sl-note" },
                        r.adCount + " ad(s) seen"),
                      h("span", { style: { flex: 1 } }),
                      monitored[r.pageId]
                        ? h("span", { className: "sl-chip" }, "monitored")
                        : h("button", { className: "sl-btn",
                            style: { fontSize: 12 },
                            disabled: busy !== null,
                            onClick: function () { monitor(r.pageId, r.name); } },
                          "👁 Monitor"));
                  }))
              : h("div", { className: "sl-note", style: { marginTop: 10 } },
                  "No pages found for that term — try the brand's exact name."))
          : null),

      showConnect
        ? h(ConnectModal, { kind: showConnect, onState: props.onState,
            onClose: function () { setShowConnect(false); } })
        : null,
      h("div", { className: "sl-card" },
        h("div", { style: { display: "flex", gap: 10, alignItems: "center",
                            flexWrap: "wrap" } },
          h("div", { style: { fontWeight: 800 } }, "Monitored pages"),
          (st.adPages || []).map(function (p) {
            return h("span", { key: p.page_id, className: "sl-tag" },
              h("a", { href: libPageUrl(p.page_id), target: "_blank",
                  rel: "noreferrer",
                  title: "See all their ads in the public Ad Library",
                  style: { color: "inherit", textDecoration: "none" } },
                p.name || p.page_id),
              h("button", { title: "Stop monitoring",
                  onClick: function () { unmonitor(p.page_id); } }, "✕"));
          }),
          (st.adPages || []).length === 0
            ? h("span", { className: "sl-note" },
                "none yet — search above and hit 👁 Monitor")
            : null,
          h("span", { style: { flex: 1 } }),
          (st.adPages || []).length && (st.keys.meta || st.keys.apify)
            ? h("button", { className: "sl-btn sl-btn-primary",
                title: "Pull ads via " +
                  (st.adsSource === "apify" ? "Apify" : "the Meta API"),
                disabled: busy !== null || !!sync.running, onClick: doSync },
                sync.running ? "Syncing…" : "⟳ Sync ads")
            : null,
          sync.running
            ? h("span", { className: "sl-busy" },
                h("span", { className: "sl-spin" }, "◐"), " Pulling ads…")
            : null,
          !sync.running && sync.error
            ? h("span", { className: "sl-err" }, sync.error) : null)),

      h("div", { style: { fontWeight: 800, margin: "4px 0 10px" } },
        "Their active ads — longest running first",
        h("span", { className: "sl-note", style: { fontWeight: 400,
            marginLeft: 8 } },
          "a long run means it keeps paying — those are the ones to study" +
          " · low-impression ads sink to the bottom")),
      (st.adPages || []).length > 1
        ? h("div", { className: "sl-filterbar" },
            (st.adPages || []).map(function (p) {
              var n = (st.ads || []).filter(function (a) {
                return a.page_id === p.page_id && a.active;
              }).length;
              return h("button", { key: p.page_id,
                  className: "sl-tab" +
                    (pageFilter[p.page_id] ? " sl-tab-on" : ""),
                  title: "Show only " + (p.name || p.page_id) +
                    " (select several to combine)",
                  onClick: function () { togglePageFilter(p.page_id); } },
                (p.name || p.page_id) + (n ? " (" + n + ")" : ""));
            }),
            Object.keys(pageFilter).length
              ? h("button", { className: "sl-btn", style: { fontSize: 12 },
                  onClick: function () { setPageFilter({}); } }, "✕ clear")
              : null)
        : null,
      (function () {
        var all = st.ads || [];
        var anyPageSelected = Object.keys(pageFilter).length > 0;
        if (anyPageSelected) {
          all = all.filter(function (a) { return pageFilter[a.page_id]; });
        }
        var activeAds = all.filter(function (a) { return a.active; });
        var endedAds = all.filter(function (a) { return !a.active; });
        var shown = showEnded ? all : activeAds;
        // low-impression ads sink to the bottom; longest-running order is
        // preserved within each group (stable sort on a boolean key)
        function isLow(a) {
          var imp = (a.creative || {}).impressions || "";
          return imp.indexOf("<") !== -1;
        }
        shown = shown.filter(function (a) { return !isLow(a); })
          .concat(shown.filter(isLow));
        if (!all.length) {
          return h("div", { className: "sl-card sl-note" },
            (st.keys.meta || st.keys.apify)
              ? "No ads pulled yet — monitor a page and Sync."
              : "Connect Apify or Meta to pull ads in — until then, each " +
                "monitored page above links straight to all of its ads.");
        }
        function adCard(a) {
          var cr = a.creative || {};
          var when = a.started
            ? new Date(a.started * 1000).toLocaleDateString(undefined,
                { month: "short", day: "numeric", year: "numeric" })
            : null;
          return h("div", { key: a.archive_id, className: "sl-adcard" },
            h("div", { className: "sl-adcard-top" },
              h("span", { className: "sl-chip " +
                  (a.active ? "sl-active" : "sl-ended") },
                a.active ? "● Active" : "ended"),
              cr.impressions && cr.impressions.indexOf("<") !== -1
                ? h("span", { className: "sl-lowimp",
                    title: "Meta reports " + cr.impressions +
                      " impressions for this ad" },
                    "Low impression count")
                : null,
              h("span", { className: "sl-days" },
                a.daysRunning != null ? a.daysRunning + "d" : "—"),
              h("span", { style: { flex: 1 } }),
              h("a", { className: "sl-extlink",
                  href: a.snapshot_url || libPageUrl(a.page_id),
                  target: "_blank", rel: "noreferrer",
                  title: "Open the real ad in the Ad Library" },
                h("svg", { width: 15, height: 15, viewBox: "0 0 24 24",
                    fill: "none", stroke: "currentColor", strokeWidth: 2,
                    strokeLinecap: "round", strokeLinejoin: "round" },
                  h("path", { d: "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8" +
                      "a2 2 0 0 1 2-2h6" }),
                  h("polyline", { points: "15 3 21 3 21 9" }),
                  h("line", { x1: 10, y1: 14, x2: 21, y2: 3 })))),
            when
              ? h("div", { className: "sl-note",
                  style: { padding: "0 12px" } },
                  "Started running " + when)
              : null,
            (a.platforms || []).length || cr.impressions
              ? h("div", { className: "sl-adcard-plats" },
                  (a.platforms || []).length
                    ? h(React.Fragment, null,
                        h("span", { className: "sl-note",
                            style: { fontSize: 11 } }, "Platforms"),
                        platBadges(a.platforms))
                    : null,
                  cr.impressions && cr.impressions.indexOf("<") === -1
                    ? h("span", { className: "sl-note",
                        style: { fontSize: 11 } },
                        "👁 " + cr.impressions + " impressions")
                    : null)
              : null,
            h("div", { className: "sl-adcard-id" },
              cr.profile
                ? h("img", { className: "sl-avatar", src: cr.profile,
                    alt: "" })
                : h("span", { className: "sl-avatar sl-avatar-ph" },
                    (a.page_name || "?").slice(0, 1)),
              h("div", null,
                h("div", { style: { fontWeight: 700, fontSize: 13 } },
                  a.page_name),
                h("div", { className: "sl-note",
                    style: { fontSize: 11 } }, "Sponsored"))),
            cr.body
              ? h(React.Fragment, null,
                  h("div", { className: "sl-adcard-body" +
                      (moreMap[a.archive_id] ? " sl-adcard-body-full" : "") },
                    cr.body),
                  cr.body.length > 140
                    ? h("button", { className: "sl-more",
                        onClick: function () {
                          toggleMap(setMoreMap, a.archive_id);
                        } },
                        moreMap[a.archive_id] ? "less" : "more",
                        h("span", { className: "sl-chev" +
                            (moreMap[a.archive_id] ? " sl-chev-open" : ""),
                            style: { marginLeft: 4 } }, "▸"))
                    : null)
              : null,
            cr.image || cr.videoUrl
              ? h("div", { className: "sl-adcard-media" },
                  playMap[a.archive_id] && cr.videoUrl
                    ? h("video", { src: cr.videoUrl, controls: true,
                        autoPlay: true, playsInline: true,
                        poster: cr.image || undefined,
                        onError: function () {
                          toggleMap(setPlayMap, a.archive_id);
                        } })
                    : h(React.Fragment, null,
                        cr.image
                          ? h("img", { src: cr.image, alt: "",
                              loading: "lazy" })
                          : null,
                        cr.videoUrl
                          ? h("button", { className: "sl-play",
                              title: "Play the ad video",
                              onClick: function () {
                                toggleMap(setPlayMap, a.archive_id);
                              } }, "▶")
                          : cr.video
                            ? h("span", { className: "sl-play",
                                style: { pointerEvents: "none" } }, "▶")
                            : null))
              : null,
            (cr.title || cr.cta)
              ? h("div", { className: "sl-adcard-cta" },
                  h("span", { style: { fontWeight: 700, fontSize: 12.5,
                      flex: 1 } }, cr.title || ""),
                  cr.cta
                    ? h("span", { className: "sl-chip" }, cr.cta)
                    : null)
              : null,
            h("div", { className: "sl-adcard-foot" },
              h("span", { style: { flex: 1 } }),
              h("button", { className: "sl-btn", style: { fontSize: 11.5,
                  padding: "3px 10px" },
                  title: "Clone this winner's style with your own assets",
                  onClick: function () {
                    var lines = [
                      a.page_name + " ad — running " +
                        (a.daysRunning != null ? a.daysRunning + " days"
                                               : "n/a") +
                        (a.active ? ", still active" : ", ended") + ".",
                    ];
                    if (cr.title) lines.push("Headline: " + cr.title);
                    if (cr.cta) lines.push("CTA: " + cr.cta);
                    if (cr.body) lines.push("FULL AD COPY:\n" + cr.body);
                    if (cr.link) lines.push("Landing page: " + cr.link);
                    lines.push("Snapshot: " + a.snapshot_url);
                    props.onUseAd({
                      context: lines.join("\n"),
                      styleImage: cr.image || "",
                    });
                  } },
                h("svg", { width: 13, height: 13, viewBox: "0 0 24 24",
                    fill: "currentColor",
                    style: { marginRight: 5, verticalAlign: "-1px" } },
                  h("path", { d: "M12 2l1.9 6.1L20 10l-6.1 1.9L12 18l-1.9" +
                      "-6.1L4 10l6.1-1.9zM19 15l.9 2.6L22.5 18.5l-2.6.9" +
                      "L19 22l-.9-2.6-2.6-.9 2.6-.9z" })),
                "Use in Ads Lab")));
        }
        return h(React.Fragment, null,
          shown.length
            ? h("div", { className: "sl-adgrid" },
                shown.slice(0, 60).map(adCard))
            : h("div", { className: "sl-card sl-note" },
                "No active ads right now — Sync again later, or show the " +
                "ended ones below."),
          endedAds.length
            ? h("div", { style: { marginTop: 10 } },
                h("button", { className: "sl-btn", style: { fontSize: 12 },
                    onClick: function () { setShowEnded(!showEnded); } },
                  showEnded
                    ? "Hide ended ads"
                    : "Show " + endedAds.length + " ended ad(s)"))
            : null);
      })());
  }

  // -------------------------------------------------------------------------
  // Tab 4 — Ads Lab
  // -------------------------------------------------------------------------
  function UploadSlot(props) {
    var inputRef = useRef(null);
    var busySt = useState(false);
    var busy = busySt[0], setBusy = busySt[1];
    var dragSt = useState(false);
    var dragOver = dragSt[0], setDragOver = dragSt[1];

    function takeFile(f) {
      if (!f) return;
      setBusy(true);
      var reader = new FileReader();
      reader.onload = function () {
        var b64 = String(reader.result || "").split(",")[1] || "";
        postJSON("/asset", { filename: f.name, dataBase64: b64 })
          .then(function (r) { props.onUploaded(r.assetId, f.name); })
          .catch(function (err2) {
            props.onError(String((err2 && err2.message) || err2));
          })
          .finally(function () { setBusy(false); });
      };
      reader.readAsDataURL(f);
    }

    function onFile(e) {
      takeFile(e.target.files && e.target.files[0]);
    }

    return h("div", {
        className: "sl-upload" + (props.value ? " sl-upload-on" : ""),
        style: Object.assign({ flex: 1, minWidth: 200 },
          dragOver ? { borderColor: "var(--color-primary, #14b8a6)",
                       background: "color-mix(in srgb, var(--color-primary, #14b8a6) 8%, transparent)" }
                   : null),
        onClick: function () {
          if (inputRef.current) inputRef.current.click();
        },
        onDragOver: function (e) { e.preventDefault(); setDragOver(true); },
        onDragLeave: function () { setDragOver(false); },
        onDrop: function (e) {
          e.preventDefault();
          setDragOver(false);
          var f = e.dataTransfer && e.dataTransfer.files &&
                  e.dataTransfer.files[0];
          if (f && /^image\//.test(f.type || "")) takeFile(f);
        } },
      h("input", { type: "file", accept: "image/*",
        style: { display: "none" }, ref: inputRef, onChange: onFile }),
      busy ? "Uploading…"
           : (props.value ? "✓ " + props.value
                          : props.label + " — click or drop"));
  }

  function AdvancedStudio(props) {
    var st = props.st;
    var openSt = useState(function () {
      try { return localStorage.getItem("sl-adv-open") === "1"; }
      catch (e) { return false; }
    });
    var open = openSt[0], setOpen = openSt[1];
    var advSt = useState(null);           // /advanced/state payload
    var adv = advSt[0], setAdv = advSt[1];
    var secSt = useState("recipes");      // recipes|refs|tools|log
    var sec = secSt[0], setSec = secSt[1];
    var folderSt = useState("influencers");
    var folder = folderSt[0], setFolder = folderSt[1];
    var pickSt = useState([]);            // selected reference paths
    var picks = pickSt[0], setPicks = pickSt[1];
    var recSt = useState("ugc-selfie");
    var recId = recSt[0], setRecId = recSt[1];
    var briefSt = useState("");
    var brief = briefSt[0], setBrief = briefSt[1];
    var extraSt = useState("");
    var extra = extraSt[0], setExtra = extraSt[1];
    var modelSt = useState("");
    var model = modelSt[0], setModel = modelSt[1];
    var arSt = useState("9:16");
    var ar = arSt[0], setAr = arSt[1];
    var durSt = useState(0);
    var dur = durSt[0], setDur = durSt[1];
    var nSt = useState(1);
    var nVar = nSt[0], setNVar = nSt[1];
    var busySt = useState(false);
    var busy = busySt[0], setBusy = busySt[1];
    var errSt = useState(null);
    var err = errSt[0], setErr = errSt[1];
    var okSt = useState(null);
    var okMsg = okSt[0], setOkMsg = okSt[1];
    var impSt = useState(false);
    var importing = impSt[0], setImporting = impSt[1];
    var avUrlSt = useState("");
    var avUrl = avUrlSt[0], setAvUrl = avUrlSt[1];
    var avDescSt = useState("");
    var avDesc = avDescSt[0], setAvDesc = avDescSt[1];

    function loadAdv() {
      api("/advanced/state").then(setAdv).catch(function (e) {
        setErr(String((e && e.message) || e));
      });
    }
    useEffect(function () {
      if (open && !adv) loadAdv();
      try { localStorage.setItem("sl-adv-open", open ? "1" : "0"); }
      catch (e) {}
    }, [open]);

    var rec = null;
    if (adv) {
      (adv.recipes || []).forEach(function (r) {
        if (r.id === recId) rec = r;
      });
    }
    var isVideo = rec && rec.media === "video";
    var kieOk = !!(adv && adv.capabilities && adv.capabilities.kie);

    function togglePick(p) {
      var next = picks.indexOf(p) >= 0
        ? picks.filter(function (x) { return x !== p; })
        : picks.concat([p]);
      setPicks(next);
    }

    function runRecipe() {
      if (busy || !rec) return;
      if (!brief.trim() && rec.kind !== "tool") {
        setErr("Describe what to make first."); return;
      }
      setBusy(true); setErr(null); setOkMsg(null);
      postJSON("/advanced/recipe/start", {
        recipe: recId, brief: brief, extra: extra, model: model,
        aspectRatio: ar, duration: Number(dur) || 0, variants: nVar,
        refPaths: picks,
      })
        .then(function (r) {
          props.onState(r.state);
          setOkMsg((r.creationIds || []).length +
            " creation(s) started — they land in the list below.");
          setPicks([]);
        })
        .catch(function (e) { setErr(String((e && e.message) || e)); })
        .finally(function () { setBusy(false); });
    }

    function runAnalyze(kind) {
      if (busy) return;
      if (!avUrl.trim() && !avDesc.trim()) {
        setErr("Give the video URL and describe it."); return;
      }
      setBusy(true); setErr(null); setOkMsg(null);
      postJSON("/advanced/analyze-video",
        { url: avUrl, description: avDesc, recipe: kind })
        .then(function (r) {
          setOkMsg("Template saved: " + r.template.name);
          loadAdv();
        })
        .catch(function (e) { setErr(String((e && e.message) || e)); })
        .finally(function () { setBusy(false); });
    }

    function importStarter() {
      if (importing) return;
      setImporting(true); setErr(null);
      postJSON("/reference/import-starter", {})
        .then(function (r) {
          setOkMsg("Starter pack: " + r.imported + " imported, " +
            r.skipped + " already present.");
          loadAdv();
        })
        .catch(function (e) { setErr(String((e && e.message) || e)); })
        .finally(function () { setImporting(false); });
    }

    function uploadRef(file) {
      var reader = new FileReader();
      reader.onload = function () {
        var b64 = String(reader.result || "").split(",")[1] || "";
        postJSON("/reference/upload",
          { folder: folder, filename: file.name, dataBase64: b64 })
          .then(function () { loadAdv(); })
          .catch(function (e) { setErr(String((e && e.message) || e)); });
      };
      reader.readAsDataURL(file);
    }

    var refInputRef = useRef(null);

    return h("div", { className: "sl-card" },
      h("div", { className: "sl-creation-head",
          onClick: function () { setOpen(!open); } },
        h("span", { className: "sl-chev" + (open ? " sl-chev-open" : "") },
          "▸"),
        h("span", { style: { fontWeight: 800, flex: 1 } },
          "⚙ Advanced studio"),
        h("span", { className: "sl-note" },
          "references · recipes · video · pipelines")),
      !open ? null : !adv
        ? h("div", { className: "sl-note", style: { marginTop: 10 } },
            "Loading studio…")
        : h("div", { style: { marginTop: 12 } },
            h("div", { style: { display: "flex", gap: 6, flexWrap: "wrap",
                marginBottom: 12 } },
              [["recipes", "✨ Recipes"], ["refs", "🗂 References"],
               ["tools", "🔎 Reverse-engineer"], ["log", "🧾 Log"]]
                .map(function (t) {
                  return h("button", { key: t[0], className: "sl-tag",
                      style: sec === t[0]
                        ? { color: "var(--color-primary, #14b8a6)",
                            borderColor: "color-mix(in srgb, var(--color-primary, #14b8a6) 60%, transparent)",
                            cursor: "pointer" }
                        : { cursor: "pointer" },
                      onClick: function () { setSec(t[0]); } }, t[1]);
                })),

            sec === "refs" ? h("div", null,
              h("div", { style: { display: "flex", gap: 6, flexWrap: "wrap",
                  alignItems: "center", marginBottom: 10 } },
                ["influencers", "products", "aesthetics", "examples"]
                  .map(function (f) {
                    return h("button", { key: f, className: "sl-tag",
                        style: folder === f
                          ? { color: "var(--color-primary, #14b8a6)",
                              borderColor: "color-mix(in srgb, var(--color-primary, #14b8a6) 60%, transparent)",
                              cursor: "pointer" }
                          : { cursor: "pointer" },
                        onClick: function () { setFolder(f); } }, f);
                  }),
                h("span", { style: { flex: 1 } }),
                h("button", { className: "sl-btn",
                    style: { fontSize: 12 },
                    onClick: function () {
                      if (refInputRef.current) refInputRef.current.click();
                    } }, "⬆ Upload"),
                h("input", { type: "file", accept: "image/*",
                    style: { display: "none" }, ref: refInputRef,
                    onChange: function (e) {
                      var f = e.target.files && e.target.files[0];
                      if (f) uploadRef(f);
                    } }),
                h("button", { className: "sl-btn",
                    style: { fontSize: 12 }, disabled: importing,
                    title: "Pull the ad-builder kit's influencer sheets, " +
                      "products, and ugc-selfie style frames",
                    onClick: importStarter },
                  importing ? "◐ Importing…" : "📦 Import starter pack")),
              h("div", { className: "sl-note",
                  style: { marginBottom: 8 } },
                "Click a reference to attach it to the next recipe run (" +
                picks.length + " selected). Influencer sheets: hero, " +
                "close-up, and full-body per character."),
              h("div", { style: { display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(96px, 1fr))",
                  gap: 8 } },
                ((adv.references || {})[folder] || []).map(function (rf) {
                  var on = picks.indexOf(rf.path) >= 0;
                  return h("div", { key: rf.path,
                      style: { position: "relative", cursor: "pointer" },
                      title: rf.path,
                      onClick: function () { togglePick(rf.path); } },
                    h("img", { src: API + "/reference/" + rf.path,
                        style: { width: "100%", height: 96,
                          objectFit: "cover", borderRadius: 8,
                          border: on
                            ? "2px solid var(--color-primary, #14b8a6)"
                            : "1px solid var(--color-border, #2b2b44)" } }),
                    rf.group
                      ? h("div", { className: "sl-note",
                          style: { fontSize: 9.5, overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap" } }, rf.group)
                      : null);
                })),
              ((adv.references || {})[folder] || []).length === 0
                ? h("div", { className: "sl-note" },
                    "Empty — upload images or import the starter pack.")
                : null) : null,

            sec === "recipes" ? h("div", null,
              h("div", { style: { display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))",
                  gap: 8, marginBottom: 12 } },
                (adv.recipes || []).filter(function (r) {
                  return r.kind !== "tool";
                }).map(function (r) {
                  var on = r.id === recId;
                  return h("div", { key: r.id,
                      className: "sl-copytake",
                      style: { cursor: "pointer", flexDirection: "column",
                        alignItems: "stretch",
                        borderColor: on
                          ? "color-mix(in srgb, var(--color-primary, #14b8a6) 60%, transparent)"
                          : undefined },
                      onClick: function () {
                        setRecId(r.id); setModel(r.model || "");
                      } },
                    h("div", { style: { fontWeight: 800,
                        fontSize: 12.5 } },
                      r.emoji + " " + r.name,
                      r.media === "video"
                        ? h("span", { className: "sl-note",
                            style: { marginLeft: 6, fontSize: 10 } },
                            "🎬 video · KIE")
                        : null),
                    h("div", { className: "sl-note",
                        style: { fontSize: 11 } }, r.desc));
                })),
              rec && isVideo && !kieOk
                ? h("div", { className: "sl-err",
                    style: { marginBottom: 8 } },
                    "🎬 Video + sound run on KIE only — the instance " +
                    "image model (" +
                    (((adv.capabilities || {}).instanceModel || {}).model ||
                      "grok") +
                    ") does images, not video. Connect KIE to run this " +
                    "recipe.")
                : null,
              h("textarea", { className: "sl-input", rows: 3,
                  placeholder: rec && rec.id === "character-sheet"
                    ? "Describe the influencer — age, hair, features, " +
                      "lighting… (name goes in Extra direction)"
                    : "What are we making? Product, audience, message…",
                  value: brief,
                  onChange: function (e) { setBrief(e.target.value); } }),
              h("input", { className: "sl-input",
                  style: { marginTop: 8 },
                  placeholder: rec && rec.id === "character-sheet"
                    ? "Influencer name (folder slug)"
                    : "Extra direction (optional)",
                  value: extra,
                  onChange: function (e) { setExtra(e.target.value); } }),
              h("div", { style: { display: "flex", gap: 10,
                  alignItems: "center", flexWrap: "wrap",
                  marginTop: 10 } },
                isVideo
                  ? h("select", { className: "sl-input",
                      style: { width: "auto" }, value: model,
                      onChange: function (e) { setModel(e.target.value); } },
                      Object.keys(adv.models || {}).filter(function (m) {
                        return adv.models[m].type === "video";
                      }).map(function (m) {
                        var mi = adv.models[m];
                        return h("option", { key: m, value: m },
                          mi.label + (mi.audio ? " · 🔊" : " · silent"));
                      }))
                  : null,
                isVideo && model && adv.models[model]
                  ? h("select", { className: "sl-input",
                      style: { width: "auto" }, value: String(dur),
                      onChange: function (e) { setDur(e.target.value); } },
                      [h("option", { key: "auto", value: "0" }, "auto")]
                        .concat((adv.models[model].durations || [])
                          .map(function (d) {
                            return h("option", { key: d, value: String(d) },
                              d + "s");
                          })))
                  : null,
                h("select", { className: "sl-input",
                    style: { width: "auto" }, value: ar,
                    onChange: function (e) { setAr(e.target.value); } },
                  ["9:16", "16:9", "1:1", "4:5", "3:2", "2:3"]
                    .map(function (a) {
                      return h("option", { key: a, value: a }, a);
                    })),
                h("select", { className: "sl-input",
                    style: { width: "auto" }, value: String(nVar),
                    onChange: function (e) {
                      setNVar(Number(e.target.value));
                    } },
                  [1, 2, 3, 4].map(function (n) {
                    return h("option", { key: n, value: String(n) }, n);
                  })),
                h("button", { className: "sl-btn sl-btn-primary",
                    disabled: busy || (isVideo && !kieOk),
                    onClick: runRecipe },
                  busy
                    ? h(React.Fragment, null,
                        h("span", { className: "sl-spin",
                            style: { marginRight: 6 } }, "◐"),
                        "Working…")
                    : "✨ Run recipe"),
                picks.length
                  ? h("span", { className: "sl-note" },
                      picks.length + " reference(s) attached")
                  : null)) : null,

            sec === "tools" ? h("div", null,
              h("div", { className: "sl-note",
                  style: { marginBottom: 8 } },
                "Reverse-engineer a reference video into a reusable " +
                "Seedance template, or clone it straight onto your " +
                "product."),
              h("input", { className: "sl-input",
                  placeholder: "Reference video URL",
                  value: avUrl,
                  onChange: function (e) { setAvUrl(e.target.value); } }),
              h("textarea", { className: "sl-input", rows: 3,
                  style: { marginTop: 8 },
                  placeholder: "Describe the video shot by shot — hook, " +
                    "scenes, text overlays, audio…",
                  value: avDesc,
                  onChange: function (e) { setAvDesc(e.target.value); } }),
              h("div", { style: { display: "flex", gap: 10,
                  marginTop: 10 } },
                h("button", { className: "sl-btn", disabled: busy,
                    onClick: function () { runAnalyze("analyze-video"); } },
                  "🔎 Extract template"),
                h("button", { className: "sl-btn", disabled: busy,
                    onClick: function () { runAnalyze("clone-ad"); } },
                  "🧪 Clone for my product")),
              (adv.videoTemplates || []).length
                ? h("div", { style: { marginTop: 12 } },
                    h("div", { style: { fontWeight: 800, fontSize: 13,
                        marginBottom: 6 } }, "Saved templates"),
                    (adv.videoTemplates || []).map(function (t, i) {
                      return h("div", { key: i, className: "sl-copytake" },
                        h("span", { style: { flex: 1 } },
                          h("b", null, t.name),
                          h("span", { className: "sl-note",
                              style: { marginLeft: 6 } },
                            (t.parameters || []).join(", "))),
                        h("button", { className: "sl-btn",
                            style: { fontSize: 11, padding: "2px 8px" },
                            title: "Copy the template prompt",
                            onClick: function () {
                              try {
                                navigator.clipboard.writeText(t.template);
                              } catch (e2) {}
                            } }, "⧉"));
                    }))
                : null) : null,

            sec === "log" ? h("div", null,
              (adv.log || []).length === 0
                ? h("div", { className: "sl-note" },
                    "No generations logged yet.")
                : (adv.log || []).map(function (row, i) {
                    return h("div", { key: i, className: "sl-copytake",
                        style: { fontSize: 11.5 } },
                      h("span", { style: { flex: 1 } },
                        row.model + " · " + row.kind +
                        (row.duration ? " · " + row.duration + "s" : "")),
                      h("span", { className: "sl-note" },
                        new Date((row.at || 0) * 1000)
                          .toLocaleString()));
                  })) : null,

            err ? h("div", { className: "sl-err",
                style: { marginTop: 8 } }, err) : null,
            okMsg ? h("div", { style: { marginTop: 8, fontSize: 12.5,
                color: "var(--color-primary, #14b8a6)" } }, okMsg)
              : null));
  }

  function AdLabTabWrap(props) {
    return h(AdsLabTab, props);
  }

  function loadAdLabSaved() {
    try {
      return JSON.parse(localStorage.getItem("sl-adlab") || "{}") || {};
    } catch (e) { return {}; }
  }

  function AdsLabTab(props) {
    var st = props.st;
    var savedSt = useState(loadAdLabSaved);
    var saved = savedSt[0];
    var connectSt = useState(false);
    var showConnect = connectSt[0], setShowConnect = connectSt[1];
    var briefSt = useState(saved.brief || "");
    var brief = briefSt[0], setBrief = briefSt[1];
    var ctxSt = useState(props.adContext || saved.adContext || "");
    var adContext = ctxSt[0], setAdContext = ctxSt[1];
    var srcSt = useState(saved.source || null);   // {id, name}
    var source = srcSt[0], setSource = srcSt[1];
    var stySt = useState(saved.styleRef || null);
    var styleRef = stySt[0], setStyleRef = stySt[1];
    var adStyleSt = useState(props.adStyleUrl || saved.adStyle || "");
    var adStyle = adStyleSt[0], setAdStyle = adStyleSt[1];
    var varSt = useState(saved.variants || 1);
    var variants = varSt[0], setVariants = varSt[1];
    var iterSt = useState(null);       // creation being iterated
    var iterFor = iterSt[0], setIterFor = iterSt[1];
    var iterTextSt = useState("");
    var iterText = iterTextSt[0], setIterText = iterTextSt[1];
    var iterNSt = useState(1);
    var iterN = iterNSt[0], setIterN = iterNSt[1];
    var iterBusySt = useState(false);
    var iterBusy = iterBusySt[0], setIterBusy = iterBusySt[1];
    var iterErrSt = useState(null);
    var iterErr = iterErrSt[0], setIterErr = iterErrSt[1];

    var job = st.adlabJob || {};
    var jobRunning = !!job.running;
    var ib = st.imageBackend || {};
    var hermesOk = !!(ib.hermes && ib.hermes.available);
    var useKie = !hermesOk || (ib.active || "kie") === "kie";

    function setBackend(backend) {
      postJSON("/adlab/backend", { backend: backend })
        .then(function (r) { props.onState(r.state); })
        .catch(function (e) { setErr(String((e && e.message) || e)); });
    }

    function runIterate() {
      if (!iterText.trim() || iterBusy) return;
      setIterBusy(true);
      setIterErr(null);
      postJSON("/adlab/iterate", { id: iterFor.id, instruction: iterText,
                                   variants: iterN })
        .then(function (r) {
          props.onState(r.state);
          setIterFor(null);
          setIterText("");
        })
        .catch(function (e) {
          setIterErr(String((e && e.message) || e));
        })
        .finally(function () { setIterBusy(false); });
    }
    var busySt = useState(false);
    var busy = busySt[0], setBusy = busySt[1];
    var errSt = useState(null);
    var err = errSt[0], setErr = errSt[1];
    var openSt = useState(null);
    var open = openSt[0], setOpen = openSt[1];
    var contentSt = useState({});
    var contents = contentSt[0], setContents = contentSt[1];
    var postSelSt = useState({});      // creationId -> active post-copy tab
    var postSel = postSelSt[0], setPostSel = postSelSt[1];
    var selSt = useState({});          // creationId -> checked for publish
    var sel = selSt[0], setSel = selSt[1];
    var pubBusySt = useState(false);
    var pubBusy = pubBusySt[0], setPubBusy = pubBusySt[1];
    var pubDoneSt = useState(null);    // {url} after a publish
    var pubDone = pubDoneSt[0], setPubDone = pubDoneSt[1];
    var pagesSt = useState(null);      // null=closed, "loading", [] = list
    var pages = pagesSt[0], setPages = pagesSt[1];
    var metaModSt = useState(false);   // meta publish modal open
    var metaMod = metaModSt[0], setMetaMod = metaModSt[1];
    var adsetsSt = useState(null);
    var adsets = adsetsSt[0], setAdsets = adsetsSt[1];
    var adsetSt = useState("");
    var adsetId = adsetSt[0], setAdsetId = adsetSt[1];
    var linkSt = useState("");
    var metaLink = linkSt[0], setMetaLink = linkSt[1];
    var ctaSt = useState("LEARN_MORE");
    var metaCta = ctaSt[0], setMetaCta = ctaSt[1];
    var metaBusySt = useState(false);
    var metaBusy = metaBusySt[0], setMetaBusy = metaBusySt[1];
    var metaDoneSt = useState(null);
    var metaDone = metaDoneSt[0], setMetaDone = metaDoneSt[1];

    function openMetaPublish() {
      if (!st.keys.metaAds) { setShowConnect("metaads"); return; }
      var ids = Object.keys(sel).filter(function (k) { return sel[k]; });
      if (!ids.length) {
        setErr("Tick the ads to publish first (checkbox on each card).");
        return;
      }
      setMetaMod(true); setMetaDone(null);
      if (adsets === null) {
        setAdsets("loading");
        api("/adlab/meta/adsets")
          .then(function (r) { setAdsets(r.adsets || []); })
          .catch(function (e) {
            setAdsets([]);
            setErr(String((e && e.message) || e));
          });
      }
    }

    function runMetaPublish() {
      if (metaBusy) return;
      var ids = Object.keys(sel).filter(function (k) { return sel[k]; })
        .map(Number);
      setMetaBusy(true); setMetaDone(null);
      postJSON("/adlab/meta/publish", {
        ids: ids, adsetId: adsetId, link: metaLink, cta: metaCta })
        .then(function (r) {
          setMetaDone(r.published || []);
          setSel({});
          props.onState(r.state);
        })
        .catch(function (e) { setMetaDone(String((e && e.message) || e)); })
        .finally(function () { setMetaBusy(false); });
    }

    function toggleSel(id) {
      var next = {};
      Object.keys(sel).forEach(function (k) { next[k] = sel[k]; });
      next[id] = !next[id];
      setSel(next);
    }

    function publishSurge() {
      if (pubBusy) return;
      if (!st.keys.surge) { setShowConnect("surge"); return; }
      var ids = Object.keys(sel).filter(function (k) { return sel[k]; })
        .map(Number);
      if (!ids.length) {
        setErr("Tick the ads to publish first (checkbox on each card).");
        return;
      }
      setPubBusy(true); setErr(null); setPubDone(null);
      postJSON("/adlab/surge/publish", { ids: ids })
        .then(function (r) {
          setPubDone(r.page);
          setSel({});
          props.onState(r.state);
        })
        .catch(function (e) { setErr(String((e && e.message) || e)); })
        .finally(function () { setPubBusy(false); });
    }

    function loadPages() {
      if (!st.keys.surge) { setShowConnect("surge"); return; }
      setPages("loading");
      api("/adlab/surge/pages")
        .then(function (r) { setPages(r.pages || []); })
        .catch(function (e) {
          setPages([]);
          setErr(String((e && e.message) || e));
        });
    }

    // survive refresh / tab switches — the Clear button resets this
    useEffect(function () {
      try {
        localStorage.setItem("sl-adlab", JSON.stringify({
          brief: brief, adContext: adContext, source: source,
          styleRef: styleRef, adStyle: adStyle, variants: variants }));
      } catch (e) {}
    }, [brief, adContext, source, styleRef, adStyle, variants]);

    function clearForm() {
      setBrief(""); setAdContext(""); setSource(null);
      setStyleRef(null); setAdStyle(""); setVariants(1); setErr(null);
      try { localStorage.removeItem("sl-adlab"); } catch (e) {}
    }

    useEffect(function () {
      if (props.adContext) setAdContext(props.adContext);
    }, [props.adContext]);
    useEffect(function () {
      if (props.adStyleUrl) setAdStyle(props.adStyleUrl);
    }, [props.adStyleUrl]);

    var briefRef = useRef(null);
    function generate() {
      if (busy || jobRunning) return;
      if (!brief.trim()) {
        setErr("Describe your product/offer first — that's what the ad sells.");
        if (briefRef.current) briefRef.current.focus();
        return;
      }
      setBusy(true); setErr(null);
      postJSON("/adlab/generate", {
        brief: brief, adContext: adContext,
        sourceAssetId: source ? source.id : "",
        styleAssetId: styleRef ? styleRef.id : "",
        styleUrl: (!styleRef && adStyle) ? adStyle : "",
        variants: variants,
      })
        .then(function (r) { props.onState(r.state); setOpen(r.creationId); })
        .catch(function (e) { setErr(String((e && e.message) || e)); })
        .finally(function () { setBusy(false); });
    }
    function loadContent(id) {
      if (contents[id]) return;
      api("/creation/" + id).then(function (c) {
        setContents(function (prev) {
          var next = Object.assign({}, prev);
          next[id] = c.content || "";
          return next;
        });
      }).catch(function () {});
    }
    function remove(id) {
      postJSON("/creations/delete", { id: id })
        .then(function (r) { props.onState(r.state); })
        .catch(function () {});
    }

    var adsCreations = (st.creations || []).filter(function (c) {
      return c.kind === "image-ad" || c.kind === "video-ad" ||
        c.kind === "pipeline";
    });

    return h("div", null,
      showConnect
        ? h(ConnectModal, { kind: showConnect, onState: props.onState,
            defaultLogin: st.surgeEmail || "",
            onClose: function () { setShowConnect(false); } })
        : null,
      iterFor
        ? h("div", { className: "sl-modal", onClick: function (e) {
              if (e.target === e.currentTarget) setIterFor(null);
            } },
            h("div", { className: "sl-modal-box" },
              h("div", { style: { fontWeight: 800, fontSize: 15,
                  marginBottom: 6 } }, "↻ Iterate: " + iterFor.title),
              iterFor.resultUrl
                ? h("img", { src: iterFor.resultUrl, alt: "",
                    style: { width: 120, borderRadius: 8,
                             marginBottom: 8 } })
                : null,
              h("div", { className: "sl-note", style: { marginBottom: 8 } },
                "Your instruction edits THIS image — everything else " +
                "stays as rendered."),
              h("textarea", { className: "sl-input", rows: 3,
                  autoFocus: true,
                  placeholder: "e.g. make the headline larger and move it above my head; swap the red accents to teal…",
                  value: iterText,
                  onChange: function (e) { setIterText(e.target.value); } }),
              h("div", { style: { display: "flex", gap: 8,
                  alignItems: "center", marginTop: 8 } },
                h("span", { className: "sl-note" }, "takes"),
                h("select", { className: "sl-input",
                    style: { width: "auto" }, value: String(iterN),
                    onChange: function (e) { setIterN(Number(e.target.value)); } },
                  [1, 2, 3, 4].map(function (n) {
                    return h("option", { key: n, value: String(n) }, n);
                  }))),
              h("div", { className: "sl-modal-row" },
                h("button", { className: "sl-btn",
                    onClick: function () { setIterFor(null); } }, "Cancel"),
                h("button", { className: "sl-btn sl-btn-primary",
                    disabled: iterBusy || !iterText.trim(),
                    onClick: runIterate },
                  iterBusy
                    ? h(React.Fragment, null,
                        h("span", { className: "sl-spin",
                            style: { marginRight: 6 } }, "◐"),
                        "Submitting…")
                    : "↻ Apply the edit")),
              iterErr
                ? h("div", { className: "sl-err", style: { marginTop: 8 } },
                    iterErr)
                : null))
        : null,
      h("div", { className: "sl-card" },
        h("div", { style: { display: "flex", alignItems: "center", gap: 10,
                            flexWrap: "wrap", marginBottom: 6 } },
          h("div", { style: { fontWeight: 800, flex: 1 } },
            "🎨 Clone a winning ad's style"),
          h("button", { className: "sl-tag",
              style: { cursor: "pointer" },
              title: "Reset the form — brief, winning-ad context, images, " +
                "and variant count (saved between visits until cleared)",
              onClick: clearForm }, "✕ Reset"),
          hermesOk
            ? h(React.Fragment, null,
                h("span", { className: "sl-note" }, "generator"),
                h("button", {
                    className: "sl-tag",
                    style: !useKie
                      ? { color: "var(--color-primary, #14b8a6)",
                          borderColor: "color-mix(in srgb, var(--color-primary, #14b8a6) 60%, transparent)",
                          cursor: "pointer" }
                      : { cursor: "pointer" },
                    title: "This instance's own image model" +
                      (ib.hermes && ib.hermes.provider
                        ? " via " + ib.hermes.provider : "") +
                      " — no KIE or imgBB keys needed",
                    onClick: function () { setBackend("hermes"); },
                  }, "⚡ " + ((ib.hermes && (ib.hermes.model ||
                       ib.hermes.provider)) || "Instance model")),
                h("button", {
                    className: "sl-tag",
                    style: useKie
                      ? { color: "var(--color-primary, #14b8a6)",
                          borderColor: "color-mix(in srgb, var(--color-primary, #14b8a6) 60%, transparent)",
                          cursor: "pointer" }
                      : { cursor: "pointer" },
                    title: "Generate on KIE.ai instead (pay-as-you-go; " +
                      "needs the KIE + imgBB keys)",
                    onClick: function () { setBackend("kie"); },
                  }, "KIE.ai"))
            : null,
          !useKie ? null : h("button", {
              className: "sl-tag",
              style: st.keys.kie
                ? { color: "var(--color-primary, #14b8a6)",
                    borderColor: "color-mix(in srgb, var(--color-primary, #14b8a6) 60%, transparent)",
                    cursor: "pointer" }
                : { cursor: "pointer" },
              title: st.keys.kie
                ? "KIE connected — click to replace the key"
                : "The generator — pay-as-you-go image models",
              onClick: function () { setShowConnect("kie"); },
            }, st.keys.kie ? "✓ KIE connected" : "🔗 Connect KIE"),
          !useKie ? null : h("span", { className: "sl-note" }, "and"),
          !useKie ? null : h("button", {
              className: "sl-tag",
              style: st.keys.imgbb
                ? { color: "var(--color-primary, #14b8a6)",
                    borderColor: "color-mix(in srgb, var(--color-primary, #14b8a6) 60%, transparent)",
                    cursor: "pointer" }
                : { cursor: "pointer" },
              title: st.keys.imgbb
                ? "imgBB connected — click to replace the key"
                : "Free image hosting for your uploaded reference images",
              onClick: function () { setShowConnect("imgbb"); },
            }, st.keys.imgbb ? "✓ imgBB connected" : "🔗 Connect imgBB")),
        h("div", { className: "sl-note", style: { marginBottom: 10 } },
          "The image-ad-clone method: your source image (a portrait, your " +
          "product) is converted INTO the style of the winning ad — its " +
          "composition, text placement, and mood — with your offer's copy. " +
          "Grab a screenshot of the winning creative (View creative ↗ on " +
          "Ads Research) as the style reference."),
        h("textarea", {
          className: "sl-input", rows: 3, ref: briefRef,
          placeholder: "Your product/offer + audience — e.g. 'AI security bootcamp for career-switchers, $497, launch week urgency'…",
          value: brief,
          onChange: function (e) { setBrief(e.target.value); },
        }),
        h("textarea", {
          className: "sl-input", rows: 2, style: { marginTop: 8 },
          placeholder: "The winning ad you're cloning — filled automatically from 🪄 Use in Ads Lab, or describe it (layout, text, vibe)…",
          value: adContext,
          onChange: function (e) { setAdContext(e.target.value); },
        }),
        h("div", { style: { display: "flex", gap: 10, marginTop: 10,
                            flexWrap: "wrap" } },
          h(UploadSlot, { label: "📷 Source image — your portrait / product",
            value: source && source.name,
            onUploaded: function (id, name) { setSource({ id: id, name: name }); },
            onError: setErr }),
          h(UploadSlot, { label: "🖼 Style reference — winning ad screenshot",
            value: styleRef ? styleRef.name
              : (adStyle ? "creative from the selected ad" : null),
            onUploaded: function (id, name) { setStyleRef({ id: id, name: name }); },
            onError: setErr })),
        adStyle && !styleRef
          ? h("div", { style: { display: "flex", gap: 10,
              alignItems: "center", marginTop: 8 } },
              h("img", { src: adStyle, alt: "", style: { width: 54,
                  height: 54, objectFit: "cover", borderRadius: 8,
                  border: "1px solid var(--color-border, #2b2b44)" } }),
              h("span", { className: "sl-note" },
                "The selected ad's creative rides along as the style " +
                "reference — upload your own to override it."),
              h("button", { className: "sl-btn", style: { fontSize: 11 },
                  onClick: function () { setAdStyle(""); } }, "✕"))
          : null,
        h("div", { className: "sl-note", style: { marginTop: 8 } },
          useKie
            ? "Reference images are hosted briefly on imgBB (auto-deleted " +
              "after ~30 minutes) so the generator can fetch them — KIE " +
              "takes URLs only."
            : "Reference images go straight to the instance's image model " +
              "— no hosting or extra keys needed."),
        h("div", { style: { display: "flex", gap: 10, alignItems: "center",
                            marginTop: 10, flexWrap: "wrap" } },
          h("button", { className: "sl-btn sl-btn-primary",
              disabled: busy || jobRunning, onClick: generate },
            (busy || jobRunning)
              ? h(React.Fragment, null,
                  h("span", { className: "sl-spin",
                      style: { marginRight: 6 } }, "◐"),
                  jobRunning ? "Planning variants…" : "Submitting…")
              : "✨ Generate " + (variants > 1
                  ? variants + " variants" : "the ad")),
          jobRunning
            ? h("span", { className: "sl-note" },
                "runs on the server — safe to leave or refresh the page")
            : null,
          h("span", { className: "sl-note" }, "variants"),
          h("select", { className: "sl-input", style: { width: "auto" },
              value: String(variants),
              title: "Each variant is its own distinct generation (and its " +
                "own KIE charge) — a different angle on headline, " +
                "composition, or mood",
              onChange: function (e) { setVariants(Number(e.target.value)); } },
            [1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30, 40, 50].map(function (n) {
              return h("option", { key: n, value: String(n) }, n);
            }))),
        !useKie && ib.hermes && !ib.hermes.canEdit
          ? h("div", { className: "sl-note", style: { marginTop: 8 } },
              "⚠ This image model is text-to-image only — source and " +
              "style images won't be applied. Switch the generator to " +
              "KIE.ai for style cloning.")
          : null,
        useKie && (!st.keys.kie || !st.keys.imgbb)
          ? h("div", { className: "sl-note", style: { marginTop: 8 } },
              (!st.keys.kie ? "Connect KIE above to generate. " : "") +
              (!st.keys.imgbb
                ? "Connect imgBB above to host your uploaded images " +
                  "(the ad's own creative works as a style ref without it)."
                : ""))
          : null,
        err ? h("div", { className: "sl-err" }, err) : null,
        !jobRunning && job.error
          ? h("div", { className: "sl-err" },
              "last generation failed: " + job.error)
          : null),

      h(AdvancedStudio, { st: st, onState: props.onState }),
      metaMod
        ? h("div", { className: "sl-modal", onClick: function (e) {
              if (e.target === e.currentTarget) setMetaMod(false);
            } },
            h("div", { className: "sl-modal-box" },
              h("div", { style: { fontWeight: 800, fontSize: 15,
                  marginBottom: 6 } },
                "📣 Publish to Meta — PAUSED drafts"),
              h("div", { className: "sl-note",
                  style: { marginBottom: 10 } },
                "One ad per ticked creative, created PAUSED in the ad " +
                "set you pick — review and launch in Ads Manager. Post " +
                "copy variants ride along as the ad's text options."),
              adsets === "loading"
                ? h("div", { className: "sl-note" }, "Loading ad sets…")
                : h("select", { className: "sl-input", value: adsetId,
                    onChange: function (e) { setAdsetId(e.target.value); } },
                    [h("option", { key: "", value: "" },
                      "— pick the target ad set —")]
                      .concat((adsets || []).map(function (a) {
                        return h("option", { key: a.id, value: a.id },
                          (a.campaign ? a.campaign + " › " : "") + a.name +
                          " (" + a.status + ")");
                      }))),
              h("input", { className: "sl-input",
                  style: { marginTop: 8 },
                  placeholder: "Destination link (https://…)",
                  value: metaLink,
                  onChange: function (e) { setMetaLink(e.target.value); } }),
              h("select", { className: "sl-input",
                  style: { marginTop: 8, width: "auto" }, value: metaCta,
                  onChange: function (e) { setMetaCta(e.target.value); } },
                ["LEARN_MORE", "SHOP_NOW", "SIGN_UP", "SUBSCRIBE",
                 "GET_OFFER", "CONTACT_US", "DOWNLOAD", "APPLY_NOW"]
                  .map(function (c) {
                    return h("option", { key: c, value: c },
                      c.replace("_", " ")); })),
              Array.isArray(metaDone)
                ? h("div", { style: { marginTop: 10, fontSize: 12.5,
                    color: "var(--color-primary, #14b8a6)" } },
                    "✓ " + metaDone.length + " paused ad(s) created — " +
                    "find them in Ads Manager.")
                : (metaDone
                    ? h("div", { className: "sl-err",
                        style: { marginTop: 8 } }, metaDone)
                    : null),
              h("div", { className: "sl-modal-row" },
                h("button", { className: "sl-btn",
                    onClick: function () { setMetaMod(false); } }, "Close"),
                h("button", { className: "sl-btn sl-btn-primary",
                    disabled: metaBusy || !adsetId ||
                      !/^https?:\/\//.test(metaLink),
                    onClick: runMetaPublish },
                  metaBusy
                    ? h(React.Fragment, null,
                        h("span", { className: "sl-spin",
                            style: { marginRight: 6 } }, "◐"),
                        "Publishing…")
                    : "📣 Create paused ads"))))
        : null,
      pages !== null
        ? h("div", { className: "sl-modal", onClick: function (e) {
              if (e.target === e.currentTarget) setPages(null);
            } },
            h("div", { className: "sl-modal-box" },
              h("div", { style: { fontWeight: 800, fontSize: 15,
                  marginBottom: 10 } }, "🌐 Published surge.sh pages"),
              pages === "loading"
                ? h("div", { className: "sl-note" }, "Loading…")
                : pages.length === 0
                  ? h("div", { className: "sl-note" },
                      "Nothing published yet.")
                  : pages.map(function (p) {
                      return h("div", { key: p.domain,
                          className: "sl-copytake",
                          style: { alignItems: "center" } },
                        h("a", { className: "sl-link", href: p.url,
                            target: "_blank", rel: "noreferrer",
                            style: { flex: 1, wordBreak: "break-all" } },
                          p.domain),
                        p.timeAgo
                          ? h("span", { className: "sl-note",
                              style: { flexShrink: 0 } }, p.timeAgo)
                          : null,
                        h("button", { className: "sl-btn",
                            style: { fontSize: 11, padding: "2px 8px" },
                            title: "Copy the page URL",
                            onClick: function () {
                              try {
                                navigator.clipboard.writeText(p.url);
                              } catch (e2) {}
                            } }, "⧉ copy"));
                    }),
              h("div", { className: "sl-modal-row" },
                h("button", { className: "sl-btn",
                    onClick: function () { setPages(null); } }, "Close"))))
        : null,
      h("div", { style: { fontWeight: 800, margin: "4px 0 10px" } },
        "Your ad creatives",
        h("span", { className: "sl-note", style: { fontWeight: 400,
            marginLeft: 8 } }, adsCreations.length + " creative(s)"),
        (function () {
          var gen = adsCreations.filter(function (c) {
            return c.status === "generating";
          }).length;
          return gen
            ? h("span", { style: { marginLeft: 10, fontWeight: 700,
                  fontSize: 12.5,
                  color: "var(--color-primary, #14b8a6)" } },
                h("span", { className: "sl-spin",
                    style: { marginRight: 5 } }, "◐"),
                gen + " in progress")
            : null;
        })(),
        h("span", { style: { float: "right", display: "inline-flex",
            gap: 8, fontWeight: 400 } },
          (function () {
            var ready = adsCreations.filter(function (c) {
              return c.status === "ready";
            });
            if (!ready.length) return null;
            var allOn = ready.every(function (c) { return sel[c.id]; });
            return h("button", { className: "sl-btn",
                style: { fontSize: 12 },
                title: allOn ? "Untick every ad"
                             : "Tick every ready ad for the pack",
                onClick: function () {
                  var next = {};
                  if (!allOn) {
                    ready.forEach(function (c) { next[c.id] = true; });
                  }
                  setSel(next);
                } },
              allOn ? "☐ Select none" : "☑ Select all");
          })(),
          h("button", {
              className: "sl-tag",
              style: st.keys.surge
                ? { color: "var(--color-primary, #14b8a6)",
                    borderColor: "color-mix(in srgb, var(--color-primary, #14b8a6) 60%, transparent)",
                    cursor: "pointer", fontSize: 11.5 }
                : { cursor: "pointer", fontSize: 11.5 },
              title: st.keys.surge
                ? "surge.sh connected — click to switch accounts"
                : "Create / sign in to your surge.sh account",
              onClick: function () { setShowConnect("surge"); },
            }, st.keys.surge ? "✓ surge connected" : "🔗 Connect surge"),
          h("button", { className: "sl-btn", style: { fontSize: 12 },
              disabled: pubBusy,
              title: st.keys.surge
                ? "Publish the ticked ads as a shareable page for your editor"
                : "Connect your surge.sh account first",
              onClick: publishSurge },
            pubBusy
              ? h(React.Fragment, null,
                  h("span", { className: "sl-spin",
                      style: { marginRight: 5 } }, "◐"), "Publishing…")
              : "▲ Publish on surge.sh"),
          h("button", { className: "sl-btn", style: { fontSize: 12 },
              title: "Published ad-pack pages, with copy-link buttons",
              onClick: loadPages }, "☰ List surge.sh pages"),
          h("button", {
              className: "sl-tag",
              style: st.keys.metaAds
                ? { color: "var(--color-primary, #14b8a6)",
                    borderColor: "color-mix(in srgb, var(--color-primary, #14b8a6) 60%, transparent)",
                    cursor: "pointer", fontSize: 11.5 }
                : { cursor: "pointer", fontSize: 11.5 },
              title: st.keys.metaAds
                ? "Meta Ads connected — click to update credentials"
                : "Connect a Meta ads account (token + account + page)",
              onClick: function () { setShowConnect("metaads"); },
            }, st.keys.metaAds ? "✓ Meta Ads" : "🔗 Connect Meta Ads"),
          h("button", { className: "sl-btn", style: { fontSize: 12 },
              title: "Create the ticked creatives as PAUSED draft ads in " +
                "Ads Manager — nothing spends until you launch them",
              onClick: openMetaPublish }, "📣 Publish to Meta (paused)"))),
      pubDone
        ? h("div", { className: "sl-card", style: { display: "flex",
              gap: 10, alignItems: "center" } },
            h("span", null, "🌐 Published: "),
            h("a", { className: "sl-link", href: pubDone.url,
                target: "_blank", rel: "noreferrer",
                style: { flex: 1, wordBreak: "break-all" } }, pubDone.url),
            h("button", { className: "sl-btn",
                style: { fontSize: 11, padding: "2px 8px" },
                onClick: function () {
                  try { navigator.clipboard.writeText(pubDone.url); }
                  catch (e2) {}
                } }, "⧉ copy"))
        : null,
      adsCreations.length === 0
        ? h("div", { className: "sl-card sl-note" },
            "Nothing yet — describe your offer above and hit ✨.")
        : adsCreations.map(function (c) {
            var isOpen = open === c.id;
            return h("div", { key: c.id, className: "sl-card sl-creation" },
              h("div", { className: "sl-creation-head",
                  onClick: function () {
                    setOpen(isOpen ? null : c.id);
                    if (!isOpen) loadContent(c.id);
                  } },
                c.status === "ready" && c.kind === "image-ad"
                  ? h("input", { type: "checkbox",
                      checked: !!sel[c.id],
                      title: "Include in the surge.sh ad pack",
                      style: { accentColor: "var(--color-primary, #14b8a6)",
                               cursor: "pointer" },
                      onClick: function (e) { e.stopPropagation(); },
                      onChange: function () { toggleSel(c.id); } })
                  : null,
                h("span", { className: "sl-chev" + (isOpen ? " sl-chev-open" : "") }, "▸"),
                h("span", { style: { fontWeight: 700, flex: 1 } }, c.title),
                c.status === "generating"
                  ? h("span", { className: "sl-busy" },
                      h("span", { className: "sl-spin" }, "◐"), " generating")
                  : c.status === "failed"
                    ? h("span", { className: "sl-chip", style: { color: "#f87171" } },
                        "failed")
                    : h("span", { className: "sl-chip sl-active" }, "ready"),
                c.resultUrl
                  ? h(React.Fragment, null,
                      h("a", { className: "sl-link", href: c.resultUrl,
                          target: "_blank", rel: "noreferrer",
                          onClick: function (e) { e.stopPropagation(); } },
                          "⬇ Open / download"),
                      h("button", { className: "sl-btn",
                          style: { fontSize: 12 },
                          title: "Edit this image — your instruction runs " +
                            "against this exact render",
                          onClick: function (e) {
                            e.stopPropagation();
                            setIterText(""); setIterN(1); setIterFor(c);
                          } }, "↻ Iterate"))
                  : null,
                h("button", { className: "sl-btn", style: { fontSize: 12 },
                    onClick: function (e) { e.stopPropagation(); remove(c.id); } },
                  "🗑"),
                h("span", { className: "sl-note" }, fmtWhen(c.createdAt))),
              c.status === "failed" && c.error
                ? h("div", { className: "sl-err" }, c.error) : null,
              c.status === "ready" && c.error
                ? h("div", { style: { color: "#f59e0b", fontSize: 12,
                    padding: "0 4px" } }, "⚠ " + c.error)
                : null,
              c.kind === "pipeline" && c.steps
                ? h("div", { style: { marginTop: 8 } },
                    c.steps.map(function (sp) {
                      return h("div", { key: sp.id,
                          className: "sl-copytake",
                          style: { fontSize: 11.5 } },
                        h("span", { className: "sl-note",
                            style: { flexShrink: 0 } },
                          sp.state === "done" ? "✓" : "◐"),
                        h("span", { style: { flex: 1 } }, sp.id),
                        sp.url
                          ? h("a", { className: "sl-link", href: sp.url,
                              target: "_blank", rel: "noreferrer" }, "view")
                          : null);
                    }),
                    c.status === "ready" && c.steps.some(function (sp) {
                      return sp.state === "done" && sp.url;
                    }) && c.title.indexOf("Character sheet") < 0
                      ? h("button", { className: "sl-btn",
                          style: { fontSize: 12, marginTop: 6 },
                          title: "Seedance image-to-video on every " +
                            "finished beat — one clip per beat",
                          onClick: function () {
                            postJSON("/advanced/animate", { id: c.id })
                              .then(function (r) { props.onState(r.state); })
                              .catch(function (e) {
                                setErr(String((e && e.message) || e));
                              });
                          } }, "🎞 Animate beats (Seedance)")
                      : null)
                : null,
              c.resultUrl && c.kind === "video-ad"
                ? h("video", { className: "sl-result-img",
                    style: { maxWidth: 460, width: "100%", marginTop: 10 },
                    src: c.resultUrl, controls: true, preload: "metadata" })
                : null,
              c.resultUrl && c.kind !== "video-ad" && c.kind !== "pipeline"
                ? h("div", { style: { display: "flex", gap: 14,
                      flexWrap: "wrap", alignItems: "flex-start",
                      marginTop: 10 } },
                    h("img", { className: "sl-result-img",
                        style: { maxWidth: 380, flex: "0 1 380px" },
                        src: c.resultUrl, alt: c.title }),
                    (c.postCopy || []).length
                      ? (function () {
                          var sel = Math.min(postSel[c.id] || 0,
                                             c.postCopy.length - 1);
                          var p = c.postCopy[sel] || {};
                          var full = [p.hook, p.content, p.cta]
                            .filter(Boolean).join("\n\n");
                          return h("div", { style: { flex: "1 1 260px",
                              minWidth: 230 } },
                            h("div", { style: { fontWeight: 800,
                                fontSize: 13, marginBottom: 6 } },
                              "Post copy",
                              h("span", { className: "sl-note",
                                  style: { fontWeight: 400, marginLeft: 6 } },
                                "runs with the ad")),
                            h("div", { style: { display: "flex", gap: 6,
                                marginBottom: 8 } },
                              c.postCopy.map(function (_, j) {
                                var on = j === sel;
                                return h("button", { key: j,
                                    className: "sl-tag",
                                    style: on
                                      ? { color: "var(--color-primary, #14b8a6)",
                                          borderColor: "color-mix(in srgb, var(--color-primary, #14b8a6) 60%, transparent)",
                                          cursor: "pointer" }
                                      : { cursor: "pointer" },
                                    onClick: function () {
                                      var next = {};
                                      Object.keys(postSel).forEach(
                                        function (k) { next[k] = postSel[k]; });
                                      next[c.id] = j;
                                      setPostSel(next);
                                    } }, "Variant " + (j + 1));
                              }),
                              h("button", { className: "sl-btn",
                                  style: { fontSize: 11, padding: "2px 8px",
                                           marginLeft: "auto" },
                                  title: "Copy this variant (hook + content + CTA)",
                                  onClick: function () {
                                    try {
                                      navigator.clipboard.writeText(full);
                                    } catch (e2) {}
                                  } }, "⧉ Copy")),
                            p.hook
                              ? h("div", { className: "sl-copytake" },
                                  h("span", { className: "sl-note",
                                      style: { flexShrink: 0 } }, "Hook"),
                                  h("span", { style: { flex: 1 } }, p.hook))
                              : null,
                            p.content
                              ? h("div", { className: "sl-copytake" },
                                  h("span", { className: "sl-note",
                                      style: { flexShrink: 0 } }, "Content"),
                                  h("span", { style: { flex: 1,
                                      whiteSpace: "pre-wrap" } }, p.content))
                              : null,
                            p.cta
                              ? h("div", { className: "sl-copytake" },
                                  h("span", { className: "sl-note",
                                      style: { flexShrink: 0 } }, "CTA"),
                                  h("span", { style: { flex: 1 } }, p.cta))
                              : null);
                        })()
                      : (c.copyTakes || []).length
                        ? h("div", { style: { flex: "1 1 240px",
                              minWidth: 220 } },
                            h("div", { style: { fontWeight: 800,
                                fontSize: 13, marginBottom: 6 } },
                              "Ad copy takes"),
                            c.copyTakes.map(function (t, j) {
                              return h("div", { key: j,
                                  className: "sl-copytake" },
                                h("span", { className: "sl-note",
                                    style: { flexShrink: 0 } }, (j + 1) + "."),
                                h("span", { style: { flex: 1 } }, t),
                                h("button", { className: "sl-btn",
                                    style: { fontSize: 11,
                                             padding: "2px 8px" },
                                    title: "Copy this take",
                                    onClick: function () {
                                      try {
                                        navigator.clipboard.writeText(t);
                                      } catch (e2) {}
                                    } }, "⧉"));
                            }))
                        : null)
                : null,
              c.status !== "generating"
                ? h("div", { className: "sl-creation-head",
                    style: { marginTop: 8, fontSize: 12.5 },
                    onClick: function () {
                      setOpen(isOpen ? null : c.id);
                      if (!isOpen) loadContent(c.id);
                    } },
                    h("span", { className: "sl-chev" +
                        (isOpen ? " sl-chev-open" : "") }, "▸"),
                    h("span", { className: "sl-note" },
                      "Details — notes & generation prompt"))
                : null,
              isOpen
                ? h("pre", { className: "sl-md" }, contents[c.id] || "Loading…")
                : null);
          }));
  }

  // -------------------------------------------------------------------------
  // Page
  // -------------------------------------------------------------------------
  var TABS = [
    ["research", "Shorts Research"],
    ["content", "Shorts Lab"],
    ["adsresearch", "Ads Research"],
    ["adslab", "Ads Lab"],
  ];

  function ShortsLabPage() {
    var stSt = useState(null);
    var st = stSt[0], setSt = stSt[1];
    var errSt = useState(null);
    var err = errSt[0], setErr = errSt[1];
    var tabSt = useState(function () {
      try { return localStorage.getItem("sl-tab") || "research"; }
      catch (e) { return "research"; }
    });
    var tab = tabSt[0], setTab = tabSt[1];
    var draftSt = useState("");
    var draftBrief = draftSt[0], setDraftBrief = draftSt[1];
    var adCtxSt = useState("");
    var adContext = adCtxSt[0], setAdContext = adCtxSt[1];
    var adStyleSt = useState("");
    var adStyleUrl = adStyleSt[0], setAdStyleUrl = adStyleSt[1];

    function pickTab(t) {
      setTab(t);
      try { localStorage.setItem("sl-tab", t); } catch (e) {}
    }

    var refresh = useCallback(function () {
      return api("/state")
        .then(function (d) { setSt(d); setErr(null); })
        .catch(function (e) { setErr(String((e && e.message) || e)); });
    }, []);
    useEffect(function () { refresh(); }, [refresh]);

    // while a sync runs, keep the page fresh
    var syncing = !!(st && ((st.shortsSync || {}).running ||
                            (st.adsSync || {}).running ||
                            (st.adlabJob || {}).running));
    useEffect(function () {
      if (!syncing) return undefined;
      var id = window.setInterval(refresh, 5000);
      return function () { window.clearInterval(id); };
    }, [refresh, syncing]);

    // poll generating creations (KIE tasks are async)
    var generating = (st && st.creations || []).filter(function (c) {
      return c.status === "generating";
    }).map(function (c) { return c.id; });
    var genKey = generating.join(",");
    useEffect(function () {
      if (!genKey) return undefined;
      var id = window.setInterval(function () {
        genKey.split(",").forEach(function (cid) {
          postJSON("/creations/check", { id: Number(cid) })
            .then(function (r) { setSt(r.state); })
            .catch(function () {});
        });
      }, 8000);
      return function () { window.clearInterval(id); };
    }, [genKey]);

    if (!st) {
      return h("div", { className: "sl-page" },
        h("div", { style: { color: MUTED, padding: 40 } }, err || "Loading…"));
    }

    return h("div", { className: "sl-page" },
      h("div", { className: "sl-inner" },
        h("div", { style: { marginBottom: 14 } },
          h("div", { style: { fontSize: 13, letterSpacing: 1.5, color: MUTED,
                              textTransform: "uppercase" } },
            "AI Cyber Value Creator™"),
          h("h1", { style: { fontSize: 30, margin: "4px 0 6px",
                             fontWeight: 800 } },
            "⚡ Short Form")),
        h("div", { className: "sl-tabs" },
          TABS.map(function (t) {
            return h("button", {
              key: t[0],
              className: "sl-pagetab" + (tab === t[0] ? " sl-pagetab-active" : ""),
              onClick: function () { pickTab(t[0]); },
            }, t[1]);
          }),
          h("span", { style: { flex: 1 } }),
          h("button", {
              className: "sl-tab" + (st.autoSync ? " sl-tab-on" : ""),
              style: { fontSize: 13.5, padding: "8px 18px",
                       alignSelf: "center", marginBottom: 4 },
              title: "Background sync of monitored ads and tracked " +
                "competitor shorts. Adjust the schedule on the Cron tab.",
              onClick: function () {
                postJSON("/autosync", { enabled: !st.autoSync })
                  .then(function (r) { setSt(r.state); })
                  .catch(function () {});
              },
            }, "⏰ Auto-sync (twice a day) " +
               (st.autoSync ? "on" : "off"))),
        err ? h("div", { className: "sl-err" }, err) : null,
        tab === "research"
          ? h(ShortsResearchTab, { st: st, onState: setSt,
              onDraft: function (o) { setDraftBrief(o); pickTab("content"); } })
          : tab === "content"
            ? h(ShortsContentTab, { st: st, onState: setSt,
                draftBrief: draftBrief })
            : tab === "adsresearch"
              ? h(AdsResearchTab, { st: st, onState: setSt,
                  onUseAd: function (payload) {
                    setAdContext(payload.context || "");
                    setAdStyleUrl(payload.styleImage || "");
                    pickTab("adslab");
                  } })
              : h(AdLabTabWrap, { st: st, onState: setSt,
                  adContext: adContext, adStyleUrl: adStyleUrl })));
  }

  window.__HERMES_PLUGINS__.register("shorts-lab", ShortsLabPage);
})();
