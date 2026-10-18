import React from 'react';
import {Composition} from 'remotion';
import {Scene} from './Scene';
import {Thumb} from './Thumb';
import {SceneProps} from './theme';

// Size, length and frame rate come from the props, so one bundle serves 16:9, 9:16 and the thumbnail.
// Remotion merges the input props over these, so they hold only the keys every scene sends anyway.
const demo: SceneProps = {type: 'title', width: 1920, height: 1080, fps: 30, seconds: 3};
const meta = ({props}: {props: any}) => ({width: props.width, height: props.height, fps: props.fps, durationInFrames: Math.max(2, Math.round(props.seconds * props.fps))});

export const Root: React.FC = () => (
  <>
    <Composition id="Scene" component={Scene as any} defaultProps={demo} width={1920} height={1080} fps={30} durationInFrames={180} calculateMetadata={meta} />
    <Composition id="Thumb" component={Thumb as any} defaultProps={{type: 'thumb', width: 1280, height: 720, fps: 30, seconds: 1}}
      width={1280} height={720} fps={30} durationInFrames={30} calculateMetadata={meta} />
  </>
);
