import React from "react";
import { Composition } from "remotion";
import { Short, shortSchema, type ShortProps } from "./Short";

const defaultProps: ShortProps = {
  title: "Breaking news",
  niche: "programming",
  hook: "",
  durationInSeconds: 50,
  words: [],
  backgrounds: [],
  voiceSrc: "",
  musicSrc: null,
  fps: 30,
};

export const Root: React.FC = () => {
  return (
    <Composition
      id="Short"
      component={Short}
      durationInFrames={Math.ceil((defaultProps.durationInSeconds ?? 50) * 30)}
      fps={30}
      width={1080}
      height={1920}
      defaultProps={defaultProps}
      schema={shortSchema}
      calculateMetadata={({ props }) => {
        const fps = props.fps ?? 30;
        const dur = Math.max(1, Math.ceil((props.durationInSeconds ?? 50) * fps));
        return { durationInFrames: dur, fps };
      }}
    />
  );
};