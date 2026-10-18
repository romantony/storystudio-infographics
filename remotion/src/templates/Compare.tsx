// versus, timeline, list
import React from 'react';
import {AbsoluteFill, Img, useCurrentFrame} from 'remotion';
import {FONT, Palette, SceneProps, isImage, url} from '../theme';
import {Backdrop, Footnote, Heading, Icon, StageBox, beatAt, countText, pop, prog, useStage} from '../kit';

type P = SceneProps & {p: Palette};

const Side: React.FC<{s: any; p: Palette; a: number; u: number; base?: string; col: string; size: number}> = ({s, p, a, u, base, col, size}) => (
  <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 * u, transform: `scale(${a})`}}>
    <div style={{width: size, height: size, borderRadius: '50%', background: col, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
      border: `${8 * u}px solid ${p.text}`, boxShadow: `0 ${10 * u}px 0 rgba(0,0,0,0.25)`}}>
      {isImage(s.image) ? <Img src={url(base, s.image)!} style={{width: '100%', height: '100%', objectFit: s.fit || 'cover'}} /> : <Icon icon={s.icon || s.image} size={size * 0.7} base={base} />}
    </div>
    <div style={{fontFamily: FONT, fontWeight: 900, fontSize: 46 * u, color: p.text, textAlign: 'center'}}>{s.name}</div>
  </div>
);

// versus: {a: {name, image | icon, color}, b: {...}, rows: [{label, a, b, unit, better: "high" | "low" | "none"}]}  beats: [a, b, row 1, row 2, ...]
export const Versus: React.FC<P> = ({p, a = {}, b = {}, rows = [], title, beats, seconds, source, base}) => {
  const f = useCurrentFrame(); const {fps, u, portrait} = useStage();
  const n = 2 + rows.length;
  const ta = beatAt(beats, 0, n, seconds, 0.2, 0.55), tb = beatAt(beats, 1, n, seconds, 0.2, 0.55);
  const aa = pop(f, fps, ta), ab = pop(f, fps, tb), vs = pop(f, fps, (ta + tb) / 2 + 0.15, {damping: 7, stiffness: 220});
  const ca = a.color || p.series[3], cb = b.color || p.series[1];
  const size = (portrait ? 220 : rows.length > 3 ? 190 : 240) * u;
  return (
    <AbsoluteFill>
      <Backdrop p={p} seed={5} />
      <AbsoluteFill style={{background: `linear-gradient(90deg, ${ca}22 0%, transparent 45%, transparent 55%, ${cb}22 100%)`}} />
      <StageBox>
        {title ? <Heading title={title} p={p} /> : null}
        <div style={{display: 'flex', justifyContent: 'space-around', alignItems: 'center'}}>
          <Side s={a} p={p} a={aa} u={u} base={base} col={ca} size={size} />
          <div style={{fontFamily: FONT, fontWeight: 900, fontSize: 110 * u, color: p.accent, transform: `scale(${vs}) rotate(${(1 - Math.min(vs, 1)) * 30}deg)`,
            textShadow: `0 ${8 * u}px 0 rgba(0,0,0,0.35)`, fontStyle: 'italic'}}>VS</div>
          <Side s={b} p={p} a={ab} u={u} base={base} col={cb} size={size} />
        </div>
        <div style={{flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 18 * u, marginTop: 20 * u}}>
          {rows.map((r: any, i: number) => {
            const t = beatAt(beats, 2 + i, n, seconds, 0.2, 0.55); const ra = pop(f, fps, t, {damping: 16}); const k = prog(f, fps, t, 0.9);
            const va = Number(r.a), vb = Number(r.b); const numeric = !isNaN(va) && !isNaN(vb);
            const mx = Math.max(Math.abs(va), Math.abs(vb), 1e-9); const better = r.better || 'high';
            const win = !numeric || better === 'none' || va === vb ? 0 : (better === 'high' ? (va > vb ? -1 : 1) : (va < vb ? -1 : 1));
            const bar = (v: number, side: number) => {
              const w = numeric ? (Math.abs(v) / mx) * 100 * k : 100 * k; const won = win === side;
              return <div style={{flex: 1, display: 'flex', justifyContent: side < 0 ? 'flex-end' : 'flex-start', alignItems: 'center', gap: 14 * u, flexDirection: side < 0 ? 'row' : 'row-reverse'}}>
                <div style={{fontFamily: FONT, fontWeight: 900, fontSize: 40 * u, color: won ? p.accent : p.text, whiteSpace: 'nowrap'}}>{numeric ? countText(String(side < 0 ? r.a : r.b), k) : (side < 0 ? r.a : r.b)}{r.unit || ''}</div>
                <div style={{width: `${w * 0.62}%`, height: 40 * u, borderRadius: 8 * u, background: won ? p.accent : (side < 0 ? ca : cb), opacity: won || !win ? 1 : 0.55}} />
              </div>;
            };
            return (
              <div key={i} style={{opacity: Math.min(ra, 1), transform: `translateY(${(1 - Math.min(ra, 1)) * 30 * u}px)`}}>
                <div style={{textAlign: 'center', fontFamily: FONT, fontWeight: 800, fontSize: 30 * u, color: p.muted, textTransform: 'uppercase', letterSpacing: 2 * u}}>{r.label}</div>
                <div style={{display: 'flex', gap: 24 * u, alignItems: 'center'}}>{bar(va, -1)}<div style={{width: 6 * u, height: 50 * u, background: p.text, opacity: 0.4}} />{bar(vb, 1)}</div>
              </div>
            );
          })}
        </div>
      </StageBox>
      <Footnote text={source} p={p} />
    </AbsoluteFill>
  );
};

