import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  interpolate,
  Easing,
  random,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { z } from "zod";

export const FPS = 30;
const INTRO_SEC = 2.5;
const OUTRO_SEC = 4;
const TRANSITION_SEC = 0.8; // camera glide between scenes

export const FORMATS: Record<string, { width: number; height: number }> = {
  vertical: { width: 1080, height: 1920 }, // Shorts/Reels/TikTok — default
  landscape: { width: 1920, height: 1080 }, // YouTube 1080p
  square: { width: 1080, height: 1080 }, // 1:1 feed
  portrait45: { width: 1080, height: 1350 }, // Instagram 4:5
  landscape4k: { width: 3840, height: 2160 }, // 4K 16:9
};

const regionSchema = z.object({
  x: z.number(),
  y: z.number(),
  w: z.number().min(1),
  h: z.number().min(1),
});

const sceneSchema = z.object({
  headline: z.string().optional(),
  caption: z.string(),
  seconds: z.number().min(1).max(30).default(5),
  region: regionSchema,
});

const effectsSchema = z.object({
  transition: z
    .enum(["mix", "flash", "whip", "zoom", "fade", "glide"])
    .default("mix"),
  sfx: z.boolean().default(true),
  particles: z.boolean().default(true),
});

export const siteDescriberSchema = z.object({
  title: z.string(),
  url: z.string(),
  accent: z.string().default("#14b8a6"),
  format: z
    .enum(["vertical", "landscape", "square", "portrait45", "landscape4k"])
    .default("vertical"),
  effects: effectsSchema.default({}),
  // Where sfx audio lives: unset = staticFile (render); the embedded
  // player passes an http base since it has no public/ dir.
  sfxBase: z.string().optional(),
  screenshot: z.string(), // public/ filename (staticFile), blob:, or http(s)
  pageWidth: z.number().min(1),
  pageHeight: z.number().min(1),
  scenes: z.array(sceneSchema).min(1),
  outro: z
    .object({ headline: z.string(), caption: z.string() })
    .default({ headline: "See it live", caption: "" }),
});

type Props = z.infer<typeof siteDescriberSchema>;
type Region = z.infer<typeof regionSchema>;

export function resolveScreenshotSrc(src: string): string {
  return /^(https?:|blob:|data:)/.test(src) ? src : staticFile(src);
}

// Camera transform framing `region` inside the viewport — CLAMPED so the
// page always covers the viewport when it can (no dead gutters; the fix for
// scenes drifting right), centered only when the scaled page is smaller.
export function cameraFor(
  region: Region,
  viewportW: number,
  viewportH: number,
  pageW: number,
  pageH: number,
): { scale: number; tx: number; ty: number } {
  const margin = 0.94;
  // Zoom floor 1.0: the app must always read at 100%+ — a region larger
  // than the viewport gets framed at 100% from its top edge (the camera
  // pans it), never zoomed out into unreadable miniature.
  const scale = Math.max(
    1,
    Math.min(
      (viewportW / region.w) * margin,
      (viewportH / region.h) * margin,
      3.5, // never zoom past 3.5x — screenshots get blurry
    ),
  );
  // Anchor to the region's LEFT edge when it is wider than the viewport at
  // this scale (web content reads from the left), and to its TOP when
  // taller (readers scan from the top); otherwise center.
  const regionWiderThanView = region.w * scale > viewportW;
  const cx = regionWiderThanView
    ? region.x + viewportW / (2 * scale)
    : region.x + region.w / 2;
  const regionTallerThanView = region.h * scale > viewportH;
  const cy = regionTallerThanView
    ? region.y + viewportH / (2 * scale)
    : region.y + region.h / 2;
  let tx = viewportW / 2 - cx * scale;
  let ty = viewportH / 2 - cy * scale;
  const scaledW = pageW * scale;
  const scaledH = pageH * scale;
  if (scaledW >= viewportW) {
    tx = Math.min(0, Math.max(viewportW - scaledW, tx));
  } else {
    tx = (viewportW - scaledW) / 2;
  }
  if (scaledH >= viewportH) {
    ty = Math.min(0, Math.max(viewportH - scaledH, ty));
  } else {
    ty = (viewportH - scaledH) / 2;
  }
  return { scale, tx, ty };
}

