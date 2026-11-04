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
const minds = await (await fetch(`${BASE}/api/minds`)).json();
const target = minds.items[0];
await send('Page.navigate', { url: `${BASE}/?chat=${target.id}&v=${Date.now()}` });
await sleep(3200);
await shot('chat-vector');
const info = await ev(`({ view: state.view, msgs: document.querySelectorAll('#chat-stream .msg').length, avatar: !!document.querySelector('#chat-avatar-canvas')?.width, errs: window.__errs })`);
console.log(JSON.stringify(info));
// 说话状态
await ev(`document.querySelector('#btn-playaudio') && document.querySelector('#btn-playaudio').click()`);
await sleep(800);
await shot('chat-vector-speaking');
const errs = events.filter(e => e.method === 'Runtime.exceptionThrown').map(e => e.params.exceptionDetails.exception?.description);
console.log('errors', errs.length, errs.slice(0, 3));
ws.close();
