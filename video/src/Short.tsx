import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  OffthreadVideo,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from "remotion";
import { z } from "zod";
import { loadFont } from "@remotion/google-fonts/Montserrat";

const { fontFamily } = loadFont("normal", {
  weights: ["400", "700", "800", "900"],
  subsets: ["latin"],
});
const WHITE = "#FDFDFD";
const YELLOW = "#FFD60A";
const GREEN = "#3CF23C";

/** Word timings produced by the TTS engine. */
export const shortSchema = z.object({
  title: z.string(),
  niche: z.string().default("programming"),
  hook: z.string().default(""),
  durationInSeconds: z.number().default(50),
  fps: z.number().default(30),
  words: z.array(
    z.object({ text: z.string(), start: z.number(), end: z.number() })
  ),
  backgrounds: z.array(z.object({ path: z.string(), kind: z.string() })),
  voiceSrc: z.string(),
  musicSrc: z.string().nullable(),
});
export type ShortProps = z.infer<typeof shortSchema>;
type Word = { text: string; start: number; end: number };

const NICHE_TAGS: Record<string, { label: string; accent: string }> = {
  cybersecurity: { label: "CYBER ALERT", accent: "#FF3B30" },
  programming: { label: "DEV NEWS", accent: "#0A84FF" },
  crypto: { label: "CRYPTO PULSE", accent: "#30D158" },
};

/** Rolling 3-word caption window, current word highlighted in accent colour. */
const Captions: React.FC<{ words: Word[]; fps: number }> = ({ words, fps }) => {
  const frame = useCurrentFrame();
  const t = frame / fps;
  let active = 0;
  for (let i = 0; i < words.length; i++) {
    if (t >= words[i].start && t <= words[i].end) {
      active = i;
      break;
    }
    if (t > (words[i].end ?? words[i].start)) {
      active = i;
    }
  }
  const windowStart = Math.max(0, active - 1);
  const windowEnd = Math.min(words.length, windowStart + 3);
  const group = words.slice(windowStart, windowEnd);
  const progress = interpolate(t - words[active].start, [0, words[active].end - words[active].start], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", paddingBottom: 210, alignItems: "center" }}>
      <div
        style={{
          fontFamily,
          fontWeight: 800,
          fontSize: 74,
          lineHeight: 1.15,
          textAlign: "center",
          maxWidth: 980,
          color: WHITE,
          textShadow: "0 4px 18px rgba(0,0,0,0.9), 0 0 0 6px rgba(0,0,0,0.35)",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: "0 24px",
        }}
      >
        {group.map((w, i) => {
          const isActive = windowStart + i === active;
          const scale = isActive ? 1 + 0.06 * progress : 1;
          return (
            <span
              key={`${windowStart + i}`}
              style={{
                color: isActive ? YELLOW : WHITE,
                display: "inline-block",
                transform: `scale(${scale})`,
              }}
            >
              {w.text}
            </span>
          );
        })}
      </div>
      {/* progress bar */}
      <div
        style={{
          marginTop: 46,
          width: 560,
          height: 10,
          borderRadius: 5,
          background: "rgba(255,255,255,0.25)",
        }}
      >
        <div
          style={{
            width: `${(t / (words[words.length - 1]?.end ?? 50)) * 100}%`,
            height: "100%",
            borderRadius: 5,
            background: YELLOW,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};

/** Crossfading full-bleed background clips, with editorial overlay. */
const Backgrounds: React.FC<{ backgrounds: { path: string; kind: string }[]; duration: number }> = ({
  backgrounds,
  duration,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  if (!backgrounds.length) {
    return (
      <AbsoluteFill style={{ background: "linear-gradient(160deg,#0B1026,#1A2342 55%,#101325)" }} />
    );
  }
  const per = duration / backgrounds.length;
  const idx = Math.min(backgrounds.length - 1, Math.floor(t / per));
  const local = t - idx * per;
  const next = (idx + 1) % backgrounds.length;
  const progress = spring({ frame, fps, config: { damping: 200 } });
  void progress;
  const opacity = interpolate(Math.abs(local - per / 2), [per / 2 - 1.2, per / 2], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const renderPiece = (i: number, o: number) => {
    const bg = backgrounds[i % backgrounds.length];
    const src = staticFile(bg.path);
    return bg.kind === "video" ? (
      <OffthreadVideo
        key={i}
        src={src}
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
          opacity: o,
        }}
      />
    ) : (
      <Img
        key={i}
        src={src}
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
          opacity: o,
        }}
      />
    );
  };

  return (
    <AbsoluteFill style={{ background: "#0B1026" }}>
      {renderPiece(idx, 1)}
      {opacity > 0.02 && renderPiece(next, opacity)}
      {/* readability + brand overlay */}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.05) 30%, rgba(0,0,0,0.25) 60%, rgba(0,0,0,0.75) 100%)",
        }}
      />
    </AbsoluteFill>
  );
};

const Headline: React.FC<{ title: string; niche: string }> = ({ title, niche }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const outAt = Math.min(durationInFrames, 9 * fps);
  const opacity = interpolate(frame, [0, 8, outAt - 8, outAt], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const tag = NICHE_TAGS[niche] ?? NICHE_TAGS.programming;
  return (
    <AbsoluteFill style={{ alignItems: "center", opacity, padding: 120 }}>
      <div style={{ marginBottom: 34, fontFamily, fontWeight: 800, fontSize: 30, letterSpacing: 6, color: tag.accent }}>
        {tag.label}
      </div>
      <div
        style={{
          fontFamily,
          fontWeight: 900,
          fontSize: 92,
          lineHeight: 1.06,
          textAlign: "center",
          color: WHITE,
          textShadow: "0 6px 30px rgba(0,0,0,0.95)",
        }}
      >
        {title}
      </div>
    </AbsoluteFill>
  );
};

export const Short: React.FC<ShortProps> = ({
  title,
  niche,
  hook,
  durationInSeconds,
  words,
  backgrounds,
  voiceSrc,
  musicSrc,
  fps,
}) => {
  const { durationInFrames } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: "#0B1026" }}>
      <Backgrounds backgrounds={backgrounds} duration={durationInSeconds} />
      <Headline title={title} niche={niche} />
      <Captions words={words} fps={fps ?? 30} />

      {voiceSrc && <Audio src={staticFile(voiceSrc)} />}
      {musicSrc && <Audio src={staticFile(musicSrc)} volume={0.16} />}
      {hook && (
        <Sequence from={0}>
          <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }} />
        </Sequence>
      )}
      <div style={{ height: durationInFrames }} />
    </AbsoluteFill>
  );
};