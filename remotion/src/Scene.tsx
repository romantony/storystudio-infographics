import React, {useEffect, useState} from 'react';
import {AbsoluteFill, Img, continueRender, delayRender, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {FONT, SceneProps, pal, url} from './theme';
import {Illustration, TimeBadge} from './templates/Illustration';
import {BarChart, Counter, Donut, Icons, LineChart} from './templates/Charts';
import {List, Timeline, Versus} from './templates/Compare';
import {MapScene} from './templates/MapScene';
import {Ambient, normalize} from './templates/Ambient';
import {Sprites} from './templates/Sprites';
import {BackdropLayer} from './kit';
import {Bars3D, Globe, Network3D} from './templates/Three';
import {Clip, EndCard, TextCard, TimeCard, TitleCard} from './templates/Cards';

export const TEMPLATES: Record<string, React.FC<any>> = {
  illustration: Illustration, bar_chart: BarChart, line_chart: LineChart, donut: Donut, counter: Counter, icons: Icons,
  versus: Versus, timeline: Timeline, list: List, map: MapScene, title: TitleCard, timecard: TimeCard, text: TextCard,
  endcard: EndCard, clip: Clip, bars3d: Bars3D, globe: Globe, network3d: Network3D,
};

// wait for the web fonts before the first frame is captured
const useFonts = () => {
  const [h] = useState(() => delayRender('fonts'));
  useEffect(() => {
    Promise.all(['500', '700', '800', '900'].map((w) => document.fonts.load(`${w} 40px Montserrat`))).then(() => document.fonts.ready).then(() => continueRender(h)).catch(() => continueRender(h));
  }, [h]);
};

// cut: "whip" slides the new scene in with a blur (the default between different scenes), "fade" from black, "hard" none
const Entrance: React.FC<{cut?: string; children: React.ReactNode}> = ({cut = 'whip', children}) => {
  const f = useCurrentFrame(); const {fps, width} = useVideoConfig();
  if (cut === 'hard') return <>{children}</>;
  if (cut === 'fade') return <AbsoluteFill style={{opacity: interpolate(f, [0, 0.35 * fps], [0, 1], {extrapolateRight: 'clamp'})}}>{children}</AbsoluteFill>;
  const k = interpolate(f, [0, 0.28 * fps], [1, 0], {extrapolateRight: 'clamp', easing: (t) => 1 - Math.pow(1 - t, 3)});
  return <AbsoluteFill style={{transform: `translateX(${k * width * 0.18}px)`, filter: k > 0.02 ? `blur(${k * 26}px)` : undefined}}>{children}</AbsoluteFill>;
};

// a small watermark/logo the series can set in style.json ("logo": "assets/logo.png")
const Logo: React.FC<{src?: string; base?: string}> = ({src, base}) => {
  const {width, height} = useVideoConfig(); const u = Math.min(width, height) / 1080;
  if (!src) return null;
  return <Img src={url(base, src)!} style={{position: 'absolute', right: 30 * u, top: 30 * u, height: 70 * u, opacity: 0.85}} />;
};

export const Scene: React.FC<SceneProps> = (props) => {
  useFonts();
  const p = pal(props.palette); const T = TEMPLATES[props.type];
  if (!T) return <AbsoluteFill style={{background: '#300', color: '#fff', fontFamily: FONT, fontSize: 60, padding: 80}}>Unknown scene type: {props.type}</AbsoluteFill>;
  // ambient: a looping animated motif. Behind the chart templates (through their Backdrop); over a still or a clip, blended on top.
  const amb = normalize(props.ambient); const overImage = props.type === 'illustration' || props.type === 'clip';
  return (
    <AbsoluteFill style={{background: p.bg}}>
      <Entrance cut={props.cut}>
        <BackdropLayer.Provider value={amb && !overImage ? <Ambient spec={amb} p={p} /> : null}>
          <T {...props} p={p} />
          {amb && overImage ? <Ambient spec={amb} p={p} over /> : null}
        </BackdropLayer.Provider>
      </Entrance>
      {Array.isArray(props.animated) && props.animated.length ? <Sprites items={props.animated} p={p} base={props.base} /> : null}
      {props.timecard && props.type !== 'illustration' && props.type !== 'timecard' ? <TimeBadge text={props.timecard} p={p} /> : null}
      <Logo src={props.logo} base={props.base} />
    </AbsoluteFill>
  );
};
