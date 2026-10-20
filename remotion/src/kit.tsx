// Building blocks shared by the templates: layout units, entrance animations, backdrop, headings, icons, counters.
import React, {useContext} from 'react';
import {AbsoluteFill, Easing, Img, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {FONT, Palette, isImage, url} from './theme';

export const useStage = () => {
  const {width, height, fps, durationInFrames} = useVideoConfig();
  const portrait = height > width;
  const u = Math.min(width, height) / 1080;
  return {width, height, fps, n: durationInFrames, portrait, u, seconds: durationInFrames / fps};
};

// spring 0 -> 1 (with a little overshoot) starting at `at` seconds
export const usePop = (at: number, cfg: {damping?: number; stiffness?: number; mass?: number} = {}) => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const fr = f - Math.round(at * fps);
  if (fr < 0) return 0;
  return spring({frame: fr, fps, config: {damping: 11, stiffness: 170, mass: 0.6, ...cfg}});
};
export const pop = (frame: number, fps: number, at: number, cfg: {damping?: number; stiffness?: number; mass?: number} = {}) => {
  const fr = frame - Math.round(at * fps);
  return fr < 0 ? 0 : spring({frame: fr, fps, config: {damping: 11, stiffness: 170, mass: 0.6, ...cfg}});
};

// linear-eased progress 0 -> 1 between at and at + dur seconds
export const prog = (frame: number, fps: number, at: number, dur: number, easing = Easing.out(Easing.cubic)) =>
  interpolate(frame, [at * fps, (at + Math.max(dur, 0.01)) * fps], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing});

// reveal time of item i: from beats, else spread evenly through the first part of the scene
export const beatAt = (beats: number[] | undefined, i: number, count: number, seconds: number, start = 0.35, span = 0.6) => {
  if (beats && beats[i] !== undefined && beats[i] !== null) return beats[i];
  const end = Math.max(start + 0.3, seconds * span);
  return count <= 1 ? start : start + (end - start) * (i / (count - 1));
};

export const fmtNumber = (target: number, k: number, decimals: number, commas = true) => {
  const n = (target * k).toFixed(decimals); const [i, d] = n.split('.');
  return (commas ? i.replace(/\B(?=(\d{3})+(?!\d))/g, ',') : i) + (d ? '.' + d : '');
};

// "$1,250 billion" -> counts the digits up, keeps the text around them
export const countText = (value: string | number, k: number) => {
  const v = String(value); const m = v.match(/^(.*?)(-?\d[\d,]*(?:\.\d+)?)(.*)$/);
  if (!m) return v;
  const dec = (m[2].split('.')[1] || '').length; const target = parseFloat(m[2].replace(/,/g, ''));
  return m[1] + fmtNumber(target, k, dec, m[2].includes(',') || Math.abs(target) >= 10000) + m[3];
};

// an animated motif (templates/Ambient.tsx) the Scene lays behind the chart templates' Backdrop
export const BackdropLayer = React.createContext<React.ReactNode>(null);

// slowly moving soft shapes behind charts, so nothing is ever a frozen frame
export const Backdrop: React.FC<{p: Palette; seed?: number}> = ({p, seed = 1}) => {
  const f = useCurrentFrame(); const {width, height} = useVideoConfig(); const u = Math.min(width, height) / 1080;
  const blobs = [0, 1, 2, 3].map((i) => {
    const s = (seed * 7 + i * 13) % 17;
    return {x: ((s * 97) % 100) / 100, y: ((s * 53 + 20) % 100) / 100, r: (260 + ((s * 31) % 200)) * u, ph: s};
  });
  return (
    <AbsoluteFill style={{background: `radial-gradient(ellipse at 30% 25%, ${p.bg2} 0%, ${p.bg} 70%)`, overflow: 'hidden'}}>
      {blobs.map((b, i) => (
        <div key={i} style={{position: 'absolute', width: b.r * 2, height: b.r * 2, borderRadius: '50%',
          left: b.x * width - b.r + Math.sin((f + b.ph * 20) / 70) * 40 * u, top: b.y * height - b.r + Math.cos((f + b.ph * 15) / 85) * 30 * u,
          background: i % 2 ? p.accent : '#ffffff', opacity: 0.045}} />
      ))}
      <AbsoluteFill style={{backgroundImage: `repeating-linear-gradient(135deg, rgba(255,255,255,0.025) 0 ${2 * u}px, transparent ${2 * u}px ${26 * u}px)`}} />
      {useContext(BackdropLayer)}
    </AbsoluteFill>
  );
};

