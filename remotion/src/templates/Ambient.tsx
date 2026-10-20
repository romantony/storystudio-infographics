// Looping animated backgrounds, drawn in code (no GPU, no clip files), so they never run out: every motif repeats every `period` seconds.
//   ambient: "power_grid" | {motif, mode, at, period, opacity, blend}
//   motif: power_grid | city_lights | network | flow | radar | waves
//   mode:  flow (default, everything running) | blackout (lights go out in a cascade from `at`, current stops) | restore (lights come back on from `at`)
//   at: seconds into each loop when the blackout/restore starts (default 1.5)   period: loop length in seconds (default 8)
//   opacity: 0..1 (default 1 behind charts, 0.55 over a still)   blend: CSS mix-blend-mode when laid over a still (default "screen")
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {Palette} from '../theme';
import {useStage} from '../kit';

export type AmbientSpec = {motif: string; mode?: string; at?: number; period?: number; opacity?: number; blend?: string};
export const MOTIFS = ['power_grid', 'city_lights', 'network', 'flow', 'radar', 'waves'];

export const normalize = (a: any): AmbientSpec | null => {
  if (!a) return null;
  const s = typeof a === 'string' ? {motif: a} : a;
  return MOTIFS.includes(s.motif) ? s : null;
};

const rnd = (i: number, k = 1) => { const x = Math.sin(i * 127.1 + k * 311.7) * 43758.5453; return x - Math.floor(x); };
const clamp = (x: number) => Math.max(0, Math.min(1, x));

type Clock = {t: number; mode: string; at: number; g: number; lit: (r: number) => number};
// g: overall power 0..1.  lit(r): 0..1 for an element with a random rank r (the cascade reaches it at at + r * 1.6 s; it flickers before going out or coming on)
const clock = (t: number, mode: string, at: number): Clock => {
  const g = mode === 'blackout' ? clamp(1 - (t - at) / 1.6) : mode === 'restore' ? clamp((t - at) / 1.6) : 1;
  const lit = (r: number) => {
    if (mode !== 'blackout' && mode !== 'restore') return 1;
    const d = t - (at + r * 1.6); const on = mode === 'restore';
    if (d < -0.3) return on ? 0 : 1;
    if (d < 0) return Math.floor(t * 18 + r * 9) % 2 ? (on ? 0.9 : 0.15) : (on ? 0.1 : 1);   // flicker
    return on ? 1 : 0;
  };
  return {t, mode, at, g, lit};
};

type M = {p: Palette; w: number; h: number; u: number; c: Clock; f: number; fps: number; period: number};

// a quadratic bezier point
const bez = (a: number[], b: number[], c: number[], k: number) => [(1 - k) * (1 - k) * a[0] + 2 * (1 - k) * k * b[0] + k * k * c[0], (1 - k) * (1 - k) * a[1] + 2 * (1 - k) * k * b[1] + k * k * c[1]];

