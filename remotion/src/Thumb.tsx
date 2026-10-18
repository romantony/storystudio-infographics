// Thumbnail (1280x720 still): an illustration, an optional cut-out character large on one side, and 1 to 3 lines of huge outlined text.
// Text is drawn here rather than by an image model, so it is always spelled as written.
//   {image, cast: {src, side: "left" | "right", h}, lines: ["WHAT IF", "THE AI BUBBLE", "BURSTS?"], badge: "DAY BY DAY", arrow: true}
import React, {useEffect, useState} from 'react';
import {AbsoluteFill, Img, continueRender, delayRender} from 'remotion';
import {FONT, SceneProps, pal, url} from './theme';

export const Thumb: React.FC<SceneProps> = ({image, cast, lines = [], badge, base, palette, width, height}) => {
  const [h] = useState(() => delayRender('fonts'));
  useEffect(() => { document.fonts.load('900 80px Montserrat').then(() => continueRender(h)).catch(() => continueRender(h)); }, [h]);
  const p = pal(palette); const u = height / 720; const side = cast?.side || 'right';
  const colors = [p.accent, '#FFFFFF', p.accent2];
  const longest = Math.max(...lines.map((l: string) => l.length), 1);
  const size = Math.min(128, 1150 / longest) * u * (cast ? 0.92 : 1.1);
  return (
    <AbsoluteFill style={{background: p.bg, overflow: 'hidden'}}>
      {image ? <Img src={url(base, image)!} style={{width: '100%', height: '100%', objectFit: 'cover', filter: 'saturate(1.25) contrast(1.08)'}} /> : null}
      <AbsoluteFill style={{background: `linear-gradient(${side === 'right' ? '90deg' : '270deg'}, rgba(0,0,0,0.72) 0%, rgba(0,0,0,0.35) 50%, rgba(0,0,0,0) 75%)`}} />
      {cast?.src ? <Img src={url(base, cast.src)!} style={{position: 'absolute', bottom: -10 * u, [side]: 10 * u, height: (cast.h ?? 0.98) * height,
        filter: `drop-shadow(0 0 ${14 * u}px rgba(255,255,255,0.85)) drop-shadow(0 ${10 * u}px ${18 * u}px rgba(0,0,0,0.6))`}} /> : null}
      <div style={{position: 'absolute', top: 0, bottom: 0, [side === 'right' ? 'left' : 'right']: 40 * u, width: cast ? '62%' : '92%', display: 'flex', flexDirection: 'column',
        justifyContent: 'center', alignItems: side === 'right' ? 'flex-start' : 'flex-end', gap: 4 * u}}>
        {badge ? <div style={{background: p.accent2, color: '#fff', fontFamily: FONT, fontWeight: 900, fontSize: 40 * u, padding: `${6 * u}px ${18 * u}px`, borderRadius: 10 * u,
          transform: 'rotate(-3deg)', marginBottom: 10 * u, boxShadow: `0 ${6 * u}px 0 rgba(0,0,0,0.4)`}}>{badge}</div> : null}
        {lines.map((l: string, i: number) => (
          <div key={i} style={{fontFamily: FONT, fontWeight: 900, fontSize: size, lineHeight: 1.0, color: colors[i % 3], textTransform: 'uppercase',
            WebkitTextStroke: `${size * 0.09}px #000`, paintOrder: 'stroke fill', textShadow: `0 ${8 * u}px 0 #000, 0 0 ${24 * u}px rgba(0,0,0,0.6)`,
            textAlign: side === 'right' ? 'left' : 'right'}}>{l}</div>
        ))}
      </div>
    </AbsoluteFill>
  );
};
