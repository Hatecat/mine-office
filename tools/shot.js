// Captura una página con Chromium sin interfaz (WebGL por software).
// Uso: node tools/shot.js <url> <salida.png> [espera_ms=5000] [ancho=1300] [alto=850]
const path = require('path');
const { chromium } = require(path.join(__dirname, 'node_modules', 'playwright-core'));
(async () => {
  const [url, out, wait = '5000', w = '1300', h = '850'] = process.argv.slice(2);
  if (!url || !out) { console.error('uso: node tools/shot.js <url> <salida.png> [espera_ms]'); process.exit(2); }
  const b = await chromium.launch({
    executablePath: process.env.HOME + '/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  const p = await b.newPage({ viewport: { width: +w, height: +h } });
  p.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') console.log('console:', m.type(), m.text()); });
  p.on('pageerror', e => console.log('pageerror:', e.message));
  await p.goto(url);
  await p.waitForTimeout(+wait);
  if (process.env.EVAL) { await p.evaluate(process.env.EVAL); await p.waitForTimeout(3000); }
  if (process.env.CLICK) { await p.click(process.env.CLICK); await p.waitForTimeout(2500); }
  await p.screenshot({ path: out });
  await b.close();
  console.log('ok', out);
})();
