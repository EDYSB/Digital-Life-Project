import fs from 'node:fs';
const CDP = '9223', BASE = 'http://127.0.0.1:8017';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let page;
try { page = await (await fetch(`http://127.0.0.1:${CDP}/json/new?about:blank`, { method: 'PUT' })).json(); }
catch { page = await (await fetch(`http://127.0.0.1:${CDP}/json/new?about:blank`)).json(); }
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener('open', r));
let id = 0; const pend = new Map();
ws.addEventListener('message', ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pend.has(m.id)) { const p = pend.get(m.id); pend.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); }
});
const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pend.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expression, awaitPromise = true) => {
  const r = await send('Runtime.evaluate', { expression, awaitPromise, returnByValue: true });
  if (r.exceptionDetails) return { JS_ERROR: r.exceptionDetails.exception?.description || r.exceptionDetails.text };
  return r.result?.value;
};
await send('Runtime.enable'); await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: BASE + '/?v=' + Date.now() });
await sleep(2200);
await ev(`(() => {
  window.__errs = [];
  const orig = window.renderDossier;
  window.renderDossier = function (p) {
    try { return orig(p); } catch (e) { window.__errs.push('renderDossier: ' + (e.stack || e)); throw e; }
  };
  document.querySelector('#eeg-samples .chip').click();
  document.querySelector('#dna-samples .chip').click();
})()`);
for (let i = 0; i < 24; i++) {
  await sleep(250);
  if (await ev(`!document.querySelector('#btn-scan').disabled`)) break;
}
await ev(`document.querySelector('#btn-scan').click()`);
for (let i = 0; i < 24; i++) {
  await sleep(500);
  const st = await ev(`({view: state.view, errs: window.__errs, prof: !!state.profile})`);
  if (st.errs && st.errs.length) { console.log(JSON.stringify(st, null, 2)); break; }
  if (st.view === 'dossier') { console.log('ok dossier'); break; }
  if (i === 23) console.log('timeout', JSON.stringify(st));
}
ws.close();