const PowerGrid: React.FC<M> = ({p, w, h, u, c, period}) => {
  const N = 6; const baseY = h * 0.78; const xs = Array.from({length: N}, (_, i) => w * (0.06 + (0.88 * i) / (N - 1)));
  const top = (i: number) => baseY - (210 + 40 * rnd(i, 2)) * u;
  const wires = [0, 1, 2].map((wi) => xs.slice(0, -1).map((x, i) => ({a: [x, top(i) + wi * 26 * u], b: [(x + xs[i + 1]) / 2, top(i) + wi * 26 * u + 54 * u], c: [xs[i + 1], top(i + 1) + wi * 26 * u]})));
  const houses = Array.from({length: 14}, (_, i) => ({x: w * (0.04 + 0.92 * (i + rnd(i, 4) * 0.5) / 14), h: (60 + 90 * rnd(i, 5)) * u, ww: (46 + 30 * rnd(i, 6)) * u, r: rnd(i, 7)}));
  const cycle = (c.t / period) % 1;
  return (
    <svg width={w} height={h} style={{position: 'absolute', inset: 0}}>
      {houses.map((q, i) => {
        const L = c.lit(q.r);
        return (<g key={'h' + i}>
          <rect x={q.x} y={baseY - q.h} width={q.ww} height={q.h} fill="#000" opacity={0.35} />
          {[0, 1, 2].map((r) => [0, 1].map((cc) => <rect key={r + '-' + cc} x={q.x + 8 * u + cc * (q.ww / 2 - 4 * u)} y={baseY - q.h + 10 * u + r * 26 * u} width={q.ww / 2 - 14 * u} height={14 * u}
            fill={p.accent} opacity={(rnd(i * 7 + r * 2 + cc, 9) > 0.25 ? 0.95 : 0.25) * L} />))}
        </g>);
      })}
      <rect x={0} y={baseY} width={w} height={h - baseY} fill="#000" opacity={0.3} />
      {xs.map((x, i) => (<g key={'t' + i} stroke={p.muted} strokeWidth={6 * u} opacity={0.75} fill="none" strokeLinecap="round">
        <path d={`M${x - 40 * u},${baseY} L${x},${top(i)} L${x + 40 * u},${baseY} M${x - 60 * u},${top(i) + 30 * u} L${x + 60 * u},${top(i) + 30 * u} M${x - 46 * u},${top(i) + 56 * u} L${x + 46 * u},${top(i) + 56 * u}`} />
      </g>))}
      {wires.map((ws, wi) => ws.map((s, i) => {
        const pulses = [0, 1, 2].map((k) => ((cycle * 3 + k / 3 + wi * 0.13 + i * 0.07) % 1)); // 3 pulses per span, 3 spans-per-second feel
        return (<g key={wi + '-' + i}>
          <path d={`M${s.a} Q${s.b} ${s.c}`} stroke={c.g > 0.05 ? p.accent : p.muted} strokeWidth={3 * u} fill="none" opacity={0.25 + 0.5 * c.g} />
          {pulses.map((k, j) => { const [x, y] = bez(s.a, s.b, s.c, k); return <circle key={j} cx={x} cy={y} r={7 * u} fill={p.accent} opacity={c.g * (0.5 + 0.5 * Math.sin(k * Math.PI))} style={{filter: `drop-shadow(0 0 ${8 * u}px ${p.accent})`}} />; })}
        </g>);
      }))}
    </svg>
  );
};

const CityLights: React.FC<M> = ({p, w, h, u, c, f, fps}) => {
  const base = h * 0.92; const bl = Array.from({length: 11}, (_, i) => ({x: w * i / 11, ww: w / 11 - 8 * u, hh: h * (0.28 + 0.4 * rnd(i, 11)), r: rnd(i, 12)}));
  return (
    <svg width={w} height={h} style={{position: 'absolute', inset: 0}}>
      {bl.map((b, i) => {
        const cols = Math.max(2, Math.floor(b.ww / (30 * u))), rows = Math.floor(b.hh / (36 * u));
        return (<g key={i}>
          <rect x={b.x} y={base - b.hh} width={b.ww} height={b.hh} fill="#000" opacity={0.4} />
          {Array.from({length: rows * cols}, (_, k) => { const r = Math.floor(k / cols), cc = k % cols; const rk = rnd(i * 97 + k, 13);
            const blink = rnd(i * 97 + k, 14) > 0.9 ? (Math.floor(f / fps * 0.7 + rk * 5) % 2 ? 1 : 0.2) : 1;   // a few windows toggle by themselves
            return <rect key={k} x={b.x + 8 * u + cc * ((b.ww - 16 * u) / cols)} y={base - b.hh + 14 * u + r * 36 * u} width={(b.ww - 16 * u) / cols - 8 * u} height={20 * u}
              fill={rk > 0.5 ? p.accent : '#FFFFFF'} opacity={(rk > 0.2 ? 0.9 : 0.15) * c.lit(rnd(i * 97 + k, 15)) * blink} />; })}
        </g>);
      })}
    </svg>
  );
};

const Network: React.FC<M> = ({p, w, h, u, c, period}) => {
  const nodes = Array.from({length: 14}, (_, i) => [w * (0.08 + 0.84 * rnd(i, 21)), h * (0.12 + 0.76 * rnd(i, 22))]);
  const edges: number[][] = []; nodes.forEach((a, i) => { const d = nodes.map((b, j) => [j, Math.hypot(a[0] - b[0], a[1] - b[1])]).filter(([j]) => j !== i).sort((x, y) => x[1] - y[1]); d.slice(0, 2).forEach(([j]) => edges.push([i, j])); });
  const cyc = (c.t / period) % 1;
  return (
    <svg width={w} height={h} style={{position: 'absolute', inset: 0}}>
      {edges.map(([a, b], i) => { const k = (cyc * 2 + rnd(i, 23)) % 1; const A = nodes[a], B = nodes[b];
        return (<g key={i}><line x1={A[0]} y1={A[1]} x2={B[0]} y2={B[1]} stroke={p.muted} strokeWidth={2 * u} opacity={0.3} />
          <circle cx={A[0] + (B[0] - A[0]) * k} cy={A[1] + (B[1] - A[1]) * k} r={6 * u} fill={p.accent} opacity={c.g} /></g>); })}
      {nodes.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={(12 + 5 * Math.sin(c.t * 2 + i)) * u} fill={p.accent2} opacity={0.35 + 0.65 * c.lit(rnd(i, 24))} />)}
    </svg>
  );
};

