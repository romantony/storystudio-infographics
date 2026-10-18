// map: real country shapes (Natural Earth 1:50m via world-atlas, public domain), highlighted countries, pins and routes.
//   focus: {countries: [...]} | {bbox: [[lonW, latS], [lonE, latN]]} | "world"      (default: the highlighted countries, else the world)
//   highlight: ["Ukraine", {country: "Russia", color: "#FF5A5F", label: "RUSSIA"}]
//   pins: [{lon, lat, label, icon}]       routes: [{from: [lon, lat], to: [lon, lat], icon: "✈️", color}]
// Beats: highlights, then pins, then routes.
import React, {useMemo} from 'react';
import {AbsoluteFill, Easing, Img, useCurrentFrame} from 'remotion';
import {geoArea, geoCentroid, geoInterpolate, geoMercator, geoNaturalEarth1, geoPath} from 'd3-geo';
import {feature} from 'topojson-client';
import world from 'world-atlas/countries-50m.json';
import {FONT, Palette, SceneProps} from '../theme';
import {Footnote, Heading, beatAt, pop, prog, useStage} from '../kit';

const ALL: any = feature(world as any, (world as any).objects.countries);
const norm = (s: string) => s.toLowerCase().replace(/[^a-z]/g, '');
const ALIAS: Record<string, string> = {
  usa: 'unitedstatesofamerica', us: 'unitedstatesofamerica', unitedstates: 'unitedstatesofamerica', america: 'unitedstatesofamerica',
  uk: 'unitedkingdom', britain: 'unitedkingdom', greatbritain: 'unitedkingdom', england: 'unitedkingdom',
  drc: 'demrepcongo', democraticrepublicofthecongo: 'demrepcongo', congokinshasa: 'demrepcongo', southkorea: 'southkorea', korea: 'southkorea',
  northkorea: 'northkorea', czechrepublic: 'czechia', ivorycoast: 'cotedivoire', uae: 'unitedarabemirates', bosnia: 'bosniaandherz',
  southsudan: 'ssudan', centralafricanrepublic: 'centralafricanrep', dominicanrepublic: 'dominicanrep', eswatini: 'eswatini', swaziland: 'eswatini',
  burma: 'myanmar', holland: 'netherlands', palestine: 'palestine', taiwan: 'taiwan', vatican: 'vatican',
};
// the main landmass only (France without French Guiana, the USA without Hawaii), for framing and label placement
export const mainland = (f: any) => {
  if (!f || f.geometry.type !== 'MultiPolygon') return f;
  const parts = f.geometry.coordinates.map((c: any) => ({c, a: geoArea({type: 'Polygon', coordinates: c} as any)}));
  const mx = Math.max(...parts.map((q: any) => q.a));
  return {...f, geometry: {type: 'MultiPolygon', coordinates: parts.filter((q: any) => q.a >= mx * 0.3).map((q: any) => q.c)}};
};
export const findCountry = (name: string) => {
  const n = ALIAS[norm(name)] || norm(name);
  return ALL.features.find((f: any) => norm(f.properties.name) === n) || ALL.features.find((f: any) => norm(f.properties.name).startsWith(n));
};

