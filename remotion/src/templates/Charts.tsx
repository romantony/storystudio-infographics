// Data templates: bar_chart, line_chart, donut, counter, icons.
import React from 'react';
import {AbsoluteFill, Easing, useCurrentFrame} from 'remotion';
import {FONT, Palette, SceneProps} from '../theme';
import {Backdrop, Footnote, Heading, Icon, StageBox, beatAt, countText, fmtNumber, pop, prog, useStage} from '../kit';

type P = SceneProps & {p: Palette};

// bar_chart: {title, kicker, unit, prefix, decimals, max, items: [{label, value, icon, color, highlight}]}  beats: one per bar
export const BarChart: React.FC<P> = ({p, title, kicker, items = [], unit = '', prefix = '', decimals, max, beats, seconds, source, base}) => {
  const f = useCurrentFrame(); const {fps, u, portrait} = useStage();
  const mx = max ?? Math.max(...items.map((i: any) => Number(i.value) || 0), 1);
  const dec = decimals ?? (items.some((i: any) => String(i.value).includes('.')) ? 1 : 0);
  const rowH = Math.min(portrait ? 120 : 112, (portrait ? 760 : 760) / Math.max(items.length, 1)) * u;
  return (
    <AbsoluteFill>
      <Backdrop p={p} seed={items.length + 3} />
      <StageBox>
        <Heading title={title} kicker={kicker} p={p} />
        <div style={{flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: rowH * 0.2}}>
          {items.map((it: any, i: number) => {
            const at = beatAt(beats, i, items.length, seconds, 0.45, 0.55);
            const a = pop(f, fps, at, {damping: 16, stiffness: 110}); const k = prog(f, fps, at, 1.1);
            const anyHi = items.some((x: any) => x.highlight);
            const col = it.color || (anyHi ? (it.highlight ? p.accent : p.series[3]) : p.series[i % p.series.length]);
            const w = Math.max(0, (Number(it.value) || 0) / mx) * k;
            return (
              <div key={i} style={{display: 'flex', alignItems: 'center', height: rowH, gap: 18 * u, opacity: Math.min(1, a * 1.5), transform: `translateX(${(1 - Math.min(a, 1)) * -40 * u}px)`}}>
                {items.some((x: any) => x.icon) ? <Icon icon={it.icon} size={rowH * 0.78} base={base} /> : null}
                <div style={{width: portrait ? 230 * u : 330 * u, fontFamily: FONT, fontWeight: 800, fontSize: Math.min(rowH * 0.36, 40 * u), color: p.text, textAlign: 'right', lineHeight: 1.05}}>{it.label}</div>
                <div style={{flex: 1, height: rowH * 0.62, position: 'relative'}}>
                  <div style={{position: 'absolute', inset: 0, background: 'rgba(255,255,255,0.07)', borderRadius: 10 * u}} />
                  <div style={{position: 'absolute', left: 0, top: 0, bottom: 0, width: `${w * 82}%`, background: col, borderRadius: 10 * u,
                    boxShadow: it.highlight ? `0 0 ${24 * u}px ${col}` : `0 ${5 * u}px 0 rgba(0,0,0,0.25)`}} />
                  <div style={{position: 'absolute', left: `calc(${w * 82}% + ${14 * u}px)`, top: '50%', transform: 'translateY(-50%)', fontFamily: FONT, fontWeight: 900,
                    fontSize: Math.min(rowH * 0.42, 46 * u), color: it.highlight ? p.accent : p.text, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums'}}>
                    {prefix}{fmtNumber(Number(it.value) || 0, k, dec)}{unit}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </StageBox>
      <Footnote text={source} p={p} />
    </AbsoluteFill>
  );
};

// line_chart: {title, unit, points: [{x: "2019", y: 3.2}], annotate: {at: index, text}}  beats: [start drawing, annotation]
export const LineChart: React.FC<P> = ({p, title, kicker, points = [], unit = '', prefix = '', annotate, beats, seconds, source, min}) => {
  const f = useCurrentFrame(); const {fps, u, width, portrait} = useStage();
  const W = portrait ? width - 140 * u : width - 260 * u; const H = portrait ? 640 * u : 620 * u;
  const ys = points.map((q: any) => Number(q.y)); const lo = min ?? Math.min(0, ...ys); const hi = Math.max(...ys) * 1.12 || 1;
  const X = (i: number) => 90 * u + (W - 130 * u) * (points.length > 1 ? i / (points.length - 1) : 0.5);
  const Y = (v: number) => H - 60 * u - (H - 100 * u) * ((v - lo) / (hi - lo || 1));
  const t0 = beatAt(beats, 0, 2, seconds, 0.5, 0.2); const dur = Math.max(1.6, seconds * 0.45);
  const k = prog(f, fps, t0, dur, Easing.inOut(Easing.cubic));
  const d = points.map((q: any, i: number) => `${i ? 'L' : 'M'}${X(i)},${Y(Number(q.y))}`).join(' ');
  const area = d + ` L${X(points.length - 1)},${Y(lo)} L${X(0)},${Y(lo)} Z`;
  const reveal = 90 * u + (W - 130 * u) * k + 10 * u;
  const grid = [0, 1, 2, 3].map((g) => lo + ((hi - lo) * g) / 3);
  const an = annotate && points[annotate.at] ? annotate : null;
  const ta = an ? (beats?.[1] ?? t0 + dur * (an.at / Math.max(points.length - 1, 1)) + 0.2) : 0; const aa = pop(f, fps, ta);
  const dec = ys.some((v) => !Number.isInteger(v)) ? 1 : 0;
  // keep the annotation box inside the chart
  const half = an ? (an.text.length * 10 + 30) * u : 0; const ax = an ? X(an.at) : 0;
  const annoShift = an ? Math.min(0, W - (ax + half)) + Math.max(0, 80 * u - (ax - half)) : 0;
  return (
    <AbsoluteFill>
      <Backdrop p={p} seed={points.length} />
      <StageBox>
        <Heading title={title} kicker={kicker} p={p} />
        <svg width={W} height={H} style={{overflow: 'visible', alignSelf: 'center'}}>
          <defs>
            <clipPath id="rv"><rect x={0} y={-50} width={reveal} height={H + 100} /></clipPath>
            <linearGradient id="ar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={p.accent} stopOpacity={0.45} /><stop offset="1" stopColor={p.accent} stopOpacity={0} /></linearGradient>
          </defs>
          {grid.map((g, i) => (
            <g key={i}>
              <line x1={80 * u} x2={W} y1={Y(g)} y2={Y(g)} stroke="rgba(255,255,255,0.15)" strokeWidth={2 * u} strokeDasharray={`${8 * u} ${8 * u}`} />
              <text x={66 * u} y={Y(g) + 10 * u} textAnchor="end" fill={p.muted} style={{fontFamily: FONT, fontWeight: 700, fontSize: 26 * u}}>{prefix}{fmtNumber(g, 1, dec)}{unit}</text>
            </g>
          ))}
          {points.map((q: any, i: number) => (points.length <= 12 || i % Math.ceil(points.length / 10) === 0 || i === points.length - 1) ? (
            <text key={i} x={X(i)} y={H - 14 * u} textAnchor="middle" fill={p.muted} style={{fontFamily: FONT, fontWeight: 700, fontSize: 26 * u}}>{q.x}</text>) : null)}
          <g clipPath="url(#rv)">
            <path d={area} fill="url(#ar)" />
            <path d={d} fill="none" stroke={p.accent} strokeWidth={9 * u} strokeLinejoin="round" strokeLinecap="round" />
            {points.map((q: any, i: number) => <circle key={i} cx={X(i)} cy={Y(Number(q.y))} r={9 * u} fill={p.bg} stroke={p.accent} strokeWidth={5 * u} />)}
          </g>
          {an ? (
            <g transform={`translate(${X(an.at)},${Y(Number(points[an.at].y))}) scale(${aa})`}>
              <circle r={22 * u} fill="none" stroke={p.accent2} strokeWidth={6 * u} />
              <g transform={`translate(${annoShift},${-48 * u})`}>
                <rect x={-(an.text.length * 10 + 30) * u} y={-34 * u} width={(an.text.length * 20 + 60) * u} height={56 * u} rx={14 * u} fill={p.accent2} />
                <text textAnchor="middle" y={4 * u} fill="#fff" style={{fontFamily: FONT, fontWeight: 800, fontSize: 32 * u}}>{an.text}</text>
              </g>
            </g>
          ) : null}
        </svg>
      </StageBox>
      <Footnote text={source} p={p} />
    </AbsoluteFill>
  );
};

// donut: {title, items: [{label, value, color}], center: {value, label}}  beats: [sweep start, legend 1, legend 2, ...]
export const Donut: React.FC<P> = ({p, title, kicker, items = [], center, beats, seconds, source}) => {
  const f = useCurrentFrame(); const {fps, u, portrait} = useStage();
  const total = items.reduce((s: number, i: any) => s + Number(i.value), 0) || 1;
  const R = (portrait ? 250 : 230) * u; const SW = 95 * u; const C = 2 * Math.PI * R;
  const t0 = beatAt(beats, 0, 1, seconds, 0.4, 0.2); const k = prog(f, fps, t0, 1.5, Easing.inOut(Easing.cubic));
  let acc = 0;
  const ca = pop(f, fps, t0 + 1.2);
  return (
    <AbsoluteFill>
      <Backdrop p={p} seed={items.length + 9} />
      <StageBox>
        <Heading title={title} kicker={kicker} p={p} />
        <div style={{flex: 1, display: 'flex', flexDirection: portrait ? 'column' : 'row', alignItems: 'center', justifyContent: 'center', gap: 70 * u}}>
          <div style={{position: 'relative', width: 2 * R + SW, height: 2 * R + SW}}>
            <svg width={2 * R + SW} height={2 * R + SW} style={{transform: 'rotate(-90deg)'}}>
              <circle cx={R + SW / 2} cy={R + SW / 2} r={R} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={SW} />
              {items.map((it: any, i: number) => {
                const frac = Number(it.value) / total; const start = acc; acc += frac;
                const shown = Math.max(0, Math.min(frac, k - start));
                return <circle key={i} cx={R + SW / 2} cy={R + SW / 2} r={R} fill="none" stroke={it.color || p.series[i % p.series.length]} strokeWidth={SW}
                  strokeDasharray={`${shown * C} ${C}`} strokeDashoffset={-start * C} />;
              })}
            </svg>
            {center ? (
              <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', transform: `scale(${ca})`}}>
                <div style={{fontFamily: FONT, fontWeight: 900, fontSize: 86 * u, color: p.accent}}>{countText(center.value, Math.min(ca, 1))}</div>
                {center.label ? <div style={{fontFamily: FONT, fontWeight: 700, fontSize: 30 * u, color: p.text, maxWidth: R * 1.4, textAlign: 'center'}}>{center.label}</div> : null}
              </div>
            ) : null}
          </div>
          <div style={{display: 'flex', flexDirection: 'column', gap: 22 * u}}>
            {items.map((it: any, i: number) => {
              const a = pop(f, fps, beats?.[i + 1] ?? t0 + 0.25 + i * 0.3);
              return (
                <div key={i} style={{display: 'flex', alignItems: 'center', gap: 18 * u, opacity: Math.min(a, 1), transform: `translateX(${(1 - Math.min(a, 1)) * 40 * u}px)`}}>
                  <div style={{width: 34 * u, height: 34 * u, borderRadius: 8 * u, background: it.color || p.series[i % p.series.length]}} />
                  <div style={{fontFamily: FONT, fontWeight: 800, fontSize: 38 * u, color: p.text}}>{it.label}</div>
                  <div style={{fontFamily: FONT, fontWeight: 900, fontSize: 38 * u, color: p.accent}}>{it.display ?? `${Math.round((Number(it.value) / total) * 100)}%`}</div>
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

// counter: {value: "$2.4 trillion", label, icon, sub}  beats: [count start, sub line]
export const Counter: React.FC<P> = ({p, value = '', label, icon, sub, kicker, beats, seconds, source, base}) => {
  const f = useCurrentFrame(); const {fps, u} = useStage();
  const t0 = beatAt(beats, 0, 2, seconds, 0.3, 0.2); const a = pop(f, fps, t0, {damping: 9});
  const k = prog(f, fps, t0, Math.min(1.8, seconds * 0.4), Easing.out(Easing.cubic));
  const b = pop(f, fps, beats?.[1] ?? t0 + 1.2, {damping: 14});
  const shake = k > 0.98 && k < 1 ? 0 : 0;
  return (
    <AbsoluteFill>
      <Backdrop p={p} seed={7} />
      <StageBox>
        <div style={{flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', gap: 10 * u}}>
          {kicker ? <div style={{fontFamily: FONT, fontWeight: 800, fontSize: 34 * u, letterSpacing: 4 * u, color: p.accent, textTransform: 'uppercase', opacity: Math.min(a, 1)}}>{kicker}</div> : null}
          {icon ? <div style={{transform: `scale(${a}) rotate(${(1 - Math.min(a, 1)) * -20}deg)`}}><Icon icon={icon} size={190 * u} base={base} /></div> : null}
          <div style={{fontFamily: FONT, fontWeight: 900, fontSize: 168 * u, lineHeight: 1, color: p.accent, transform: `scale(${0.6 + 0.4 * a}) translateX(${shake}px)`,
            textShadow: `0 ${8 * u}px 0 rgba(0,0,0,0.3)`, fontVariantNumeric: 'tabular-nums'}}>{countText(value, k)}</div>
          {label ? <div style={{fontFamily: FONT, fontWeight: 800, fontSize: 54 * u, color: p.text, opacity: Math.min(a, 1), maxWidth: 1400 * u}}>{label}</div> : null}
          {sub ? <div style={{fontFamily: FONT, fontWeight: 700, fontSize: 36 * u, color: p.muted, opacity: Math.min(b, 1), transform: `translateY(${(1 - Math.min(b, 1)) * 20 * u}px)`, maxWidth: 1300 * u}}>{sub}</div> : null}
        </div>
      </StageBox>
      <Footnote text={source} p={p} />
    </AbsoluteFill>
  );
};

// icons: {title, total: 20, highlight: 5, icon: "🧍", label: "1 in 4 adults"}  beats: [grid, highlight]
export const Icons: React.FC<P> = ({p, title, kicker, total = 20, highlight = 1, icon = '🧍', label, beats, seconds, source, base}) => {
  const f = useCurrentFrame(); const {fps, u, portrait} = useStage();
  const cols = total <= 10 ? total : total <= 20 ? 10 : total <= 50 ? 10 : 20; const rows = Math.ceil(total / cols);
  const size = Math.min((portrait ? 960 : 1500) / cols, (portrait ? 520 : 520) / rows) * u * 0.92;
  const t0 = beatAt(beats, 0, 2, seconds, 0.3, 0.2); const t1 = beats?.[1] ?? t0 + 0.9 + total * 0.02;
  const la = pop(f, fps, t1 + 0.3);
  return (
    <AbsoluteFill>
      <Backdrop p={p} seed={11} />
      <StageBox>
        <Heading title={title} kicker={kicker} p={p} />
        <div style={{flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 30 * u}}>
          <div style={{display: 'grid', gridTemplateColumns: `repeat(${cols}, ${size}px)`, gap: size * 0.08}}>
            {Array.from({length: total}).map((_, i) => {
              const a = pop(f, fps, t0 + i * 0.02, {damping: 12}); const on = i < highlight; const h = on ? prog(f, fps, t1 + i * 0.03, 0.3) : 0;
              return <div key={i} style={{transform: `scale(${a * (1 + h * 0.12)})`, filter: on && h > 0.5 ? `drop-shadow(0 0 ${10 * u}px ${p.accent})` : `grayscale(${1 - h}) opacity(${0.35 + 0.65 * h})`}}>
                <Icon icon={icon} size={size} base={base} />
              </div>;
            })}
          </div>
          {label ? <div style={{fontFamily: FONT, fontWeight: 900, fontSize: 64 * u, color: p.accent, transform: `scale(${la})`}}>{label}</div> : null}
        </div>
      </StageBox>
      <Footnote text={source} p={p} />
    </AbsoluteFill>
  );
};
