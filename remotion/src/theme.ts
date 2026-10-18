// Palette and shared prop types. A series overrides the palette through style.json (see infogen/style.py).
export type Palette = {
  bg: string; bg2: string; text: string; muted: string; ink: string; panel: string;
  accent: string; accent2: string; good: string; bad: string; land: string; landHi: string; ocean: string; border: string;
  series: string[];
};

export const DEFAULT_PALETTE: Palette = {
  bg: '#0E2740', bg2: '#17507A', text: '#FFFFFF', muted: '#A9C1D6', ink: '#11233A', panel: '#FFFFFF',
  accent: '#FFC93C', accent2: '#FF5A5F', good: '#3DDC97', bad: '#FF5A5F',
  land: '#2C6A8C', landHi: '#FFC93C', ocean: '#0B1F33', border: '#0B1F33',
  series: ['#FFC93C', '#FF5A5F', '#3DDC97', '#4CC9F0', '#B388EB', '#FF9F1C', '#F15BB5', '#9EF01A'],
};

export const FONT = "'Montserrat', 'DejaVu Sans', 'Noto Color Emoji', sans-serif";

export type SceneProps = {
  type: string;
  width: number; height: number; fps: number; seconds: number;
  base?: string;                 // http base the image paths are served from (set by the renderer)
  palette?: Partial<Palette>;
  beats?: number[];              // reveal times in seconds, one per revealable item, in template order
  cut?: 'whip' | 'hard' | 'fade';
  source?: string;               // data source shown small at the bottom
  [k: string]: any;
};

export const pal = (p?: Partial<Palette>): Palette => ({...DEFAULT_PALETTE, ...(p || {})});

// image path from the run folder -> URL the browser can load
export const url = (base: string | undefined, p?: string) => {
  if (!p) return undefined;
  if (/^(https?:|data:)/.test(p)) return p;
  return (base || '/') + p.split('/').map(encodeURIComponent).join('/');
};

export const isImage = (s?: string) => !!s && /\.(png|jpe?g|webp|gif|svg)$/i.test(s);
