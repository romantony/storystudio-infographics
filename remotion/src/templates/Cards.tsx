// title, timecard, text, endcard, clip
import React from 'react';
import {AbsoluteFill, Img, Loop, OffthreadVideo, useCurrentFrame} from 'remotion';
import {FONT, Palette, SceneProps, url} from '../theme';
import {Backdrop, Icon, StageBox, pop, prog, useStage} from '../kit';
import {Illustration} from './Illustration';

type P = SceneProps & {p: Palette};

// title: chapter card {kicker: "PART 2", title, sub, icon, image (optional, shown darkened behind)}
export const TitleCard: React.FC<P> = (props) => {
  const {p, kicker, title = '', sub, icon, image, base} = props;
  const f = useCurrentFrame(); const {fps, u} = useStage();
  const a = pop(f, fps, 0.1, {damping: 12}), b = pop(f, fps, 0.35, {damping: 14}), line = prog(f, fps, 0.3, 0.6);
  return (
    <AbsoluteFill>
      {image ? <><Illustration {...props} cast={[]} callouts={[]} timecard={undefined} move="zoom_in" /><AbsoluteFill style={{background: `${p.bg}D0`}} /></> : <Backdrop p={p} seed={3} />}
      <StageBox>
        <div style={{flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center'}}>
          {icon ? <div style={{transform: `scale(${a})`, marginBottom: 20 * u}}><Icon icon={icon} size={150 * u} base={base} /></div> : null}
          {kicker ? <div style={{fontFamily: FONT, fontWeight: 800, fontSize: 40 * u, letterSpacing: 8 * u, color: p.accent, opacity: Math.min(a, 1)}}>{kicker}</div> : null}
          <div style={{fontFamily: FONT, fontWeight: 900, fontSize: (title.length > 28 ? 84 : 110) * u, lineHeight: 1.04, color: p.text, textTransform: 'uppercase',
            transform: `scale(${0.7 + 0.3 * a})`, opacity: Math.min(a, 1), textShadow: `0 ${8 * u}px 0 rgba(0,0,0,0.3)`, maxWidth: 1500 * u}}>{title}</div>
          <div style={{height: 10 * u, width: 360 * u * line, background: p.accent, borderRadius: 5 * u, margin: `${24 * u}px 0`}} />
          {sub ? <div style={{fontFamily: FONT, fontWeight: 700, fontSize: 42 * u, color: p.muted, opacity: Math.min(b, 1), maxWidth: 1300 * u}}>{sub}</div> : null}
        </div>
      </StageBox>
    </AbsoluteFill>
  );
};

// timecard: the "hour by hour" stinger {text: "HOUR 3", sub: "09:45 AM, Washington"}
export const TimeCard: React.FC<P> = ({p, text = '', sub, kicker}) => {
  const f = useCurrentFrame(); const {fps, u} = useStage();
  const a = pop(f, fps, 0.05, {damping: 8, stiffness: 220}); const b = pop(f, fps, 0.3);
  const sec = (f / fps) * 360; const R = 80 * u;
  return (
    <AbsoluteFill style={{background: p.ink}}>
      <AbsoluteFill style={{backgroundImage: `repeating-linear-gradient(90deg, rgba(255,255,255,0.04) 0 ${2 * u}px, transparent ${2 * u}px ${60 * u}px)`}} />
      <StageBox>
        <div style={{flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 20 * u}}>
          <svg width={2 * R + 20 * u} height={2 * R + 20 * u} style={{transform: `scale(${a})`}}>
            <g transform={`translate(${R + 10 * u},${R + 10 * u})`}>
              <circle r={R} fill="none" stroke={p.text} strokeWidth={10 * u} />
              <line x1={0} y1={0} x2={0} y2={-R * 0.55} stroke={p.text} strokeWidth={10 * u} strokeLinecap="round" transform={`rotate(${sec / 12})`} />
              <line x1={0} y1={0} x2={0} y2={-R * 0.8} stroke={p.accent} strokeWidth={6 * u} strokeLinecap="round" transform={`rotate(${sec})`} />
            </g>
          </svg>
          {kicker ? <div style={{fontFamily: FONT, fontWeight: 800, fontSize: 36 * u, letterSpacing: 8 * u, color: p.muted}}>{kicker}</div> : null}
          <div style={{fontFamily: FONT, fontWeight: 900, fontSize: 150 * u, color: p.accent, letterSpacing: 4 * u, transform: `scale(${a})`, lineHeight: 1}}>{text}</div>
          {sub ? <div style={{fontFamily: FONT, fontWeight: 800, fontSize: 50 * u, color: p.text, opacity: Math.min(b, 1), transform: `translateY(${(1 - Math.min(b, 1)) * 20 * u}px)`}}>{sub}</div> : null}
        </div>
      </StageBox>
    </AbsoluteFill>
  );
};

// text: one big statement or a quotation {text, attribution, quote: true, icon}
export const TextCard: React.FC<P> = ({p, text = '', attribution, quote, icon, base}) => {
  const f = useCurrentFrame(); const {fps, u} = useStage();
  const words = text.split(' '); const a = pop(f, fps, 0.1);
  return (
    <AbsoluteFill>
      <Backdrop p={p} seed={21} />
      <StageBox>
        <div style={{flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', gap: 24 * u}}>
          {icon ? <div style={{transform: `scale(${a})`}}><Icon icon={icon} size={140 * u} base={base} /></div> : null}
          <div style={{fontFamily: FONT, fontWeight: 900, fontSize: (text.length > 90 ? 58 : 74) * u, lineHeight: 1.18, color: p.text, maxWidth: 1500 * u}}>
            {quote ? <span style={{color: p.accent}}>“</span> : null}
            {words.map((w, i) => { const k = pop(f, fps, 0.15 + i * 0.06, {damping: 16}); return <span key={i} style={{display: 'inline-block', opacity: Math.min(k, 1), transform: `translateY(${(1 - Math.min(k, 1)) * 20 * u}px)`, marginRight: 18 * u}}>{w}</span>; })}
            {quote ? <span style={{color: p.accent}}>”</span> : null}
          </div>
          {attribution ? <div style={{fontFamily: FONT, fontWeight: 800, fontSize: 40 * u, color: p.accent, opacity: Math.min(pop(f, fps, 0.4 + words.length * 0.06), 1)}}>— {attribution}</div> : null}
        </div>
      </StageBox>
    </AbsoluteFill>
  );
};

// endcard: {series, next, lines: [...]}
export const EndCard: React.FC<P> = ({p, series = '', next, lines = []}) => {
  const f = useCurrentFrame(); const {fps, u, portrait} = useStage();
  const items: [string, string, string][] = [['👍', 'LIKE', '#50AAFF'], ['🔔', portrait ? 'FOLLOW' : 'SUBSCRIBE', '#FF3C3C'], ['📤', 'SHARE', '#46DC78']];
  return (
    <AbsoluteFill>
      <Backdrop p={p} seed={29} />
      <StageBox>
        <div style={{flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 40 * u}}>
          <div style={{display: 'flex', gap: (portrait ? 50 : 120) * u}}>
            {items.map(([e, l, c], i) => { const a = pop(f, fps, 0.1 + i * 0.15, {damping: 8}); return (
              <div key={i} style={{display: 'flex', flexDirection: 'column', alignItems: 'center', transform: `scale(${a})`}}>
                <Icon icon={e} size={(portrait ? 150 : 170) * u} />
                <div style={{fontFamily: FONT, fontWeight: 900, fontSize: (portrait ? 40 : 52) * u, color: c, WebkitTextStroke: `${2 * u}px #000`}}>{l}</div>
              </div>); })}
          </div>
          {series ? <div style={{fontFamily: FONT, fontWeight: 900, fontSize: 64 * u, color: p.accent, textAlign: 'center'}}>{series}</div> : null}
          {next ? <div style={{fontFamily: FONT, fontWeight: 800, fontSize: 44 * u, color: p.text, textAlign: 'center', opacity: Math.min(pop(f, fps, 0.6), 1)}}>{next}</div> : null}
          {lines.map((l: string, i: number) => <div key={i} style={{fontFamily: FONT, fontWeight: 600, fontSize: 28 * u, color: p.muted, textAlign: 'center'}}>{l}</div>)}
        </div>
      </StageBox>
    </AbsoluteFill>
  );
};

// clip: a video (a Wan/LTX animation of an illustration, say) filling the frame; loops while the scene lasts (a pause-free restart, no frozen frame)
export const Clip: React.FC<P> = ({p, src, base, clip_seconds = 5, timecard}) => {
  const {fps} = useStage(); const cf = Math.max(1, Math.floor(clip_seconds * fps) - 1);
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <Loop durationInFrames={cf}>
        <OffthreadVideo src={url(base, src)!} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />
      </Loop>
    </AbsoluteFill>
  );
};
