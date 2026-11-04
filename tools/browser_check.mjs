/**
 * 浏览器端验收：用 CDP 驱动 headless Edge，走一遍真实动线并截图。
 * 用法：node tools/browser_check.mjs
 */
import fs from 'node:fs';
import path from 'node:path';

const CDP = process.env.CDP_PORT || '9223';
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8017';
const OUT = 'out/shots';
fs.mkdirSync(OUT, { recursive: true });

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function json(url, opts) {
  const r = await fetch(url, opts);
  return r.json();
}

class Cdp {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    this.events = [];
    ws.addEventListener('message', ev => {
      const msg = JSON.parse(ev.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
      } else if (msg.method) {
        this.events.push(msg);
      }
    });
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async eval(expression, awaitPromise = false) {
    const res = await this.send('Runtime.evaluate', {
      expression, awaitPromise, returnByValue: true, allowUnsafeEvalBlockedByCSP: true,
    });
    if (res.exceptionDetails) throw new Error('JS 异常: ' + (res.exceptionDetails.exception?.description || res.exceptionDetails.text));
    return res.result?.value;
  }
  async shot(name) {
    const res = await this.send('Page.captureScreenshot', { format: 'png', fromSurface: true });
    const file = path.join(OUT, name + '.png');
    fs.writeFileSync(file, Buffer.from(res.data, 'base64'));
    console.log('  shot →', file);
  }
  errors() {
    const out = [];
    for (const e of this.events) {
      if (e.method === 'Runtime.exceptionThrown') {
        out.push('exception: ' + (e.params.exceptionDetails.exception?.description || e.params.exceptionDetails.text));
      }
      if (e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error') {
        out.push('console.error: ' + e.params.args.map(a => a.value ?? a.description ?? '').join(' '));
      }
      if (e.method === 'Log.entryAdded' && e.params.entry.level === 'error') {
        out.push('log: ' + e.params.entry.text);
      }
    }
    return out;
  }
}

async function main() {
  // 1. 新建标签页
  let target;
  try {
    target = await json(`http://127.0.0.1:${CDP}/json/new?about:blank`, { method: 'PUT' });
  } catch (e) {
    target = await json(`http://127.0.0.1:${CDP}/json/new?about:blank`);
  }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej); });
  const cdp = new Cdp(ws);

  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Log.enable');
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false,
  });

  console.log('→ 打开首页');
  await cdp.send('Page.navigate', { url: BASE + '/?v=' + Date.now() });
  await sleep(2200);
  await cdp.shot('01-welcome');

  console.log('→ 进入录入');
  await cdp.eval(`document.querySelector('#btn-start').click()`);
  await sleep(700);
  const intakeOk = await cdp.eval(`document.querySelector('#view-intake').classList.contains('active')`);
  console.log('  intake active:', intakeOk);
  await cdp.shot('02-intake');

  console.log('→ 载入内置样本并开始融合');
  await cdp.eval(`document.querySelector('#eeg-samples .chip').click(); document.querySelector('#dna-samples .chip').click();`);
  for (let i = 0; i < 24; i++) {
    await sleep(250);
    if (await cdp.eval(`!document.querySelector('#btn-scan').disabled`)) break;
  }
  await cdp.eval(`document.querySelector('#btn-scan').click()`);
  await sleep(2000);
  await cdp.shot('03-scan');
  for (let i = 0; i < 30; i++) {
    await sleep(500);
    const active = await cdp.eval(`document.querySelector('#view-dossier').classList.contains('active')`);
    if (active) break;
  }
  const dossOk = await cdp.eval(`document.querySelector('#view-dossier').classList.contains('active')`);
  console.log('  dossier active:', dossOk);
  await sleep(1200);
  await cdp.shot('04-dossier');
  const info = await cdp.eval(`(() => {
    const p = state.profile || {};
    return {
      name: p.persona?.name, title: p.persona?.title,
      traits: (p.traits || []).length,
      wave: p.eeg?.waveform?.channels?.[0]?.length || 0,
      memories: document.querySelectorAll('#memories .memory').length,
      radars: !!document.querySelector('#radar-canvas').width,
      helix: !!document.querySelector('#helix-canvas').width,
    };
  })()`);
  console.log('  profile:', JSON.stringify(info));

  console.log('→ 打开对话');
  await cdp.eval(`document.querySelector('#btn-talk').click()`);
  await sleep(900);
  await cdp.shot('05-chat');
  console.log('→ 发一条消息');
  await cdp.eval(`(() => {
    const ta = document.querySelector('#chat-input');
    ta.value = '我最近睡不着，脑子里很吵。';
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    document.querySelector('#chat-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  })()`);
  await sleep(1800);
  const chat = await cdp.eval(`(() => ({
    msgs: document.querySelectorAll('#chat-stream .msg').length,
    last: document.querySelector('#chat-stream .msg:last-child .bubble')?.textContent || '',
    emo: document.querySelector('#emo-label')?.textContent,
    rel: document.querySelector('#rel-label')?.textContent,
  }))()`);
  console.log('  chat:', JSON.stringify(chat));
  await cdp.shot('06-chat-reply');

  console.log('→ 档案库');
  await cdp.eval(`document.querySelector('#btn-library').click()`);
  await sleep(1200);
  const lib = await cdp.eval(`(() => ({
    cards: document.querySelectorAll('#library-grid .mind-card').length,
    empty: !document.querySelector('#library-empty').hidden,
  }))()`);
  console.log('  library:', JSON.stringify(lib));
  await cdp.shot('07-library');

  await cdp.eval(`document.querySelector('#btn-lib-close').click()`);
  await sleep(500);

  const errs = cdp.errors();
  console.log('\nJS 错误数:', errs.length);
  errs.slice(0, 12).forEach(e => console.log('  !', e));
  fs.writeFileSync('out/browser_report.json', JSON.stringify({
    intakeOk, dossOk, info, chat, lib, errors: errs,
  }, null, 2));
  ws.close();
  if (!dossOk || errs.length) process.exitCode = 1;
}

main().catch(err => { console.error('FAILED:', err); process.exit(1); });
