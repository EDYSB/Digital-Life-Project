import fs from 'node:fs';
const CDP = '9223', BASE = 'http://127.0.0.1:8017';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let page;
try { page = await (await fetch(`http://127.0.0.1:${CDP}/json/new?about:blank`, { method: 'PUT' })).json(); }
catch { page = await (await fetch(`http://127.0.0.1:${CDP}/json/new?about:blank`)).json(); }
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener('open', r));
let id = 0; const pend = new Map(); const events = [];
ws.addEventListener('message', ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pend.has(m.id)) { const p = pend.get(m.id); pend.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); }
  else if (m.method) events.push(m);
});
const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pend.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expression, awaitPromise = true) => {
  const r = await send('Runtime.evaluate', { expression, awaitPromise, returnByValue: true });
  if (r.exceptionDetails) return { JS_ERROR: r.exceptionDetails.exception?.description };
  return r.result?.value;
};
const shot = async (name) => {
  const r = await send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync(`out/shots/${name}.png`, Buffer.from(r.data, 'base64'));
  console.log('shot', name);
};
await send('Runtime.enable'); await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '/?v=' + Date.now() });
await sleep(2200);

await ev(`document.querySelector('#btn-admin').click()`);
await sleep(2500);
const info = await ev(`(() => ({
  view: state.view,
  items: document.querySelectorAll('#admin-list .admin-item').length,
  totals: document.querySelectorAll('#admin-totals div').length,
  name: document.querySelector('#ad-name')?.textContent,
  curve: document.querySelector('#admin-curve')?.width,
  hist: document.querySelector('#admin-hist')?.width,
  mood: document.querySelector('#admin-mood')?.width,
  star: document.querySelector('#admin-starmap')?.width,
  half: document.querySelector('#ad-half')?.textContent,
  rows: document.querySelectorAll('#ad-lists .ad-row').length,
}))()`);
console.log('admin', JSON.stringify(info));
await shot('admin-dashboard');

// 切换第二个生命
await ev(`document.querySelectorAll('#admin-list .admin-item')[1]?.click()`);
await sleep(1600);
console.log('second', await ev(`document.querySelector('#ad-name')?.textContent`));
await shot('admin-second');

// 时间轴拉到 +30 天
await ev(`(() => { const r = document.querySelector('#admin-days-range'); r.value = 30; r.dispatchEvent(new Event('input', { bubbles: true })); })()`);
await sleep(900);
await shot('admin-30days');
console.log('days', await ev(`document.querySelector('#ad-days')?.textContent`));

const errs = events.filter(e => e.method === 'Runtime.exceptionThrown')
  .map(e => e.params.exceptionDetails.exception?.description || e.params.exceptionDetails.text);
console.log('JS errors', errs.length);
errs.slice(0, 5).forEach(e => console.log(' !', e));
ws.close();
