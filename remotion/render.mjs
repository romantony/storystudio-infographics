// Render many scenes with one browser: node render.mjs jobs.json
// jobs.json: {"concurrency": 2, "jobs": [{"id": "Scene" | "Thumb", "props": {...}, "out": "/abs/path.mp4" | ".jpg" | ".png", "still": false}]}
// Video jobs are silent H.264 (audio is mixed by infogen). Each job writes to a temp name and renames, so a killed run leaves no half file.
// Env: INFOGEN_BROWSER (path to a Chrome/headless-shell binary; default: Remotion's own), INFOGEN_RENDER_LOG (info|verbose|error)
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {openBrowser, renderMedia, renderStill, selectComposition} from '@remotion/renderer';

const here = path.dirname(fileURLToPath(import.meta.url));
const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const serveUrl = path.join(here, 'bundle');
if (!fs.existsSync(serveUrl)) { console.error('no bundle: run npx remotion bundle src/index.ts --out-dir bundle in ' + here); process.exit(2); }
const browserExecutable = process.env.INFOGEN_BROWSER || null;
const logLevel = process.env.INFOGEN_RENDER_LOG || 'error';
const browser = await openBrowser('chrome', {browserExecutable, logLevel, chromiumOptions: {gl: 'swangle'}});
let failed = 0;
for (const [i, j] of spec.jobs.entries()) {
  const t0 = Date.now();
  try {
    const composition = await selectComposition({serveUrl, id: j.id || 'Scene', inputProps: j.props, puppeteerInstance: browser, browserExecutable, logLevel});
    const ext = path.extname(j.out); const tmp = j.out.slice(0, -ext.length) + '.part' + ext;
    if (j.still) {
      await renderStill({composition, serveUrl, output: tmp, inputProps: j.props, puppeteerInstance: browser, browserExecutable, logLevel,
        frame: j.frame ?? composition.durationInFrames - 1, imageFormat: ext === '.png' ? 'png' : 'jpeg', jpegQuality: 92});
    } else {
      await renderMedia({composition, serveUrl, codec: 'h264', outputLocation: tmp, inputProps: j.props, puppeteerInstance: browser, browserExecutable, logLevel,
        concurrency: spec.concurrency || null, crf: 18, pixelFormat: 'yuv420p', muted: true, imageFormat: 'jpeg', jpegQuality: 90, x264Preset: 'veryfast'});
    }
    fs.renameSync(tmp, j.out);
    console.log(JSON.stringify({i, out: j.out, ok: true, seconds: (Date.now() - t0) / 1000}));
  } catch (e) {
    failed += 1;
    console.log(JSON.stringify({i, out: j.out, ok: false, error: String(e && e.message || e).slice(0, 600)}));
  }
}
await browser.close({silent: true});
process.exit(failed ? 1 : 0);
