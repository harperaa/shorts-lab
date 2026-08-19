/**
 * Embeddable Remotion Player for the Site Video tab.
 *
 * Built by scripts/build-player.mjs into the dashboard bundle as
 * sv-player.js (self-contained IIFE: React + @remotion/player + the
 * SiteDescriber composition). The dashboard lazy-loads it and calls:
 *
 *   window.__SITE_VIDEO_PLAYER__.mount(el, props)   // props = plan.json
 *   window.__SITE_VIDEO_PLAYER__.unmount(el)
 */
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { Player } from "@remotion/player";
import { SiteDescriber, FPS, FORMATS } from "./SiteDescriber";

const INTRO = 2.5;
const OUTRO = 4;

type PlanProps = React.ComponentProps<typeof SiteDescriber>;

const roots = new WeakMap<HTMLElement, Root>();

function durationInFrames(props: PlanProps): number {
  const body = (props.scenes ?? []).reduce(
    (sum, s) => sum + (s.seconds ?? 5),
    0,
  );
  return Math.max(1, Math.round((INTRO + body + OUTRO) * FPS));
}

function mount(el: HTMLElement, props: PlanProps): void {
  const fmt = FORMATS[props.format ?? "vertical"] ?? FORMATS.vertical;
  let root = roots.get(el);
  if (!root) {
    root = createRoot(el);
    roots.set(el, root);
  }
  root.render(
    <Player
      component={SiteDescriber}
      inputProps={props}
      durationInFrames={durationInFrames(props)}
      compositionWidth={fmt.width}
      compositionHeight={fmt.height}
      fps={FPS}
      controls
      loop
      style={{ width: "100%", height: "100%" }}
      acknowledgeRemotionLicense
    />,
  );
}

function unmount(el: HTMLElement): void {
  const root = roots.get(el);
  if (root) {
    root.unmount();
    roots.delete(el);
  }
}

declare global {
  interface Window {
    __SITE_VIDEO_PLAYER__?: { mount: typeof mount; unmount: typeof unmount };
  }
}

window.__SITE_VIDEO_PLAYER__ = { mount, unmount };