const Flow: React.FC<M> = ({p, w, h, u, c, period}) => {
  const lanes = 5; const cyc = (c.t / period) % 1;
  return (
    <svg width={w} height={h} style={{position: 'absolute', inset: 0}}>
      {Array.from({length: lanes}, (_, l) => {
        const y = h * (0.2 + 0.6 * l / (lanes - 1)); const amp = (30 + 40 * rnd(l, 31)) * u;
        return (<g key={l}>
          <path d={`M0,${y} C${w * 0.3},${y - amp} ${w * 0.6},${y + amp} ${w},${y}`} stroke={p.muted} strokeWidth={2 * u} fill="none" opacity={0.2} />
          {Array.from({length: 7}, (_, k) => { const q = (cyc * (1 + l % 2) + k / 7 + rnd(l, 32)) % 1; const x = q * w; const yy = y + Math.sin(q * Math.PI * 2) * amp * 0.6;
            return <circle key={k} cx={x} cy={yy} r={(6 + 4 * rnd(k + l * 9, 33)) * u} fill={p.series[(l + k) % p.series.length]} opacity={0.8 * c.g * Math.sin(q * Math.PI)} />; })}
        </g>);
      })}
    </svg>
  );
};

const Radar: React.FC<M> = ({p, w, h, u, c, period}) => {
  const cyc = (c.t / period) % 1; const cx = w / 2, cy = h / 2;
  return (
    <svg width={w} height={h} style={{position: 'absolute', inset: 0}}>
      {[0, 1, 2, 3].map((k) => { const q = (cyc * 2 + k / 4) % 1; return <circle key={k} cx={cx} cy={cy} r={q * Math.max(w, h) * 0.6} fill="none" stroke={p.accent} strokeWidth={4 * u} opacity={(1 - q) * 0.6 * c.g} />; })}
      <circle cx={cx} cy={cy} r={14 * u} fill={p.accent2} opacity={0.5 + 0.5 * Math.sin(c.t * 4)} />
    </svg>
  );
};

const Waves: React.FC<M> = ({p, w, h, u, c, period}) => {
  const cyc = (c.t / period) % 1;
  return (
    <svg width={w} height={h} style={{position: 'absolute', inset: 0}}>
      {[0, 1, 2, 3].map((l) => {
        const y = h * (0.62 + 0.1 * l); const amp = (16 + 6 * l) * u; const ph = cyc * Math.PI * 2 * (l % 2 ? -1 : 1) * (1 + l);   // whole periods per loop: seamless
        const d = Array.from({length: 49}, (_, i) => `${i ? 'L' : 'M'}${(w * i) / 48},${y + Math.sin((i / 48) * Math.PI * 4 + ph) * amp}`).join(' ') + ` L${w},${h} L0,${h} Z`;
        return <path key={l} d={d} fill={l % 2 ? p.accent : '#FFFFFF'} opacity={0.07 + 0.02 * l} />;
      })}
    </svg>
  );
};

const DRAW: Record<string, React.FC<M>> = {power_grid: PowerGrid, city_lights: CityLights, network: Network, flow: Flow, radar: Radar, waves: Waves};

export const Ambient: React.FC<{spec: AmbientSpec; p: Palette; over?: boolean}> = ({spec, p, over}) => {
  const f = useCurrentFrame(); const {fps, width, height, u} = useStage();
  const period = spec.period ?? 8; const t = (f / fps) % period; const D = DRAW[spec.motif];
  if (!D) return null;
  const c = clock(t, spec.mode ?? 'flow', spec.at ?? 1.5);
  return (
    <AbsoluteFill style={{opacity: spec.opacity ?? (over ? 0.55 : 1), mixBlendMode: (over ? (spec.blend ?? 'screen') : 'normal') as any, pointerEvents: 'none'}}>
      <D p={p} w={width} h={height} u={u} c={c} f={f} fps={fps} period={period} />
    </AbsoluteFill>
  );
};
