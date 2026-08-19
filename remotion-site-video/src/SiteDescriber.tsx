import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  Easing,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { z } from "zod";

export const FPS = 30;
const INTRO_SEC = 2.5;
const OUTRO_SEC = 4;
const TRANSITION_SEC = 0.8; // camera glide between scenes

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

export const siteDescriberSchema = z.object({
  title: z.string(),
  url: z.string(),
  accent: z.string().default("#14b8a6"),
  screenshot: z.string(), // public/ filename (staticFile) or http(s) URL
  pageWidth: z.number().min(1),
  pageHeight: z.number().min(1),
  scenes: z.array(sceneSchema).min(1),
  outro: z
    .object({ headline: z.string(), caption: z.string() })
    .default({ headline: "See it live", caption: "" }),
});

type Props = z.infer<typeof siteDescriberSchema>;
type Region = z.infer<typeof regionSchema>;

// Camera transform that frames `region` of the page inside the viewport,
// slightly zoomed for a comfortable margin.
function cameraFor(
  region: Region,
  viewportW: number,
  viewportH: number,
): { scale: number; tx: number; ty: number } {
  const margin = 0.92;
  const scale = Math.min(
    (viewportW / region.w) * margin,
    (viewportH / region.h) * margin,
    3.5, // never zoom past 3.5x — screenshots get blurry
  );
  const cx = region.x + region.w / 2;
  const cy = region.y + region.h / 2;
  return {
    scale,
    tx: viewportW / 2 - cx * scale,
    ty: viewportH / 2 - cy * scale,
  };
}

export const SiteDescriber: React.FC<Props> = (props) => {
  const frame = useCurrentFrame();
  const { width, height, durationInFrames } = useVideoConfig();
  const t = frame / FPS;

  const introEnd = INTRO_SEC;
  const scenes = props.scenes;
  // Scene time windows (absolute seconds).
  const starts: number[] = [];
  let acc = introEnd;
  for (const s of scenes) {
    starts.push(acc);
    acc += s.seconds;
  }
  const outroStart = acc;

  // ---- camera: which scene are we in, and where is the camera? -----------
  const viewportPad = 90;
  const vw = width - viewportPad * 2;
  const vh = height - viewportPad * 2 - 120; // caption band at the bottom
  let cam = cameraFor(scenes[0].region, vw, vh);
  let activeIdx = 0;
  if (t >= introEnd && t < outroStart) {
    for (let i = 0; i < scenes.length; i++) {
      const s0 = starts[i];
      const s1 = s0 + scenes[i].seconds;
      if (t >= s0 && t < s1) {
        activeIdx = i;
        const from = cameraFor(
          scenes[Math.max(0, i - 1)].region,
          vw,
          vh,
        );
        const to = cameraFor(scenes[i].region, vw, vh);
        const gl = interpolate(t, [s0, s0 + TRANSITION_SEC], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.bezier(0.33, 1, 0.68, 1),
        });
        // Ken-Burns drift for the rest of the scene: slow 3% zoom-in.
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
    cam = cameraFor(scenes[scenes.length - 1].region, vw, vh);
    activeIdx = scenes.length - 1;
  }

  const scene = scenes[activeIdx];
  const sceneStart = starts[activeIdx] ?? introEnd;

  // ---- intro / outro opacities -------------------------------------------
  const introOpacity = interpolate(t, [0, 0.4, INTRO_SEC - 0.5, INTRO_SEC], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
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

  // caption text reveal per scene
  const capReveal = interpolate(t, [sceneStart + 0.2, sceneStart + 0.9], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const progress = interpolate(frame, [0, durationInFrames - 1], [0, 1]);

  const chrome = 46; // fake browser chrome height

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
          height: 8,
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
          {/* fake browser chrome */}
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
                marginLeft: 14,
                padding: "6px 16px",
                borderRadius: 8,
                background: "rgba(255,255,255,0.08)",
                color: "rgba(255,255,255,0.75)",
                fontSize: 17,
              }}
            >
              {props.url}
            </div>
          </div>
          {/* the page, camera-transformed */}
          <div style={{ position: "relative", width: vw, height: vh, overflow: "hidden" }}>
            <Img
              src={
                props.screenshot.startsWith("http")
                  ? props.screenshot
                  : staticFile(props.screenshot)
              }
              style={{
                position: "absolute",
                width: props.pageWidth,
                transformOrigin: "0 0",
                transform: `translate(${cam.tx}px, ${cam.ty}px) scale(${cam.scale})`,
              }}
            />
          </div>
        </div>

        {/* caption band */}
        <div
          style={{
            position: "absolute",
            left: viewportPad,
            right: viewportPad,
            bottom: 26,
            display: "flex",
            alignItems: "center",
            gap: 18,
            opacity: capReveal,
            transform: `translateY(${(1 - capReveal) * 14}px)`,
          }}
        >
          {scene.headline ? (
            <div
              style={{
                flexShrink: 0,
                padding: "10px 20px",
                borderRadius: 999,
                background: props.accent,
                color: "#04211c",
                fontWeight: 800,
                fontSize: 26,
              }}
            >
              {scene.headline}
            </div>
          ) : null}
          <div style={{ color: "#eef2f8", fontSize: 30, fontWeight: 600, lineHeight: 1.25 }}>
            {scene.caption}
          </div>
        </div>
      </div>

      {/* ---- intro card ---- */}
      <AbsoluteFill
        style={{
          opacity: introOpacity,
          justifyContent: "center",
          alignItems: "center",
          zIndex: 30,
        }}
      >
        <div style={{ textAlign: "center" }}>
          <div style={{ color: props.accent, fontSize: 30, letterSpacing: 6, fontWeight: 700 }}>
            SITE TOUR
          </div>
          <div style={{ color: "#f3f6fb", fontSize: 84, fontWeight: 900, margin: "18px 0 10px" }}>
            {props.title}
          </div>
          <div style={{ color: "rgba(255,255,255,0.65)", fontSize: 32 }}>{props.url}</div>
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
        }}
      >
        <div style={{ textAlign: "center", maxWidth: 1200 }}>
          <div style={{ color: "#f3f6fb", fontSize: 72, fontWeight: 900 }}>
            {props.outro.headline}
          </div>
          {props.outro.caption ? (
            <div style={{ color: "rgba(255,255,255,0.75)", fontSize: 34, marginTop: 16 }}>
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
              fontSize: 34,
              fontWeight: 800,
            }}
          >
            {props.url}
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
