// A full-frame illustration with a camera move, cut-out characters that pop in and idle, callout labels and a time badge.
//   image: path            move: zoom_in | zoom_out | pan_left | pan_right | pan_up | pan_down | still | {from: [x, y, zoom], to: [x, y, zoom]}
//   cast: [{src, x: 0..1 (centre), y: 0..1 (feet), h: 0..1 (height), flip, at}]
//   callouts: [{text, x, y, icon, color}]   timecard: "DAY 3 · 09:45"
// Beats: cast members first, then callouts.
import React from 'react';
import {AbsoluteFill, Easing, Img, interpolate, useCurrentFrame} from 'remotion';
import {Palette, SceneProps, FONT, url} from '../theme';
import {Icon, beatAt, pop, useStage} from '../kit';

type Cam = [number, number, number];
const MOVES: Record<string, [Cam, Cam]> = {
  zoom_in: [[0.5, 0.5, 1.0], [0.5, 0.5, 1.14]], zoom_out: [[0.5, 0.5, 1.16], [0.5, 0.5, 1.02]],
  pan_left: [[0.62, 0.5, 1.14], [0.38, 0.5, 1.14]], pan_right: [[0.38, 0.5, 1.14], [0.62, 0.5, 1.14]],
  pan_up: [[0.5, 0.62, 1.14], [0.5, 0.4, 1.14]], pan_down: [[0.5, 0.4, 1.14], [0.5, 0.62, 1.14]], still: [[0.5, 0.5, 1.03], [0.5, 0.5, 1.05]],
};

export const camera = (move: any, k: number): Cam => {
  const [a, b] = typeof move === 'object' && move?.from ? [move.from as Cam, move.to as Cam] : (MOVES[move as string] || MOVES.zoom_in);
  return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k];
};

// transform that shows point (cx, cy) of the frame at the centre with zoom z, clamped so no edge shows
const camStyle = (c: Cam): React.CSSProperties => {
  const z = Math.max(1, c[2]); const lim = (1 - 1 / z) / 2;
  const cx = Math.min(0.5 + lim, Math.max(0.5 - lim, c[0])); const cy = Math.min(0.5 + lim, Math.max(0.5 - lim, c[1]));
  return {transform: `scale(${z}) translate(${(0.5 - cx) * 100}%, ${(0.5 - cy) * 100}%)`, transformOrigin: '50% 50%'};
};

export const TimeBadge: React.FC<{text?: string; p: Palette}> = ({text, p}) => {
  const f = useCurrentFrame(); const {u, fps, portrait, height} = useStage(); const a = pop(f, fps, 0.15, {damping: 15});
  if (!text) return null;
  return (
    <div style={{position: 'absolute', left: 40 * u, top: portrait ? height * 0.11 : 36 * u, display: 'flex', alignItems: 'center', gap: 14 * u,
      background: p.ink, color: p.text, fontFamily: FONT, fontWeight: 800, fontSize: 38 * u, padding: `${10 * u}px ${24 * u}px`,
      borderRadius: 12 * u, borderLeft: `${10 * u}px solid ${p.accent}`, transform: `translateX(${(1 - a) * -120}%)`, boxShadow: `0 ${6 * u}px 0 rgba(0,0,0,0.25)`}}>
      <span style={{fontFamily: "'Noto Color Emoji'", fontSize: 34 * u}}>⏱️</span>{text}
    </div>
  );
};

export const Illustration: React.FC<SceneProps & {p: Palette}> = (props) => {
  const {p, base, image, move = 'zoom_in', cast = [], callouts = [], timecard, beats, seconds, tint} = props;
  const f = useCurrentFrame(); const {fps, n, u, width, height, portrait} = useStage();
  const k = interpolate(f, [0, n - 1], [0, 1], {easing: Easing.inOut(Easing.sin), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const cam = camera(move, k);
  const total = cast.length + callouts.length;
  // the cast moves a little more than the background: cheap parallax
  const par = (cam[0] - 0.5) * -60 * u;
  return (
    <AbsoluteFill style={{background: p.bg, overflow: 'hidden'}}>
      <AbsoluteFill style={camStyle(cam)}>
        {image ? <Img src={url(base, image)!} style={{width: '100%', height: '100%', objectFit: 'cover'}} /> : null}
        {tint ? <AbsoluteFill style={{background: tint, mixBlendMode: 'multiply'}} /> : null}
      </AbsoluteFill>
      {cast.map((c: any, i: number) => {
        const at = c.at ?? beatAt(beats, i, total, seconds, 0.25, 0.35);
        const a = pop(f, fps, at, {damping: 9, stiffness: 200});
        const h = (c.h ?? 0.72) * height; const bob = Math.sin((f / fps) * 2.4 + i * 1.7) * 6 * u * Math.min(a, 1);
        const breathe = 1 + Math.sin((f / fps) * 3.1 + i) * 0.012;
        return (
          <Img key={i} src={url(base, c.src)!} style={{position: 'absolute', height: h, left: (c.x ?? 0.5) * width + par * (1 + i * 0.2), top: (c.y ?? (portrait ? 0.6 : 0.98)) * height - h + bob,
            transform: `translateX(-50%) scale(${(c.flip ? -1 : 1) * Math.max(a, 0.001)}, ${Math.max(a, 0.001) * breathe})`, transformOrigin: '50% 100%',
            filter: `drop-shadow(0 ${10 * u}px ${8 * u}px rgba(0,0,0,0.35))`}} />
        );
      })}
      {callouts.map((c: any, i: number) => {
        const at = c.at ?? beatAt(beats, cast.length + i, total, seconds, 0.6, 0.6);
        const a = pop(f, fps, at, {damping: 10});
        const col = c.color || p.panel; const ink = c.color ? p.text : p.ink;
        const left = (c.x ?? 0.5) * width; const top = (c.y ?? 0.3) * height;
        return (
          <div key={'c' + i} style={{position: 'absolute', left, top, transform: `translate(-50%, -100%) scale(${a})`, transformOrigin: '50% 100%'}}>
            <div style={{display: 'flex', alignItems: 'center', gap: 12 * u, background: col, color: ink, fontFamily: FONT, fontWeight: 800, fontSize: 40 * u,
              padding: `${12 * u}px ${26 * u}px`, borderRadius: 18 * u, boxShadow: `0 ${8 * u}px 0 rgba(0,0,0,0.25)`, whiteSpace: 'nowrap'}}>
              {c.icon ? <Icon icon={c.icon} size={44 * u} base={base} /> : null}{c.text}
            </div>
            <div style={{width: 0, height: 0, margin: '0 auto', borderLeft: `${16 * u}px solid transparent`, borderRight: `${16 * u}px solid transparent`, borderTop: `${20 * u}px solid ${col}`}} />
          </div>
        );
      })}
      <TimeBadge text={timecard} p={p} />
    </AbsoluteFill>
  );
};