export const MapScene: React.FC<SceneProps & {p: Palette}> = ({p, title, kicker, focus, highlight = [], pins = [], routes = [], beats, seconds, source}) => {
  // note: the base map is a PNG of the projected world, see useMemo below
  const f = useCurrentFrame(); const {fps, u, width, height, portrait} = useStage();
  const hl = highlight.map((h: any) => (typeof h === 'string' ? {country: h} : h)).map((h: any) => ({...h, feat: findCountry(h.country)}));
  const box = portrait ? {x: 30 * u, y: height * 0.15, w: width - 60 * u, h: width * 0.95} : {x: 40 * u, y: (title ? 150 : 40) * u, w: width - 80 * u, h: height - (title ? 210 : 100) * u};
  const {proj, base: worldImg, hi} = useMemo(() => {
    let target: any;
    if (focus === 'world' || (!focus && !hl.some((h: any) => h.feat) && !pins.length && !routes.length)) target = {type: 'Sphere'};
    else if (focus?.bbox) {
      const [[w, s], [e, n]] = focus.bbox;
      target = {type: 'Feature', geometry: {type: 'MultiPoint', coordinates: [[w, s], [e, n], [w, n], [e, s]]}};
    } else {
      const feats = (focus?.countries ? focus.countries.map(findCountry) : hl.map((h: any) => h.feat)).filter(Boolean).map(mainland);
      const pts = [...pins.map((q: any) => [q.lon, q.lat]), ...routes.flatMap((r: any) => [r.from, r.to])];
      target = {type: 'FeatureCollection', features: [...feats, ...(pts.length ? [{type: 'Feature', geometry: {type: 'MultiPoint', coordinates: pts}}] : [])]};
    }
    const wide = target.type === 'Sphere' || (focus?.bbox && Math.abs(focus.bbox[1][0] - focus.bbox[0][0]) > 140);
    const pr = (wide ? geoNaturalEarth1() : geoMercator());
    const pad = (wide ? 20 : 110) * u;
    pr.fitExtent([[box.x + pad, box.y + pad], [box.x + box.w - pad, box.y + box.h - pad]], target);
    const gp = geoPath(pr);
    // The projection never changes during the scene (the camera is a transform), so the world is drawn once, to a
    // canvas, and every frame only moves that picture. Drawing 240 detailed outlines as SVG on every frame is ~50x slower.
    const cv = document.createElement('canvas'); cv.width = width; cv.height = height; const ctx = cv.getContext('2d')!;
    ctx.fillStyle = p.ocean; ctx.fill(new Path2D(gp({type: 'Sphere'} as any) || ''));
    ctx.fillStyle = p.land; ctx.strokeStyle = p.border; ctx.lineWidth = 1.4 * u; ctx.lineJoin = 'round';
    for (const ft of ALL.features) { const d = gp(ft); if (d) { const p2 = new Path2D(d); ctx.fill(p2); ctx.stroke(p2); } }
    return {proj: pr, base: cv.toDataURL('image/png'), hi: hl.map((h: any) => (h.feat ? gp(h.feat) || '' : ''))};
  }, [JSON.stringify(focus), JSON.stringify(highlight), JSON.stringify(pins), JSON.stringify(routes), width, height, JSON.stringify(p)]);
  // slow push-in on the focus
  const z = 0.82 + 0.18 * prog(f, fps, 0, Math.min(2.2, seconds * 0.5), Easing.out(Easing.cubic)) + 0.03 * (f / Math.max(1, seconds * fps));
  const cx = box.x + box.w / 2, cy = box.y + box.h / 2;
  const total = hl.length + pins.length + routes.length;
  const at = (i: number) => beatAt(beats, i, total, seconds, 0.6, 0.65);
  return (
    <AbsoluteFill style={{background: p.ocean, overflow: 'hidden'}}>
      <AbsoluteFill style={{backgroundImage: `radial-gradient(circle at 50% 40%, ${p.bg2}55 0%, transparent 70%)`}} />
      <Img src={worldImg} style={{position: 'absolute', left: 0, top: 0, width, height, transformOrigin: `${cx}px ${cy}px`, transform: `scale(${z})`}} />
      <svg width={width} height={height} style={{position: 'absolute'}}>
        <g transform={`translate(${cx},${cy}) scale(${z}) translate(${-cx},${-cy})`}>
          {hl.map((h: any, i: number) => {
            if (!h.feat) return null;
            const k = prog(f, fps, at(i), 0.5);
            return <path key={'h' + i} d={hi[i]} fill={h.color || p.landHi} fillOpacity={k} stroke="#fff" strokeWidth={3 * u * k / z} />;
          })}
          {routes.map((r: any, i: number) => {
            const t = at(hl.length + pins.length + i); const k = prog(f, fps, t, Math.min(2, seconds * 0.35), Easing.inOut(Easing.cubic));
            const ip = geoInterpolate(r.from, r.to); const N = 64; const pts: [number, number][] = [];
            for (let s = 0; s <= N * k; s++) { const q = proj(ip(s / N)); if (q) pts.push(q as [number, number]); }
            if (pts.length < 2) return null;
            const d = 'M' + pts.map((q) => q.join(',')).join('L'); const head = pts[pts.length - 1];
            return (
              <g key={'r' + i}>
                <path d={d} fill="none" stroke="#fff" strokeWidth={14 * u / z} strokeLinecap="round" opacity={0.9} />
                <path d={d} fill="none" stroke={r.color || p.accent2} strokeWidth={8 * u / z} strokeLinecap="round" strokeDasharray={r.dashed ? `${20 * u / z} ${16 * u / z}` : undefined} />
                {r.icon && k > 0 ? <text x={head[0]} y={head[1]} textAnchor="middle" dominantBaseline="central" style={{fontSize: 60 * u / z, fontFamily: "'Noto Color Emoji'"}}>{r.icon}</text> : null}
              </g>
            );
          })}
        </g>
      </svg>
      {/* labels and pins are drawn unscaled on top, at the zoomed positions */}
      {hl.map((h: any, i: number) => {
        if (!h.feat || h.label === '') return null;
        const c = h.at ? proj(h.at) : proj(geoCentroid(mainland(h.feat))); if (!c) return null;
        const a = pop(f, fps, at(i) + 0.15);
        return <div key={'l' + i} style={{position: 'absolute', left: cx + (c[0] - cx) * z, top: cy + (c[1] - cy) * z, transform: `translate(-50%,-50%) scale(${a})`,
          fontFamily: FONT, fontWeight: 900, fontSize: 40 * u, color: '#fff', textTransform: 'uppercase', letterSpacing: 2 * u, whiteSpace: 'nowrap',
          textShadow: `0 0 ${10 * u}px rgba(0,0,0,0.9), 0 ${3 * u}px 0 rgba(0,0,0,0.6)`}}>{h.label ?? h.country}</div>;
      })}
      {pins.map((q: any, i: number) => {
        const c = proj([q.lon, q.lat]); if (!c) return null;
        const a = pop(f, fps, at(hl.length + i), {damping: 9}); const ring = ((f / fps) * 1.2 + i * 0.3) % 1;
        const x = cx + (c[0] - cx) * z, y = cy + (c[1] - cy) * z;
        return (
          <div key={'p' + i} style={{position: 'absolute', left: x, top: y}}>
            <div style={{position: 'absolute', width: 90 * u, height: 90 * u, left: -45 * u, top: -45 * u, borderRadius: '50%', border: `${5 * u}px solid ${p.accent2}`,
              transform: `scale(${a * (0.3 + ring)})`, opacity: (1 - ring) * Math.min(a, 1)}} />
            <div style={{position: 'absolute', width: 30 * u, height: 30 * u, left: -15 * u, top: -15 * u, borderRadius: '50%', background: p.accent2, border: `${6 * u}px solid #fff`, transform: `scale(${a})`}} />
            {q.label ? <div style={{position: 'absolute', left: 0, top: -40 * u, transform: `translate(-50%,-100%) scale(${a})`, transformOrigin: '50% 100%', background: p.panel, color: p.ink,
              fontFamily: FONT, fontWeight: 800, fontSize: 34 * u, padding: `${8 * u}px ${18 * u}px`, borderRadius: 12 * u, whiteSpace: 'nowrap', boxShadow: `0 ${6 * u}px 0 rgba(0,0,0,0.3)`}}>
              {q.icon ? <span style={{fontFamily: "'Noto Color Emoji'", marginRight: 10 * u}}>{q.icon}</span> : null}{q.label}</div> : null}
          </div>
        );
      })}
      {title || kicker ? <div style={{position: 'absolute', left: 0, right: 0, top: portrait ? height * 0.11 - 110 * u : 30 * u}}><Heading title={title} kicker={kicker} p={p} /></div> : null}
      <Footnote text={source || 'Natural Earth (map data)'} p={p} />
    </AbsoluteFill>
  );
};
