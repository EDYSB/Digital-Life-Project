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
const target = minds.items.find(x => x.name === '守一') || minds.items[0];
console.log('profile', target.id, target.name);
await send('Page.navigate', { url: `${BASE}/?mind=${target.id}&v=${Date.now()}` });
await sleep(2600);

// 星图截图
await ev(`document.querySelector('#starmap-card').scrollIntoView({block:'center', behavior:'instant'})`);
await sleep(1200);
await shot('star-map');
const mapInfo = await ev(`({
  nodes: document.querySelectorAll('#starmap-legend span').length,
  detail: document.querySelector('#starmap-detail').textContent,
  comp: document.querySelectorAll('#comp-bar i').length,
  memories: document.querySelectorAll('#mind-list .mind-item').length,
  mood: !!document.querySelector('#mood-canvas').width,
})`);
console.log('map', JSON.stringify(mapInfo));

// 点一个节点
await ev(`(() => {
  const cv = document.querySelector('#starmap-canvas');
  const r = cv.getBoundingClientRect();
  cv.dispatchEvent(new PointerEvent('pointerdown', { clientX: r.left + r.width * 0.5, clientY: r.top + r.height * 0.5, bubbles: true }));
  cv.dispatchEvent(new PointerEvent('pointermove', { clientX: r.left + r.width * 0.5, clientY: r.top + r.height * 0.5, bubbles: true }));
})()`);
await sleep(600);
await shot('star-map-detail');

// 对话：建立记忆 → 追问
await ev(`document.querySelector('#btn-talk').click()`);
await sleep(1200);
console.log('opening', (await ev(`document.querySelector('#chat-stream .msg.ai .bubble')?.textContent`))?.slice(0, 80));
for (const q of ['我的猫叫年糕，它总在凌晨叫。', '你还记得我的猫吗？', '我最近有点累。']) {
  await ev(`(() => {
    const ta = document.querySelector('#chat-input');
    ta.value = ${JSON.stringify(q)};
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    document.querySelector('#chat-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  })()`);
  await sleep(2200);
}
const chatInfo = await ev(`({
  msgs: document.querySelectorAll('#chat-stream .msg').length,
  chips: Array.from(document.querySelectorAll('.mem-chip')).map(x => x.textContent),
  mem: document.querySelector('#mem-count')?.textContent,
  mood: document.querySelector('#emo-label')?.textContent,
})`);
console.log('chat', JSON.stringify(chatInfo));
await shot('chat-memory');

// 回档案看星图新节点
await ev(`document.querySelector('#btn-back-dossier').click()`);
await sleep(1200);
await ev(`document.querySelector('#starmap-card').scrollIntoView({block:'center', behavior:'instant'})`);
await sleep(1000);
await shot('star-map-after-chat');
const after = await ev(`({ memories: document.querySelectorAll('#mind-list .mind-item').length, count: document.querySelector('#mind-count')?.textContent })`);
console.log('after', JSON.stringify(after));
ws.close();
