// Small looping animated props laid over any scene (free: drawn in code, or a Lottie JSON the series supplies).
//   animated: [{sprite: "turbine" | "gears" | "coin" | "heartbeat" | "bulb", x: 0..1 (centre), y: 0..1 (centre), h: 0..1 of the frame height, at: seconds, mode: "on" | "off" | "flicker" (bulb), color}]
//             [{lottie: "assets/lottie/name.json", x, y, h, at, loop: true}]
import React, {useEffect, useState} from 'react';
import {AbsoluteFill, continueRender, delayRender, useCurrentFrame} from 'remotion';
import {Lottie, LottieAnimationData} from '@remotion/lottie';
import {Palette, url} from '../theme';
import {pop, useStage} from '../kit';

const TAU = Math.PI * 2;
type S = {p: Palette; t: number; size: number; mode?: string; color?: string};

const Turbine: React.FC<S> = ({p, t, size, color}) => (
  <svg width={size} height={size} viewBox="-50 -50 100 100">
    <path d="M-4,50 L-2,0 L2,0 L4,50 Z" fill={p.muted} />
    <g transform={`rotate(${(t * 90) % 360})`}>
      {[0, 120, 240].map((a) => <path key={a} transform={`rotate(${a})`} d="M-3,0 L0,-46 L3,0 Z" fill={color || '#FFFFFF'} />)}
    </g>
    <circle r={5} fill={p.accent} />
  </svg>
);

const Gears: React.FC<S> = ({p, t, size, color}) => {
  const gear = (r: number, teeth: number, rot: number, fill: string) => (
    <g transform={`rotate(${rot})`}>
      {Array.from({length: teeth}, (_, i) => <rect key={i} x={-r * 0.12} y={-r * 1.18} width={r * 0.24} height={r * 0.3} fill={fill} transform={`rotate(${(360 / teeth) * i})`} />)}
      <circle r={r} fill={fill} /><circle r={r * 0.4} fill={p.bg} />
    </g>
  );
  return (
    <svg width={size} height={size} viewBox="-50 -50 100 100">
      <g transform="translate(-14,10)">{gear(22, 10, t * 40, color || p.accent)}</g>
      <g transform="translate(24,-18)">{gear(15, 8, -t * 40 * (22 / 15) + 18, p.accent2)}</g>
    </svg>
  );
};

const Coin: React.FC<S> = ({p, t, size, color}) => {
  const k = Math.cos(t * 3.2);
  return (
    <svg width={size} height={size} viewBox="-50 -50 100 100">
      <g transform={`scale(${Math.max(0.06, Math.abs(k))},1)`}>
        <circle r={40} fill={color || p.accent} stroke="#B8860B" strokeWidth={5} />
        {k > 0 ? <text y={14} textAnchor="middle" fontSize={44} fontWeight={800} fill="#B8860B" fontFamily="Montserrat, sans-serif">$</text> : <circle r={24} fill="none" stroke="#B8860B" strokeWidth={4} />}
      </g>
    </svg>
  );
};

const Heartbeat: React.FC<S> = ({p, t, size, color}) => {
  const W = 200, beat = (x: number) => { const q = ((x % 50) + 50) % 50; return q < 8 ? 0 : q < 12 ? -(q - 8) * 6 : q < 16 ? (q - 12) * 12 - 24 : q < 20 ? 24 - (q - 16) * 9 : q < 24 ? -12 + (q - 20) * 3 : 0; };
  const sh = (t * 60) % 50;
  const d = Array.from({length: W + 1}, (_, i) => `${i ? 'L' : 'M'}${i},${50 + beat(i + sh)}`).join(' ');
  return (
    <svg width={size * 2} height={size} viewBox="0 0 200 100">
      <path d={d} fill="none" stroke={color || p.good} strokeWidth={4} strokeLinejoin="round" style={{filter: `drop-shadow(0 0 4px ${color || p.good})`}} />
    </svg>
  );
};

const Bulb: React.FC<S> = ({p, t, size, mode = 'on', color}) => {
  const on = mode === 'off' ? 0 : mode === 'flicker' ? (Math.floor(t * 14) % 3 === 0 ? 0.2 : 1) : 0.85 + 0.15 * Math.sin(t * 5);
  const c = color || p.accent;
  return (
    <svg width={size} height={size} viewBox="-50 -50 100 100">
      {on > 0 ? <circle r={46} fill={c} opacity={0.22 * on} /> : null}
      <path d="M-18,8 A24,24 0 1 1 18,8 C14,16 14,20 14,26 L-14,26 C-14,20 -14,16 -18,8 Z" fill={on > 0.5 ? c : p.muted} opacity={0.35 + 0.65 * on} />
      <rect x={-12} y={28} width={24} height={6} rx={2} fill={p.muted} /><rect x={-9} y={36} width={18} height={6} rx={2} fill={p.muted} />
    </svg>
  );
};

const SPRITES: Record<string, React.FC<S>> = {turbine: Turbine, gears: Gears, coin: Coin, heartbeat: Heartbeat, bulb: Bulb};
export const SPRITE_NAMES = Object.keys(SPRITES);

const LottieSprite: React.FC<{src: string; size: number; loop: boolean}> = ({src, size, loop}) => {
  const [h] = useState(() => delayRender('lottie')); const [data, setData] = useState<LottieAnimationData | null>(null);
  useEffect(() => { fetch(src).then((r) => r.json()).then((d) => { setData(d); continueRender(h); }).catch(() => continueRender(h)); }, [src, h]);
  return data ? <Lottie animationData={data} loop={loop} style={{width: size, height: size}} /> : null;
};

export const Sprites: React.FC<{items: any[]; p: Palette; base?: string}> = ({items, p, base}) => {
  const f = useCurrentFrame(); const {fps, width, height} = useStage();
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {items.map((it, i) => {
        const a = pop(f, fps, it.at ?? 0.3 + 0.2 * i, {damping: 11}); const size = (it.h ?? 0.22) * height;
        const S = it.sprite ? SPRITES[it.sprite] : null;
        if (!S && !it.lottie) return null;
        return (
          <div key={i} style={{position: 'absolute', left: (it.x ?? 0.85) * width, top: (it.y ?? 0.2) * height, transform: `translate(-50%, -50%) scale(${Math.max(a, 0.001)})`}}>
            {S ? <S p={p} t={f / fps} size={size} mode={it.mode} color={it.color} /> : <LottieSprite src={url(base, it.lottie)!} size={size} loop={it.loop !== false} />}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