// the area a template lays out in: the whole frame in 16:9; in 9:16 a square band clear of the Shorts UI and the captions
export const StageBox: React.FC<{children: React.ReactNode; pad?: number}> = ({children, pad = 90}) => {
  const {width, height, portrait, u} = useStage();
  const style: React.CSSProperties = portrait
    ? {position: 'absolute', left: 50 * u, right: 50 * u, top: height * 0.11, height: width - 100 * u + 60 * u, display: 'flex', flexDirection: 'column'}
    : {position: 'absolute', left: pad * u, right: pad * u, top: 70 * u, bottom: 80 * u, display: 'flex', flexDirection: 'column'};
  return <div style={style}>{children}</div>;
};

export const Heading: React.FC<{title?: string; kicker?: string; p: Palette; at?: number; align?: 'left' | 'center'}> = ({title, kicker, p, at = 0.05, align = 'center'}) => {
  const {u} = useStage(); const a = usePop(at, {damping: 14});
  if (!title && !kicker) return null;
  return (
    <div style={{textAlign: align, marginBottom: 26 * u, opacity: Math.min(a, 1), transform: `translateY(${(1 - a) * -30 * u}px)`}}>
      {kicker ? <div style={{fontFamily: FONT, fontWeight: 800, fontSize: 30 * u, letterSpacing: 4 * u, color: p.accent, textTransform: 'uppercase'}}>{kicker}</div> : null}
      {title ? <div style={{fontFamily: FONT, fontWeight: 900, fontSize: 62 * u, lineHeight: 1.08, color: p.text, textShadow: `0 ${4 * u}px 0 rgba(0,0,0,0.25)`}}>{title}</div> : null}
    </div>
  );
};

// an emoji, or an image path served from the run folder
export const Icon: React.FC<{icon?: string; size: number; base?: string; style?: React.CSSProperties}> = ({icon, size, base, style}) => {
  if (!icon) return null;
  if (isImage(icon)) return <Img src={url(base, icon)!} style={{width: size, height: size, objectFit: 'contain', ...style}} />;
  return <span style={{fontSize: size * 0.86, lineHeight: 1, width: size, height: size, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Noto Color Emoji', sans-serif", ...style}}>{icon}</span>;
};

export const Footnote: React.FC<{text?: string; p: Palette}> = ({text, p}) => {
  const {u, portrait, height} = useStage(); const a = usePop(0.6, {damping: 20});
  if (!text) return null;
  return <div style={{position: 'absolute', left: 40 * u, ...(portrait ? {top: height * 0.11 - 50 * u} : {bottom: 24 * u}), fontFamily: FONT, fontWeight: 500,
    fontSize: 22 * u, color: p.muted, opacity: 0.9 * Math.min(a, 1)}}>Source: {text}</div>;
};

export const Pill: React.FC<{children: React.ReactNode; bg: string; color: string; size: number; style?: React.CSSProperties}> = ({children, bg, color, size, style}) => (
  <div style={{display: 'inline-block', background: bg, color, fontFamily: FONT, fontWeight: 800, fontSize: size, padding: `${size * 0.28}px ${size * 0.6}px`,
    borderRadius: size * 0.5, boxShadow: `0 ${size * 0.12}px 0 rgba(0,0,0,0.25)`, whiteSpace: 'nowrap', ...style}}>{children}</div>
);