export const SiteDescriber: React.FC<Props> = (props) => {
  const frame = useCurrentFrame();
  const { width, height, durationInFrames } = useVideoConfig();
  const t = frame / FPS;
  const vertical = height >= width;
  const k = Math.min(width, height) / 1080; // resolution scale (4K etc.)

  const introEnd = INTRO_SEC;
  const scenes = props.scenes;
  const starts: number[] = [];
  let acc = introEnd;
  for (const s of scenes) {
    starts.push(acc);
    acc += s.seconds;
  }
  const outroStart = acc;

  // ---- layout ------------------------------------------------------------
  const viewportPad = (vertical ? 22 : 60) * k;
  const captionBand = (height > width * 1.4 ? 250 : vertical ? 190 : 110) * k;
  const chrome = (vertical ? 54 : 46) * k;
  const vw = width - viewportPad * 2;
  const vh = height - viewportPad * 2 - captionBand - chrome;

  const camAt = (region: Region) =>
    cameraFor(region, vw, vh, props.pageWidth, props.pageHeight);

  let cam = camAt(scenes[0].region);
  let activeIdx = 0;
  if (t >= introEnd && t < outroStart) {
    for (let i = 0; i < scenes.length; i++) {
      const s0 = starts[i];
      const s1 = s0 + scenes[i].seconds;
      if (t >= s0 && t < s1) {
        activeIdx = i;
        const from = camAt(scenes[Math.max(0, i - 1)].region);
        const to = camAt(scenes[i].region);
        const gl = interpolate(t, [s0, s0 + TRANSITION_SEC], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.bezier(0.33, 1, 0.68, 1),
        });
        // Ken-Burns drift within the scene: gentle 3% zoom-in.
        const drift = interpolate(t, [s0 + TRANSITION_SEC, s1], [1, 1.03], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        cam = {
          scale: (from.scale + (to.scale - from.scale) * gl) * drift,
          tx: from.tx + (to.tx - from.tx) * gl,
          ty: from.ty + (to.ty - from.ty) * gl,
        };
        break;
      }
    }
  } else if (t >= outroStart) {
    cam = camAt(scenes[scenes.length - 1].region);
    activeIdx = scenes.length - 1;
  }

  const scene = scenes[activeIdx];
  const sceneStart = starts[activeIdx] ?? introEnd;
  const effects = props.effects ?? {
    transition: "flash", sfx: true, particles: true,
  };

  // ---- transition overlays at each scene boundary ------------------------
  // flash: quick white pulse; fade: dip to black. Applied around every
  // scene start (and the outro start).
  const boundaries = [...starts, outroStart];
  const kindFor = (i: number): string => {
    if (effects.transition === "mix")
      return ["flash", "whip", "zoom"][i % 3];
    return effects.transition;
  };
  let flashOpacity = 0;
  let fadeOpacity = 0;
  let whipBlur = 0;
  let punchZoom = 0;
  boundaries.forEach((b, i) => {
    const kind = kindFor(i);
    if (kind === "flash") {
      flashOpacity = Math.max(
        flashOpacity,
        interpolate(t, [b - 0.06, b, b + 0.3], [0, 0.8, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        }),
      );
    } else if (kind === "fade") {
      fadeOpacity = Math.max(
        fadeOpacity,
        interpolate(t, [b - 0.35, b, b + 0.35], [0, 0.85, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        }),
      );
    } else if (kind === "whip") {
      whipBlur = Math.max(
        whipBlur,
        interpolate(t, [b - 0.18, b, b + 0.22], [0, 14, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        }),
      );
    } else if (kind === "zoom") {
      punchZoom = Math.max(
        punchZoom,
        interpolate(t, [b - 0.12, b, b + 0.28], [0, 0.06, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        }),
      );
    }
  });

  // Click cursor: during each scene transition a cursor glides to the
  // center of the incoming region (viewport coords) and "clicks" with a
  // ripple — paired with the click sfx.
  let cursor: { x: number; y: number; ripple: number; visible: boolean } = {
    x: 0, y: 0, ripple: 0, visible: false,
  };
  for (let i = 1; i < scenes.length; i++) {
    const b = starts[i];
    if (t >= b - 0.6 && t <= b + 0.5) {
      const toCam = camAt(scenes[i].region);
      const target = {
        x: (scenes[i].region.x + scenes[i].region.w / 2) * toCam.scale + toCam.tx,
        y: Math.min(
          (scenes[i].region.y + scenes[i].region.h / 2) * toCam.scale + toCam.ty,
          vh - 40,
        ),
      };
      const approach = interpolate(t, [b - 0.6, b], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
        easing: Easing.bezier(0.4, 0, 0.2, 1),
      });
      cursor = {
        visible: true,
        x: vw * 0.75 + (target.x - vw * 0.75) * approach,
        y: vh * 0.85 + (target.y - vh * 0.85) * approach,
        ripple: interpolate(t, [b, b + 0.45], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        }),
      };
      break;
    }
  }

  const sfxSrc = (name: string) =>
    props.sfxBase ? props.sfxBase + name : staticFile(name);

  const introOpacity = interpolate(
    t,
    [0, 0.4, INTRO_SEC - 0.5, INTRO_SEC],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const bodyOpacity = interpolate(
    t,
    [INTRO_SEC - 0.3, INTRO_SEC + 0.3, outroStart - 0.3, outroStart + 0.5],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const outroOpacity = interpolate(t, [outroStart, outroStart + 0.6], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const capReveal = interpolate(
    t,
    [sceneStart + 0.2, sceneStart + 0.9],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const progress = interpolate(frame, [0, durationInFrames - 1], [0, 1]);

  const titleSize = (vertical ? 64 : 84) * k;
  const capSize = (vertical ? 40 : 30) * k;
  const headSize = (vertical ? 32 : 26) * k;

  return (
    <AbsoluteFill
      style={{
        background:
          `radial-gradient(1200px 800px at 20% 0%, ${props.accent}33, transparent), ` +
          "linear-gradient(160deg, #0b0f17 0%, #101826 60%, #0b0f17 100%)",
        fontFamily:
          "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif",
      }}
    >
      {/* progress bar */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          height: vertical ? 10 : 8,
          width: `${progress * 100}%`,
          background: props.accent,
          zIndex: 40,
        }}
      />

      {/* ---- body: browser frame + panning screenshot ---- */}
      <div style={{ opacity: bodyOpacity, position: "absolute", inset: 0 }}>
        <div
          style={{
            position: "absolute",
            left: viewportPad,
            top: viewportPad,
            width: vw,
            height: vh + chrome,
            borderRadius: 18,
            overflow: "hidden",
            boxShadow: "0 40px 120px rgba(0,0,0,0.55)",
            border: "1px solid rgba(255,255,255,0.12)",
            background: "#0d1117",
          }}
        >
          <div
            style={{
              height: chrome,
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "0 18px",
              background: "rgba(255,255,255,0.06)",
              borderBottom: "1px solid rgba(255,255,255,0.08)",
            }}
          >
            {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
              <div
                key={c}
                style={{ width: 14, height: 14, borderRadius: 7, background: c }}
              />
            ))}
            <div
              style={{
                marginLeft: 12,
                padding: "6px 16px",
                borderRadius: 8,
                background: "rgba(255,255,255,0.08)",
                color: "rgba(255,255,255,0.75)",
                fontSize: vertical ? 20 : 17,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                maxWidth: vw - 120,
              }}
            >
              {props.url}
            </div>
          </div>
          <div
            style={{
              position: "relative",
              width: vw,
              height: vh,
              overflow: "hidden",
            }}
          >
            <Img
              src={resolveScreenshotSrc(props.screenshot)}
              style={{
                position: "absolute",
                width: props.pageWidth,
                transformOrigin: "0 0",
                transform: `translate(${cam.tx}px, ${cam.ty}px) scale(${
                  cam.scale * (1 + punchZoom)
                })`,
                filter: whipBlur > 0.5 ? `blur(${whipBlur}px)` : undefined,
              }}
            />
            {cursor.visible ? (
              <div
                style={{
                  position: "absolute",
                  left: cursor.x,
                  top: cursor.y,
                  zIndex: 5,
                  pointerEvents: "none",
                }}
              >
                {cursor.ripple > 0 && cursor.ripple < 1 ? (
                  <div
                    style={{
                      position: "absolute",
                      left: -30 * cursor.ripple * k,
                      top: -30 * cursor.ripple * k,
                      width: 60 * cursor.ripple * k,
                      height: 60 * cursor.ripple * k,
                      borderRadius: "50%",
                      border: `${3 * k}px solid ${props.accent}`,
                      opacity: 1 - cursor.ripple,
                    }}
                  />
                ) : null}
                <svg
                  width={30 * k}
                  height={30 * k}
                  viewBox="0 0 24 24"
                  style={{ filter: "drop-shadow(0 2px 6px rgba(0,0,0,0.6))" }}
                >
                  <path
                    d="M5 3l14 8-6 1.5L16.5 19l-3 1.3L10 14l-5 4z"
                    fill="#ffffff"
                    stroke="#0b0f17"
                    strokeWidth="1.4"
                  />
                </svg>
              </div>
            ) : null}
          </div>
        </div>

        {/* caption band — the scene's highlight */}
        <div
          style={{
            position: "absolute",
            left: viewportPad,
            right: viewportPad,
            bottom: vertical ? 90 : 26,
            display: "flex",
            flexDirection: vertical ? "column" : "row",
            alignItems: vertical ? "flex-start" : "center",
            gap: vertical ? 14 : 18,
            opacity: capReveal,
            transform: `translateY(${(1 - capReveal) * 14}px)`,
          }}
        >
          {scene.headline ? (
            <div
              style={{
                flexShrink: 0,
                padding: vertical ? "12px 26px" : "10px 20px",
                borderRadius: 999,
                background: props.accent,
                color: "#04211c",
                fontWeight: 800,
                fontSize: headSize,
              }}
            >
              {scene.headline}
            </div>
          ) : null}
          <div
            style={{
              color: "#eef2f8",
              fontSize: capSize,
              fontWeight: 600,
              lineHeight: 1.3,
              textShadow: "0 2px 12px rgba(0,0,0,0.7)",
            }}
          >
            {scene.caption}
          </div>
        </div>
      </div>

      {/* ---- ambient particles ("smoke") ---- */}
      {effects.particles ? (
        <AbsoluteFill style={{ pointerEvents: "none", zIndex: 20 }}>
          {Array.from({ length: 14 }).map((_, i) => {
            const seed = random(`p${i}`);
            const seed2 = random(`q${i}`);
            const size = 120 + seed * 260;
            const x =
              ((seed2 + t * (0.008 + seed * 0.012)) % 1) * (width + size) -
              size;
            const y =
              ((seed + t * 0.006 * (i % 3 === 0 ? -1 : 1) + 1) % 1) * height;
            const o = 0.05 + 0.06 * Math.sin(t * 0.7 + i);
            return (
              <div
                key={i}
                style={{
                  position: "absolute",
                  left: x,
                  top: y,
                  width: size,
                  height: size,
                  borderRadius: "50%",
                  background: `radial-gradient(circle, ${
                    i % 4 === 0 ? props.accent : "#9fb4d8"
                  }22, transparent 70%)`,
                  filter: "blur(18px)",
                  opacity: Math.max(0, o),
                }}
              />
            );
          })}
        </AbsoluteFill>
      ) : null}

      {/* ---- transition overlays ---- */}
      {flashOpacity > 0 ? (
        <AbsoluteFill
          style={{ background: "#ffffff", opacity: flashOpacity, zIndex: 35 }}
        />
      ) : null}
      {fadeOpacity > 0 ? (
        <AbsoluteFill
          style={{ background: "#04070c", opacity: fadeOpacity, zIndex: 35 }}
        />
      ) : null}

      {/* ---- sfx: whoosh on each scene change, click at intro/outro ---- */}
      {effects.sfx ? (
        <>
          <Sequence from={Math.round((introEnd - 0.1) * FPS)} durationInFrames={20}>
            <Audio src={sfxSrc("sfx-click.wav")} volume={0.7} />
          </Sequence>
          {starts.slice(1).map((s0, i) => (
            <Sequence
              key={i}
              from={Math.round((s0 - 0.12) * FPS)}
              durationInFrames={Math.round(0.5 * FPS)}
            >
              <Audio src={sfxSrc("sfx-whoosh.wav")} volume={0.5} />
            </Sequence>
          ))}
          {starts.slice(1).map((s0, i) => (
            <Sequence
              key={"c" + i}
              from={Math.round(s0 * FPS)}
              durationInFrames={15}
            >
              <Audio src={sfxSrc("sfx-click.wav")} volume={0.8} />
            </Sequence>
          ))}
          <Sequence from={Math.round(outroStart * FPS)} durationInFrames={20}>
            <Audio src={sfxSrc("sfx-click.wav")} volume={0.7} />
          </Sequence>
        </>
      ) : null}

      {/* ---- intro card ---- */}
      <AbsoluteFill
        style={{
          opacity: introOpacity,
          justifyContent: "center",
          alignItems: "center",
          zIndex: 30,
          padding: 60,
        }}
      >
        <div style={{ textAlign: "center" }}>
          <div
            style={{
              color: props.accent,
              fontSize: vertical ? 26 : 30,
              letterSpacing: 6,
              fontWeight: 700,
            }}
          >
            SITE TOUR
          </div>
          <div
            style={{
              color: "#f3f6fb",
              fontSize: titleSize,
              fontWeight: 900,
              margin: "18px 0 10px",
              lineHeight: 1.1,
            }}
          >
            {props.title}
          </div>
          <div
            style={{ color: "rgba(255,255,255,0.65)", fontSize: vertical ? 26 : 32 }}
          >
            {props.url}
          </div>
        </div>
      </AbsoluteFill>

      {/* ---- outro card ---- */}
      <AbsoluteFill
        style={{
          opacity: outroOpacity,
          justifyContent: "center",
          alignItems: "center",
          zIndex: 30,
          background: "rgba(5,8,13,0.82)",
          padding: 60,
        }}
      >
        <div style={{ textAlign: "center", maxWidth: vertical ? 900 : 1200 }}>
          <div
            style={{ color: "#f3f6fb", fontSize: vertical ? 58 : 72, fontWeight: 900 }}
          >
            {props.outro.headline}
          </div>
          {props.outro.caption ? (
            <div
              style={{
                color: "rgba(255,255,255,0.75)",
                fontSize: vertical ? 30 : 34,
                marginTop: 16,
              }}
            >
              {props.outro.caption}
            </div>
          ) : null}
          <div
            style={{
              display: "inline-block",
              marginTop: 30,
              padding: "16px 40px",
              borderRadius: 999,
              background: props.accent,
              color: "#04211c",
              fontSize: vertical ? 28 : 34,
              fontWeight: 800,
              maxWidth: "100%",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {props.url}
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