// timeline: {title, events: [{date, label, icon}]}  beats: one per event. Scrolls when the events do not fit.
export const Timeline: React.FC<P> = ({p, title, kicker, events = [], beats, seconds, source, base}) => {
  const f = useCurrentFrame(); const {fps, u, width, height, portrait} = useStage();
  const ts = events.map((_: any, i: number) => beatAt(beats, i, events.length, seconds, 0.4, 0.8));
  const gap = (portrait ? 230 : 400) * u; const visible = portrait ? 4 : 4;
  // follow the newest event once more than `visible` are out
  let shown = 0; ts.forEach((t: number) => { if (f / fps >= t - 0.2) shown += 1; });
  const target = Math.max(0, shown - visible) * gap;
  const lastT = ts[Math.max(0, shown - 1)] ?? 0; const off = target - (1 - prog(f, fps, lastT - 0.2, 0.6)) * (shown > visible ? gap : 0);
  const lineK = prog(f, fps, 0.15, Math.max(0.6, (ts[ts.length - 1] ?? 1) + 0.3));
  const len = (events.length - 1) * gap;
  return (
    <AbsoluteFill>
      <Backdrop p={p} seed={13} />
      <StageBox>
        <Heading title={title} kicker={kicker} p={p} />
        <div style={{flex: 1, position: 'relative', overflow: 'hidden'}}>
          <div style={{position: 'absolute', ...(portrait ? {left: 170 * u, top: 60 * u - off} : {top: '50%', left: 160 * u - off})}}>
            <div style={{position: 'absolute', background: 'rgba(255,255,255,0.25)', borderRadius: 4 * u, ...(portrait ? {left: -4 * u, top: 0, width: 8 * u, height: len * lineK} : {top: -4 * u, left: 0, height: 8 * u, width: len * lineK})}} />
            {events.map((e: any, i: number) => {
              const a = pop(f, fps, ts[i], {damping: 11}); const pos = i * gap; const up = i % 2 === 0;
              return (
                <div key={i} style={{position: 'absolute', ...(portrait ? {top: pos, left: 0} : {left: pos, top: 0})}}>
                  <div style={{position: 'absolute', width: 40 * u, height: 40 * u, left: -20 * u, top: -20 * u, borderRadius: '50%', background: p.accent, border: `${7 * u}px solid ${p.text}`, transform: `scale(${a})`}} />
                  <div style={{position: 'absolute', width: portrait ? 640 * u : 360 * u, ...(portrait ? {left: 50 * u, top: -46 * u} : {left: -180 * u, ...(up ? {bottom: 44 * u} : {top: 44 * u})}),
                    textAlign: portrait ? 'left' : 'center', opacity: Math.min(a, 1), transform: `translateY(${(1 - Math.min(a, 1)) * (up ? 30 : -30) * u}px)`}}>
                    {e.icon ? <div style={{marginBottom: 6 * u}}><Icon icon={e.icon} size={70 * u} base={base} /></div> : null}
                    <div style={{fontFamily: FONT, fontWeight: 900, fontSize: 46 * u, color: p.accent}}>{e.date}</div>
                    <div style={{fontFamily: FONT, fontWeight: 700, fontSize: 32 * u, color: p.text, lineHeight: 1.15}}>{e.label}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </StageBox>
      <Footnote text={source} p={p} />
    </AbsoluteFill>
  );
};

// list: {title, items: [{text, icon}], numbered: true, countdown: false}  beats: one per item
export const List: React.FC<P> = ({p, title, kicker, items = [], numbered = true, countdown = false, beats, seconds, source, base}) => {
  const f = useCurrentFrame(); const {fps, u, portrait} = useStage();
  const rowH = Math.min(130, 760 / Math.max(items.length, 1)) * u;
  return (
    <AbsoluteFill>
      <Backdrop p={p} seed={17} />
      <StageBox>
        <Heading title={title} kicker={kicker} p={p} />
        <div style={{flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: rowH * 0.16}}>
          {items.map((it: any, i: number) => {
            const a = pop(f, fps, beatAt(beats, i, items.length, seconds, 0.4, 0.75), {damping: 14});
            const num = countdown ? items.length - i : i + 1;
            return (
              <div key={i} style={{display: 'flex', alignItems: 'center', gap: 24 * u, height: rowH, opacity: Math.min(a * 1.4, 1), transform: `translateX(${(1 - Math.min(a, 1)) * -80 * u}px)`}}>
                {numbered ? <div style={{width: rowH * 0.86, height: rowH * 0.86, borderRadius: rowH * 0.2, background: p.accent, color: p.ink, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontFamily: FONT, fontWeight: 900, fontSize: rowH * 0.48, flexShrink: 0, boxShadow: `0 ${6 * u}px 0 rgba(0,0,0,0.25)`}}>{num}</div> : null}
                {it.icon ? <Icon icon={it.icon} size={rowH * 0.8} base={base} /> : null}
                <div style={{fontFamily: FONT, fontWeight: 800, fontSize: Math.min(rowH * 0.42, 50 * u), color: p.text, lineHeight: 1.12}}>{it.text}</div>
              </div>
            );
          })}
        </div>
      </StageBox>
      <Footnote text={source} p={p} />
    </AbsoluteFill>
  );
};
