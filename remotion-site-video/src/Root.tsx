import React from "react";
import { Composition } from "remotion";
import {
  SiteDescriber,
  siteDescriberSchema,
  FPS,
  FORMATS,
} from "./SiteDescriber";

const DEFAULTS = {
  title: "Site Tour",
  url: "https://example.com",
  accent: "#14b8a6",
  format: "vertical" as const,
  screenshot: "",
  pageWidth: 1440,
  pageHeight: 4000,
  scenes: [
    {
      headline: "Welcome",
      caption: "A quick tour of the site.",
      seconds: 5,
      region: { x: 0, y: 0, w: 1440, h: 900 },
    },
  ],
  outro: { headline: "See it live", caption: "Visit the site today." },
};

export const Root: React.FC = () => {
  return (
    <Composition
      id="SiteDescriber"
      component={SiteDescriber}
      schema={siteDescriberSchema}
      width={FORMATS.vertical.width}
      height={FORMATS.vertical.height}
      fps={FPS}
      durationInFrames={60 * FPS}
      defaultProps={DEFAULTS}
      calculateMetadata={({ props }) => {
        const INTRO = 2.5;
        const OUTRO = 4;
        const body = (props.scenes ?? []).reduce(
          (sum: number, s: { seconds?: number }) => sum + (s.seconds ?? 5),
          0,
        );
        const fmt =
          FORMATS[(props as { format?: string }).format ?? "vertical"] ??
          FORMATS.vertical;
        return {
          width: fmt.width,
          height: fmt.height,
          durationInFrames: Math.max(
            1,
            Math.round((INTRO + body + OUTRO) * FPS),
          ),
        };
      }}
    />
  );
};
