import fs from 'node:fs';

const CDP = '9223';
const BASE = 'http://127.0.0.1:8017';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const list = await (await fetch(`http://127.0.0.1:${CDP}/json/list`)).json();
const page = list.find(t => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener('open', r));
let id = 0;
const pending = new Map();
const events = [];
ws.addEventListener('message', ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const p = pending.get(m.id); pending.delete(m.id);
    m.error ? p.rej(new Error(m.error.message)) : p.res(m.result);
  } else if (m.method) events.push(m);
});
const send = (method, params = {}) => new Promise((res, rej) => {
  const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params }));
});
const ev = async (expression, awaitPromise = true) => {
  const r = await send('Runtime.evaluate', { expression, awaitPromise, returnByValue: true });
  if (r.exceptionDetails) return { JS_ERROR: r.exceptionDetails.exception?.description || r.exceptionDetails.text };
  return r.result?.value;
};
const shot = async name => {
  const r = await send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync(`out/shots/${name}.png`, Buffer.from(r.data, 'base64'));
  console.log('  shot →', name);
};

await send('Runtime.enable');
await send('Page.enable');
await send('Log.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });

console.log('→ 档案库 / 对比');
await send('Page.navigate', { url: `${BASE}/?view=library` });
await sleep(500);
await ev(`document.querySelector('#btn-library').click()`);
await sleep(1500);
await ev(`document.querySelector('#btn-compare-mode').click()`);
await sleep(300);
await ev(`document.querySelectorAll('#library-grid .mind-card')[0].click()`);
await sleep(200);
await ev(`document.querySelectorAll('#library-grid .mind-card')[1].click()`);
await sleep(400);
const ready = await ev(`!document.querySelector('#btn-do-compare').disabled`);
console.log('  compare ready:', ready);
await shot('11-compare-pick');
await ev(`document.querySelector('#btn-do-compare').click()`);
await sleep(2200);
const cmp = await ev(`(() => ({
  active: document.querySelector('#view-compare').classList.contains('active'),
  score: document.querySelector('#cmp-score').textContent,
  rows: document.querySelectorAll('#compare-diffs .diff-row').length,
  title: document.querySelector('#cmp-title').textContent,
}))()`);
console.log('  compare:', JSON.stringify(cmp));
await shot('12-compare');

console.log('→ 音景');
const minds = await (await fetch(`${BASE}/api/minds`)).json();
const target = minds.items[0];
await send('Page.navigate', { url: `${BASE}/?mind=${target.id}` });
await sleep(2200);
await ev(`document.querySelector('#btn-talk').click()`);
await sleep(600);
await ev(`document.querySelector('#btn-playaudio').click()`);
await sleep(1200);
const audio = await ev(`({ playing: Audio.playing, state: Audio.ctx && Audio.ctx.state, nodes: Audio.nodes.length })`);
console.log('  audio:', JSON.stringify(audio));
await ev(`Audio.stop()`);

console.log('→ 导出');
await ev(`document.querySelector('#btn-back-dossier').click()`);
await sleep(500);
await ev(`document.querySelector('#btn-md').click()`);
await sleep(1200);
const dl = await ev(`({ toast: document.querySelector('#toast').textContent, err: !document.querySelector('#toast').classList.contains('err') })`);
console.log('  export:', JSON.stringify(dl));

const errs = events.filter(e => e.method === 'Runtime.exceptionThrown')
  .map(e => e.params.exceptionDetails.exception?.description || e.params.exceptionDetails.text);
console.log('\nJS 错误数:', errs.length);
errs.slice(0, 8).forEach(e => console.log('  !', e));
ws.close();
