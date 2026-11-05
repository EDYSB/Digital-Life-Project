/* ============================================================
   数字生命初级 — 前端
   ============================================================ */
'use strict';

/* ---------------- 工具 ---------------- */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, t) => a + (b - a) * t;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const fmt = n => (n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n));
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function toast(msg, isErr) {
  const el = $('#toast');
  el.textContent = msg;
  el.className = 'toast show' + (isErr ? ' err' : '');
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.className = 'toast'; }, 3200);
}

const state = {
  status: null,
  view: 'welcome',
  eeg: null,   // {file, name, size, label}
  dna: null,
  voice: 'calm',
  face: null,
  voiceSample: null,
  lastRecalled: [],
  profile: null,
  chat: [],
  library: [],
  compareSel: [],
  pendingScan: null,
};

/* ---------------- 视图切换 ---------------- */
const VIEWS = ['welcome', 'intake', 'scan', 'dossier', 'chat', 'library', 'compare', 'admin'];
const STEP_OF = { welcome: 0, intake: 1, scan: 2, dossier: 3, chat: 3, library: 3, compare: 3, admin: 3 };

function show(view) {
  state.view = view;
  $$('.view').forEach(v => v.classList.toggle('active', v.id === 'view-' + view));
  $$('#steps .step').forEach(el => {
    const n = +el.dataset.step;
    const cur = STEP_OF[view];
    el.classList.toggle('active', n === cur);
    el.classList.toggle('done', n < cur);
  });
  window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' });
  if (view === 'dossier') { requestAnimationFrame(() => window.dispatchEvent(new Event('resize'))); }
  if (view === 'chat') { requestAnimationFrame(() => window.dispatchEvent(new Event('resize'))); }
}

/* ---------------- 背景神经网络 ---------------- */
(function bg() {
  const cv = $('#bg-canvas');
  const ctx = cv.getContext('2d');
  let W = 0, H = 0, nodes = [], pulses = [];
  function resize() {
    W = cv.width = Math.floor(innerWidth * (devicePixelRatio > 1 ? 1.6 : 1));
    H = cv.height = Math.floor(innerHeight * (devicePixelRatio > 1 ? 1.6 : 1));
    cv.style.width = innerWidth + 'px';
    cv.style.height = innerHeight + 'px';
    const n = Math.min(110, Math.floor(innerWidth / 14));
    nodes = Array.from({ length: n }, () => ({
      x: Math.random() * W, y: Math.random() * H,
      vx: (Math.random() - .5) * .22, vy: (Math.random() - .5) * .22,
      r: 1 + Math.random() * 2.2,
    }));
  }
  const dpr = () => cv.width / innerWidth;
  function frame() {
    ctx.clearRect(0, 0, W, H);
    const s = dpr();
    for (const n of nodes) {
      n.x += n.vx * s; n.y += n.vy * s;
      if (n.x < 0 || n.x > W) n.vx *= -1;
      if (n.y < 0 || n.y > H) n.vy *= -1;
    }
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d < 170 * s) {
          const alpha = (1 - d / (170 * s)) * .16;
          ctx.strokeStyle = `rgba(90,200,225,${alpha})`;
          ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        }
      }
    }
    for (const n of nodes) {
      ctx.fillStyle = 'rgba(120,230,250,.34)';
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r * s, 0, Math.PI * 2); ctx.fill();
    }
    if (!reduceMotion && Math.random() < .03 && nodes.length > 2) {
      const a = nodes[Math.floor(Math.random() * nodes.length)];
      const b = nodes[Math.floor(Math.random() * nodes.length)];
      pulses.push({ a, b, t: 0 });
    }
    pulses = pulses.filter(p => p.t < 1);
    for (const p of pulses) {
      p.t += .018;
      const x = lerp(p.a.x, p.b.x, p.t), y = lerp(p.a.y, p.b.y, p.t);
      ctx.fillStyle = `rgba(56,232,255,${(1 - p.t) * .8})`;
      ctx.beginPath(); ctx.arc(x, y, 1.8 * s, 0, Math.PI * 2); ctx.fill();
    }
    requestAnimationFrame(frame);
  }
  resize(); addEventListener('resize', resize); requestAnimationFrame(frame);
})();

/* ---------------- 迷你波形 / 螺旋 ---------------- */
(function minis() {
  const wav = $('.mini-wave');
  if (wav) {
    const c = wav.getContext('2d');
    let t = 0;
    (function draw() {
      const W = wav.width, H = wav.height;
      c.clearRect(0, 0, W, H);
      for (let k = 0; k < 2; k++) {
        c.beginPath();
        for (let x = 0; x <= W; x += 2) {
          const p = x / W;
          const env = Math.sin(p * Math.PI) ** 1.5;
          const y = H / 2 + Math.sin(p * 28 + t + k * 1.4) * (k ? 7 : 11) * env
            + Math.sin(p * 61 - t * 1.6) * 2.5 * env;
          x ? c.lineTo(x, y) : c.moveTo(x, y);
        }
        c.strokeStyle = k ? 'rgba(155,107,255,.65)' : 'rgba(56,232,255,.85)';
        c.lineWidth = 1.4; c.stroke();
      }
      t += .035; requestAnimationFrame(draw);
    })();
  }
  const hel = $('.mini-helix');
  if (hel) {
    const c = hel.getContext('2d');
    const cols = ['#38e8ff', '#9b6bff', '#ff5fa2', '#ffb057'];
    let t = 0;
    (function draw() {
      const W = hel.width, H = hel.height;
      c.clearRect(0, 0, W, H);
      const N = 26;
      for (let i = 0; i < N; i++) {
        const p = i / (N - 1);
        const x = p * W;
        const ph = p * Math.PI * 4 + t;
        const y1 = H / 2 + Math.sin(ph) * 16;
        const y2 = H / 2 + Math.sin(ph + Math.PI) * 16;
        const depth = (Math.cos(ph) + 1) / 2;
        c.strokeStyle = `rgba(120,200,220,${.12 + depth * .3})`;
        c.lineWidth = 1;
        c.beginPath(); c.moveTo(x, y1); c.lineTo(x, y2); c.stroke();
        c.fillStyle = cols[i % 4];
        c.globalAlpha = .35 + depth * .65;
        c.beginPath(); c.arc(x, y1, 1.8 + depth * 1.6, 0, Math.PI * 2); c.fill();
        c.beginPath(); c.arc(x, y2, 1.2 + (1 - depth) * 1.4, 0, Math.PI * 2); c.fill();
      }
      c.globalAlpha = 1;
      t += .02; requestAnimationFrame(draw);
    })();
  }
})();

/* ---------------- 粒子球 ---------------- */
class Orb {
  constructor(canvas, opts = {}) {
    this.cv = canvas;
    this.ctx = canvas.getContext('2d');
    this.color = opts.color || '#38e6ff';
    this.n = opts.n || 900;
    this.pts = [];
    this.rot = 0;
    this.level = 0;
    this.target = 0;
    this.phase = Math.random() * 10;
    for (let i = 0; i < this.n; i++) {
      const y = 1 - (i / (this.n - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const th = i * 2.39996;
      const jitter = 1 + (Math.random() - .5) * .08;
      this.pts.push({ x: Math.cos(th) * r * jitter, y: y * jitter, z: Math.sin(th) * r * jitter, s: Math.random() });
    }
    this.resize();
    this.loop();
    window.addEventListener('resize', () => this.resize());
  }
  resize() {
    const r = this.cv.getBoundingClientRect();
    const dpr = Math.min(2, devicePixelRatio || 1);
    this.w = this.cv.width = Math.max(1, Math.floor((r.width || 300) * dpr));
    this.h = this.cv.height = Math.max(1, Math.floor((r.height || 300) * dpr));
  }
  setColor(c) { this.color = c; }
  pulse(v) { this.target = v; }
  loop() {
    const c = this.ctx, W = this.w, H = this.h, cx = W / 2, cy = H / 2;
    if (!W || !H) { requestAnimationFrame(() => this.loop()); return; }
    c.clearRect(0, 0, W, H);
    this.rot += reduceMotion ? .001 : .0035;
    this.level += (this.target - this.level) * .06;
    this.target *= .97;
    const R = Math.min(W, H) * .36 * (1 + this.level * .1);
    const rgb = hexRgb(this.color);
    const glow = c.createRadialGradient(cx, cy, R * .1, cx, cy, R * 1.5);
    glow.addColorStop(0, `rgba(${rgb},${.20 + this.level * .2})`);
    glow.addColorStop(.45, `rgba(${rgb},.07)`);
    glow.addColorStop(1, 'rgba(0,0,0,0)');
    c.fillStyle = glow;
    c.beginPath(); c.arc(cx, cy, R * 1.5, 0, Math.PI * 2); c.fill();

    const cos = Math.cos(this.rot), sin = Math.sin(this.rot);
    const tilt = Math.cos(this.rot * .6) * .35;
    const list = [];
    for (const p of this.pts) {
      let x = p.x * cos - p.z * sin;
      let z = p.x * sin + p.z * cos;
      let y = p.y * Math.cos(tilt) - z * Math.sin(tilt);
      z = p.y * Math.sin(tilt) + z * Math.cos(tilt);
      const persp = 1 / (1.75 - z * .55);
      const sx = cx + x * R * persp, sy = cy + y * R * persp;
      const depth = (z + 1) / 2;
      list.push({ sx, sy, depth, size: (1.1 + depth * 2.1) * Math.min(1.6, W / 420), p });
    }
    list.sort((a, b) => a.depth - b.depth);
    for (const q of list) {
      const a = .12 + q.depth * .72;
      c.fillStyle = q.depth > .72
        ? `rgba(255,255,255,${(q.depth - .72) * 1.8})`
        : `rgba(${rgb},${a})`;
      c.beginPath(); c.arc(q.sx, q.sy, q.size, 0, Math.PI * 2); c.fill();
    }
    // 内核
    const core = c.createRadialGradient(cx, cy, 0, cx, cy, R * .26);
    core.addColorStop(0, 'rgba(255,255,255,.85)');
    core.addColorStop(.35, `rgba(${rgb},.5)`);
    core.addColorStop(1, `rgba(${rgb},0)`);
    c.fillStyle = core;
    c.beginPath(); c.arc(cx, cy, R * .26, 0, Math.PI * 2); c.fill();
    // 外环
    c.strokeStyle = `rgba(${rgb},.16)`;
    c.lineWidth = 1;
    c.beginPath(); c.ellipse(cx, cy, R * 1.18, R * .32, this.rot * .3, 0, Math.PI * 2); c.stroke();
    requestAnimationFrame(() => this.loop());
  }
}
function hexRgb(hex) {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map(x => x + x).join('') : h, 16);
  return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
}

/* ---------------- 扫描舞台 ---------------- */
const ScanStage = {
  cv: null, ctx: null, active: false, prog: 0, done: 0, onDone: null, t: 0,
  init() {
    this.cv = $('#scan-canvas');
    this.ctx = this.cv.getContext('2d');
    window.addEventListener('resize', () => this.resize());
    this.resize();
  },
  resize() {
    if (!this.cv) return;
    const r = this.cv.getBoundingClientRect();
    const dpr = Math.min(2, devicePixelRatio || 1);
    this.cv.width = Math.max(1, Math.floor(r.width * dpr));
    this.cv.height = Math.max(1, Math.floor(r.height * dpr));
  },
  start() { this.active = true; this.prog = 0; this.done = 0; this.t = 0; this.loop(); },
  stop() { this.active = false; },
  loop() {
    if (!this.active) return;
    const c = this.ctx, W = this.cv.width, H = this.cv.height;
    if (!W || !H) { this.resize(); requestAnimationFrame(() => this.loop()); return; }
    const cx = W / 2, cy = H / 2, s = W / innerWidth;
    this.t += .016;
    c.clearRect(0, 0, W, H);

    // 两条数据流汇入中心
    const stage = this.prog / 100;
    for (let side = 0; side < 2; side++) {
      const dir = side ? 1 : -1;
      const base = side ? '#ff5fa2' : '#38e8ff';
      for (let k = 0; k < 26; k++) {
        const off = (k / 26 + this.t * .12) % 1;
        const x = cx + dir * (W * .42) * (1 - off) * (0.35 + stage * .65);
        const spread = (1 - off) * H * .18;
        const y = cy + Math.sin(k * 2.1 + this.t * 1.7) * spread;
        const a = (1 - off) * .55;
        c.globalAlpha = a;
        c.fillStyle = base;
        c.beginPath(); c.arc(x + (side ? -1 : 1) * Math.sin(this.t * 2 + k) * 4 * s, y, (1.4 + (1 - off) * 2) * s, 0, Math.PI * 2); c.fill();
      }
    }
    c.globalAlpha = 1;

    // 汇聚环
    const r = 60 * s + Math.sin(this.t * 2) * 6 * s + stage * 40 * s;
    const g = c.createRadialGradient(cx, cy, r * .2, cx, cy, r * 2.2);
    g.addColorStop(0, 'rgba(255,255,255,.20)');
    g.addColorStop(.3, 'rgba(56,232,255,.16)');
    g.addColorStop(.7, 'rgba(155,107,255,.08)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    c.fillStyle = g;
    c.beginPath(); c.arc(cx, cy, r * 2.2, 0, Math.PI * 2); c.fill();

    // 旋转粒子
    for (let i = 0; i < 70; i++) {
      const a = (i / 70) * Math.PI * 2 + this.t * (1.2 + (i % 5) * .1);
      const rr = r * (0.7 + (i % 7) / 10);
      const x = cx + Math.cos(a) * rr, y = cy + Math.sin(a) * rr * .55;
      c.fillStyle = i % 3 === 0 ? 'rgba(255,95,162,.7)' : 'rgba(56,232,255,.6)';
      c.beginPath(); c.arc(x, y, 1.4 * s, 0, Math.PI * 2); c.fill();
    }

    // 完成闪光
    if (this.done > 0) {
      this.done *= .94;
      c.fillStyle = `rgba(220,250,255,${this.done * .5})`;
      c.beginPath(); c.arc(cx, cy, r * (1 + (1 - this.done) * 3), 0, Math.PI * 2); c.fill();
    }
    requestAnimationFrame(() => this.loop());
  },
};

/* ---------------- 雷达图 ---------------- */
function drawRadar(cv, traits, color) {
  const dpr = Math.min(2, devicePixelRatio || 1);
  const r = cv.getBoundingClientRect();
  const W = cv.width = Math.max(1, r.width * dpr);
  const H = cv.height = Math.max(1, (r.height || r.width) * dpr);
  const c = cv.getContext('2d');
  c.clearRect(0, 0, W, H);
  const cx = W / 2, cy = H / 2, R = Math.min(W, H) * .33;
  const n = traits.length;
  const rgb = hexRgb(color || '#38e8ff');
  c.save();
  for (let ring = 1; ring <= 4; ring++) {
    c.beginPath();
    for (let i = 0; i <= n; i++) {
      const a = (i % n) / n * Math.PI * 2 - Math.PI / 2;
      const rr = R * ring / 4;
      const x = cx + Math.cos(a) * rr, y = cy + Math.sin(a) * rr;
      i ? c.lineTo(x, y) : c.moveTo(x, y);
    }
    c.strokeStyle = `rgba(130,200,220,${ring === 4 ? .22 : .1})`;
    c.lineWidth = 1; c.stroke();
  }
  for (let i = 0; i < n; i++) {
    const a = i / n * Math.PI * 2 - Math.PI / 2;
    c.beginPath(); c.moveTo(cx, cy);
    c.lineTo(cx + Math.cos(a) * R, cy + Math.sin(a) * R);
    c.strokeStyle = 'rgba(130,200,220,.1)'; c.stroke();
  }
  c.beginPath();
  traits.forEach((t, i) => {
    const a = i / n * Math.PI * 2 - Math.PI / 2;
    const rr = R * clamp(t.value, 0.04, 1);
    const x = cx + Math.cos(a) * rr, y = cy + Math.sin(a) * rr;
    i ? c.lineTo(x, y) : c.moveTo(x, y);
  });
  c.closePath();
  const grad = c.createRadialGradient(cx, cy, 0, cx, cy, R);
  grad.addColorStop(0, `rgba(${rgb},.35)`);
  grad.addColorStop(1, `rgba(${rgb},.06)`);
  c.fillStyle = grad; c.fill();
  c.strokeStyle = `rgba(${rgb},.85)`; c.lineWidth = 1.6; c.stroke();
  traits.forEach((t, i) => {
    const a = i / n * Math.PI * 2 - Math.PI / 2;
    const rr = R * clamp(t.value, 0.04, 1);
    const x = cx + Math.cos(a) * rr, y = cy + Math.sin(a) * rr;
    c.fillStyle = '#eaffff';
    c.beginPath(); c.arc(x, y, 2.2 * dpr, 0, Math.PI * 2); c.fill();
    const lx = cx + Math.cos(a) * (R + 24 * dpr), ly = cy + Math.sin(a) * (R + 22 * dpr);
    c.fillStyle = 'rgba(190,220,232,.9)';
    c.font = `${10 * dpr}px "PingFang SC","Microsoft YaHei",sans-serif`;
    c.textAlign = 'center'; c.textBaseline = 'middle';
    c.fillText(t.name, lx, ly);
  });
  c.restore();
}

/* ---------------- 波形 ---------------- */
const Wave = {
  data: [], pos: 0, cv: null, t: 0,
  draw(cv, samples) {
    this.cv = cv; this.data = samples || [];
    this.resize();
    if (!this._bound) {
      this._bound = true;
      window.addEventListener('resize', () => this.resize());
    }
    if (!this._raf) this.loop();
  },
  resize() {
    if (!this.cv) return;
    const dpr = Math.min(2, devicePixelRatio || 1);
    const r = this.cv.getBoundingClientRect();
    this.cv.width = Math.max(1, r.width * dpr);
    this.cv.height = Math.max(1, r.height * dpr);
  },
  loop() {
    this._raf = requestAnimationFrame(() => this.loop());
    if (!this.cv || !this.data.length || !this.cv.width) return;
    const c = this.cv.getContext('2d');
    const W = this.cv.width, H = this.cv.height, mid = H / 2;
    c.clearRect(0, 0, W, H);
    const d = this.data;
    const step = Math.max(1, Math.floor(d.length / (W / 2)));
    c.beginPath();
    for (let i = 0, x = 0; x < W && i < d.length; i += step, x += 2) {
      const y = mid + clamp(d[i], -1, 1) * H * .38;
      x ? c.lineTo(x, y) : c.moveTo(x, y);
    }
    c.strokeStyle = 'rgba(56,232,255,.75)';
    c.lineWidth = 1.2;
    c.shadowColor = 'rgba(56,232,255,.55)';
    c.shadowBlur = 8;
    c.stroke();
    c.shadowBlur = 0;

    this.t += .012;
    this.pos = (Math.sin(this.t * .7) * .5 + .5) * W;
    const sweep = c.createLinearGradient(this.pos - 60, 0, this.pos, 0);
    sweep.addColorStop(0, 'rgba(255,95,162,0)');
    sweep.addColorStop(1, 'rgba(255,95,162,.22)');
    c.fillStyle = sweep;
    c.fillRect(this.pos - 60, 0, 60, H);
    c.fillStyle = 'rgba(255,95,162,.9)';
    c.fillRect(this.pos, 0, 1, H);
    c.fillStyle = 'rgba(56,232,255,.5)';
    c.fillRect(0, mid, W, 1);
  }
};

/* ---------------- 频谱 ---------------- */
function drawSpectrum(cv, freqs, power, bands, peak) {
  const dpr = Math.min(2, devicePixelRatio || 1);
  const r = cv.getBoundingClientRect();
  const W = cv.width = Math.max(1, r.width * dpr);
  const H = cv.height = Math.max(1, r.height * dpr);
  const c = cv.getContext('2d');
  c.clearRect(0, 0, W, H);
  const fmin = 1, fmax = 45;
  const xOf = f => (Math.log(f / fmin) / Math.log(fmax / fmin)) * W;
  let pmin = Infinity, pmax = -Infinity;
  for (const p of power) { if (p < pmin) pmin = p; if (p > pmax) pmax = p; }
  const yOf = p => H - ((p - pmin) / (pmax - pmin || 1)) * (H - 6) - 2;
  // 频带底色
  const bandMap = { delta: '#6b5bd2', theta: '#9b6bff', alpha: '#38e8ff', beta: '#ffb057', gamma: '#ff5fa2' };
  for (const [k, col] of Object.entries(bandMap)) {
    const b = bands[k]; if (!b) continue;
    const lo = { delta: 1, theta: 4, alpha: 8, beta: 13, gamma: 30 }[k];
    const hi = { delta: 4, theta: 8, alpha: 13, beta: 30, gamma: 45 }[k];
    const x1 = xOf(Math.max(lo, fmin)), x2 = xOf(hi);
    const g = c.createLinearGradient(0, H, 0, 0);
    g.addColorStop(0, hexA(col, .16)); g.addColorStop(1, hexA(col, .02));
    c.fillStyle = g;
    c.fillRect(x1, 0, x2 - x1, H);
  }
  c.beginPath();
  for (let i = 0; i < freqs.length; i++) {
    const f = freqs[i];
    if (f < fmin || f > fmax) continue;
    const x = xOf(f), y = yOf(power[i]);
    i ? c.lineTo(x, y) : c.moveTo(x, y);
  }
  c.strokeStyle = 'rgba(210,245,255,.9)';
  c.lineWidth = 1.3; c.stroke();
  if (peak) {
    const x = xOf(peak);
    c.strokeStyle = 'rgba(255,95,162,.8)';
    c.setLineDash([3, 3]);
    c.beginPath(); c.moveTo(x, 0); c.lineTo(x, H); c.stroke();
    c.setLineDash([]);
    c.fillStyle = 'rgba(255,160,200,.95)';
    c.font = `${9 * dpr}px "JetBrains Mono",Consolas,monospace`;
    c.textAlign = 'center';
    c.fillText(peak.toFixed(1) + ' Hz', clamp(x, 34 * dpr, W - 34 * dpr), 11 * dpr);
  }
  c.fillStyle = 'rgba(130,170,185,.5)';
  c.font = `${8 * dpr}px "JetBrains Mono",Consolas,monospace`;
  [1, 4, 8, 13, 30, 45].forEach(f => {
    const x = xOf(f);
    c.fillRect(x, H - 4 * dpr, 1, 4 * dpr);
  });
}
function hexA(hex, a) {
  const rgb = hexRgb(hex);
  return `rgba(${rgb},${a})`;
}

/* ---------------- DNA 螺旋 ---------------- */
const Helix = {
  cv: null, bases: '', t: 0, raf: 0,
  start(cv, bases) {
    this.cv = cv; this.bases = bases || ''; this.t = 0;
    this.resize();
    if (!this._bound) {
      this._bound = true;
      window.addEventListener('resize', () => this.resize());
    }
    cancelAnimationFrame(this.raf);
    this.loop();
  },
  resize() {
    if (!this.cv) return;
    const dpr = Math.min(2, devicePixelRatio || 1);
    const r = this.cv.getBoundingClientRect();
    this.cv.width = Math.max(1, r.width * dpr);
    this.cv.height = Math.max(1, r.height * dpr);
  },
  loop() {
    this.raf = requestAnimationFrame(() => this.loop());
    const cv = this.cv;
    if (!cv || !cv.width || !this.bases) return;
    const c = cv.getContext('2d');
    const W = cv.width, H = cv.height, mid = H / 2;
    c.clearRect(0, 0, W, H);
    const bases = this.bases;
    const n = Math.min(64, bases.length);
    const cols = { A: '#38e8ff', T: '#ff5fa2', G: '#ffb057', C: '#9b6bff' };
    for (let i = 0; i < n; i++) {
      const p = i / (n - 1);
      const x = W * .06 + p * W * .88;
      const ph = p * Math.PI * 5 + this.t;
      const amp = H * .26;
      const y1 = mid + Math.sin(ph) * amp;
      const y2 = mid + Math.sin(ph + Math.PI) * amp;
      const depth = (Math.cos(ph) + 1) / 2;
      // 连接线
      c.strokeStyle = `rgba(120,190,210,${.05 + depth * .18})`;
      c.lineWidth = 1;
      c.beginPath(); c.moveTo(x, y1); c.lineTo(x, y2); c.stroke();
      const b = bases[i];
      c.fillStyle = cols[b] || '#88a';
      c.globalAlpha = .25 + depth * .75;
      c.beginPath(); c.arc(x, y1, (1.6 + depth * 2.2), 0, Math.PI * 2); c.fill();
      c.beginPath(); c.arc(x, y2, (1.2 + (1 - depth) * 2), 0, Math.PI * 2); c.fill();
      if (i % 3 === 0 && depth > .55) {
        c.fillStyle = `rgba(220,245,255,${(depth - .55) * 1.2})`;
        c.font = `${8 * (cv.width / (cv.getBoundingClientRect().width || 1))}px "JetBrains Mono",monospace`;
        c.textAlign = 'center';
        c.fillText(b, x, y1 - 7);
      }
    }
    c.globalAlpha = 1;
    this.t += .016;
  },
};

/* ---------------- 音景 ---------------- */
const Audio = {
  ctx: null, nodes: [], playing: false,
  ensure() {
    if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (this.ctx.state === 'suspended') this.ctx.resume();
    return this.ctx;
  },
  stop() {
    this.playing = false;
    this.nodes.forEach(n => { try { n.stop ? n.stop() : n.disconnect(); } catch (e) { } });
    this.nodes = [];
  },
  play(cfg) {
    if (!cfg) return;
    this.stop();
    const ac = this.ensure();
    const master = ac.createGain();
    master.gain.value = 0;
    master.connect(ac.destination);
    master.gain.linearRampToValueAtTime(.5, ac.currentTime + 1.6);
    const lp = ac.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 900 + 1800 * (cfg.brightness || .5);
    lp.Q.value = .6;
    lp.connect(master);
    // 持续低音
    (cfg.band_tones || []).forEach((bt, i) => {
      const o = ac.createOscillator();
      o.type = i % 2 ? 'sine' : 'triangle';
      o.frequency.value = bt.freq;
      o.detune.value = (i - 2) * 4;
      const g = ac.createGain();
      g.gain.value = bt.gain * .5;
      o.connect(g); g.connect(lp);
      o.start();
      this.nodes.push(o, g);
    });
    // 和弦琶音
    const notes = cfg.notes || [110, 165, 220];
    const tempo = cfg.tempo || 60;
    const dur = cfg.duration || 24;
    const step = 60 / tempo;
    let t = ac.currentTime + .4;
    const end = ac.currentTime + dur;
    let i = 0;
    while (t < end - 1.2) {
      const f = notes[i % notes.length] * (i % 7 === 6 ? 2 : 1);
      const o = ac.createOscillator();
      o.type = 'sine';
      o.frequency.value = f;
      const g = ac.createGain();
      g.gain.setValueAtTime(0, t);
      g.gain.linearRampToValueAtTime(.11, t + .04);
      g.gain.exponentialRampToValueAtTime(.001, t + step * 2.6);
      const pan = ac.createStereoPanner ? ac.createStereoPanner() : null;
      if (pan) { pan.pan.value = Math.sin(i * 1.7) * .5; o.connect(g); g.connect(pan); pan.connect(master); }
      else { o.connect(g); g.connect(master); }
      o.start(t); o.stop(t + step * 2.8);
      this.nodes.push(o, g);
      t += step * (i % 3 === 2 ? 1.6 : 1);
      i++;
    }
    const fadeAt = ac.currentTime + dur - 1.4;
    master.gain.setValueAtTime(.5, fadeAt);
    master.gain.linearRampToValueAtTime(0, ac.currentTime + dur);
    this.playing = true;
    this._master = master;
    setTimeout(() => { if (this.playing) this.stop(); }, (dur + .4) * 1000);
  },
};

/* ---------------- API ---------------- */
async function apiGet(path) {
  const r = await fetch(path);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || '请求失败');
  return j;
}
async function apiPost(path, body) {
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || '请求失败');
  return j;
}

/* ---------------- 录入 ---------------- */
function setSlot(kind, file, label) {
  state[kind] = file ? { file, name: file.name, size: file.size, label: label || '' } : null;
  const box = $(kind === 'eeg' ? '#eeg-file' : '#dna-file');
  const status = $(kind === 'eeg' ? '#eeg-status' : '#dna-status');
  if (file) {
    box.hidden = false;
    box.querySelector('b').textContent = file.name;
    box.querySelector('small').textContent = (label || '') + ' · ' + fmtBytes(file.size);
    status.textContent = '已接入';
    status.classList.add('ok');
  } else {
    box.hidden = true;
    status.textContent = '未连接';
    status.classList.remove('ok');
  }
  updateReady();
}
function fmtBytes(n) {
  if (!n && n !== 0) return '';
  if (n < 1024) return n + ' B';
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
  return (n / 1024 / 1024).toFixed(1) + ' MB';
}
function updateReady() {
  const ready = !!(state.eeg && state.dna);
  $('#btn-scan').disabled = !ready;
  $('#ready-hint').textContent = ready
    ? '两条通道已接入，可以开始融合'
    : (!state.eeg && !state.dna) ? '等待两条通道接入'
      : state.eeg ? '还需要基因样本' : '还需要脑电样本';
}

function wireDropzone(kind) {
  const dz = $(kind === 'eeg' ? '#drop-eeg' : '#drop-dna');
  const input = $(kind === 'eeg' ? '#file-eeg' : '#file-dna');
  dz.addEventListener('click', () => input.click());
  dz.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
  input.addEventListener('change', () => { if (input.files[0]) pickFile(kind, input.files[0]); input.value = ''; });
  ['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('drag'); }));
  dz.addEventListener('drop', e => {
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) pickFile(kind, f);
  });
  dz.addEventListener('dragover', e => { e.dataTransfer.dropEffect = 'copy'; });
}
function pickFile(kind, file) {
  const max = 32 * 1024 * 1024;
  if (file.size > max) return toast('文件超过 32 MB，请先裁剪。', true);
  const exts = kind === 'eeg'
    ? ['.csv', '.tsv', '.txt', '.json', '.edf', '.npz', '.wav']
    : ['.fasta', '.fa', '.txt', '.vcf', '.json', '.csv', '.tsv'];
  const name = file.name.toLowerCase();
  if (!exts.some(e => name.endsWith(e))) {
    return toast(kind === 'eeg' ? '脑电支持 CSV/TSV/TXT/JSON/EDF/NPZ/WAV' : '基因支持 FASTA/23andMe/VCF/JSON', true);
  }
  setSlot(kind, file);
}

/* ---------------- 面孔 ---------------- */
let facePreview = null;

function facePayload() {
  const f = state.face;
  if (!f) return null;
  return {
    mode: f.mode,
    views: (f.views || []).map(v => ({ key: v.key, angle: v.angle, turn: v.turn, photo: v.photo, meta: v.meta })),
    primary: f.primary,
    meta: f.meta,
    palette: f.palette,
  };
}

function setFace(avatar) {
  state.face = avatar || null;
  const empty = $('#face-empty');
  const cv = $('#face-preview-canvas');
  const badge = $('#face-badge');
  const status = $('#face-status');
  const views = $('#face-views');
  const clear = $('#btn-face-clear');

  if (avatar && avatar.mode === 'sprite') {
    empty.hidden = true;
    cv.hidden = true;
    let img = $('#face-sprite-preview');
    if (!img) { img = document.createElement('img'); img.id = 'face-sprite-preview'; img.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;object-fit:contain'; $('#face-preview').appendChild(img); }
    img.src = avatar.sprite; img.hidden = false;
    badge.hidden = false; badge.textContent = '立绘 · 本地';
    status.textContent = '已录入 · 立绘'; status.classList.add('ok');
    clear.hidden = false; views.innerHTML = '';
    if (facePreview) { facePreview.destroy(); facePreview = null; }
    return;
  }
  const sp = $('#face-sprite-preview'); if (sp) sp.hidden = true;
  if (!avatar) {
    empty.hidden = false;
    cv.hidden = true;
    badge.hidden = true;
    status.textContent = '未录入';
    status.classList.remove('ok');
    views.innerHTML = '';
    clear.hidden = true;
    if (facePreview) { facePreview.destroy(); facePreview = null; }
    return;
  }
  empty.hidden = true;
  cv.hidden = false;
  badge.hidden = false;
  status.textContent = avatar.mode === 'camera' ? '已录入 · 多视角' : '已录入 · 照片';
  status.classList.add('ok');
  clear.hidden = false;
  badge.textContent = (avatar.views ? avatar.views.length : 1) + ' 个视角 · 本地';

  if (!facePreview) facePreview = new Avatar(cv, { color: '#ffb057' });
  facePreview.setViews(avatar.views && avatar.views.length ? avatar.views : [{ photo: avatar.primary, meta: avatar.meta }]);

  views.innerHTML = '';
  (avatar.views || []).forEach(v => {
    const d = document.createElement('div');
    d.className = 'face-view';
    const img = document.createElement('img');
    img.src = v.photo;
    img.alt = v.key;
    const label = document.createElement('span');
    label.textContent = ({ front: '正面', left: '左转', right: '右转', up: '抬头', smile: '微笑' })[v.key] || v.key;
    d.appendChild(img); d.appendChild(label);
    views.appendChild(d);
  });
}

async function pickFaceFile(file) {
  try {
    toast('正在分析照片…');
    const res = await Face.analyze(file, { name: file.name });
    setFace({
      mode: 'photo',
      views: [{ key: 'front', angle: 0, turn: 0, photo: res.photo, meta: res.meta }],
      primary: res.photo,
      meta: res.meta,
      palette: res.meta.palette,
    });
    toast('面孔已录入。');
  } catch (err) { toast(err.message, true); }
}

function pickSprite(file) {
  if (!/^image\//.test(file.type || '')) return toast('请选择 PNG / WebP 图片。', true);
  if (file.size > 6 * 1024 * 1024) return toast('立绘超过 6 MB。', true);
  const fr = new FileReader();
  fr.onload = function () {
    setFace({ mode: 'sprite', sprite: fr.result, views: [], primary: fr.result, meta: null });
    toast('立绘已导入。打开游戏模式看看。');
  };
  fr.readAsDataURL(file);
}

function openCamera() {
  if (!window.CameraCapture) return toast('摄像头模块未加载。', true);
  CameraCapture.start(avatar => {
    setFace(avatar);
    toast('已录入 ' + avatar.views.length + ' 个视角。');
  });
}

async function recordVoice() {
  const btn = $('#btn-record');
  const status = $('#voice-status');
  if (!window.Mic) return toast('录音模块未加载。', true);
  if (btn.classList.contains('recording')) { Mic.stopRecord(); return; }
  try {
    btn.classList.add('recording');
    status.textContent = '录音中…';
    status.classList.remove('ok');
    const res = await Mic.record(3200, function (p) {
      status.textContent = '录音中 ' + Math.round(p * 100) + '%';
    });
    if (!res.clip) throw new Error('录音太短或浏览器不支持录音格式。');
    state.voiceSample = { clip: res.clip, metrics: res.metrics, duration: res.duration, at: new Date().toISOString() };
    const audio = $('#voice-audio');
    audio.src = res.clip;
    audio.hidden = false;
    $('#btn-voice-clear').hidden = false;
    status.textContent = '已录制 · ' + res.metrics.f0 + ' Hz';
    status.classList.add('ok');
    const m = res.metrics;
    $('#voice-metrics').innerHTML = [
      ['基频', m.f0 + ' Hz'], ['音色', m.centroid + ' Hz'], ['有声', Math.round(m.voiced * 100) + '%'], ['时长', m.duration + 's'],
    ].map(function (x) { return '<div><span>' + x[0] + '</span><b>' + x[1] + '</b></div>'; }).join('');
    toast('声音样本已录下。它不会克隆你，但会记住你的声线。');
  } catch (err) {
    status.textContent = '未录制';
    toast(err.message || '录音失败', true);
  } finally {
    btn.classList.remove('recording');
  }
}

function clearVoice() {
  state.voiceSample = null;
  const audio = $('#voice-audio');
  audio.hidden = true;
  audio.removeAttribute('src');
  $('#btn-voice-clear').hidden = true;
  $('#voice-metrics').innerHTML = '';
  const status = $('#voice-status');
  status.textContent = '未录制';
  status.classList.remove('ok');
}

function clearFace() {
  setFace(null);
  const input = $('#file-face');
  if (input) input.value = '';
}

let listening = false;
function toggleMic() {
  if (!window.Mic) return toast('语音模块未加载。', true);
  if (!Mic.speechSupported()) return toast('这个浏览器不支持语音识别，请用键盘输入。', true);
  const btn = $('#btn-mic');
  if (listening) {
    Mic.stopListen();
    listening = false;
    btn.classList.remove('rec');
    return;
  }
  if (!localStorage.getItem('echomind_stt_notice')) {
    const ok = confirm('语音识别可能由浏览器调用云端服务（Chrome/Edge 的实现方式），音频可能离开本机。\n\n本系统的其余部分都在本地运行。仍要使用语音输入吗？');
    if (!ok) return;
    localStorage.setItem('echomind_stt_notice', '1');
  }
  listening = true;
  btn.classList.add('rec');
  const input = $('#chat-input');
  const oldPlaceholder = input.placeholder;
  input.placeholder = '正在听…';
  Mic.listen({
    onInterim: function (t) { input.value = t; },
    onText: function (t) { input.value = t; },
    onEnd: function (finalText) {
      listening = false;
      btn.classList.remove('rec');
      input.placeholder = oldPlaceholder;
      if (finalText) { input.focus(); toast('识别完成，确认后发送。'); }
    },
    onError: function (err) {
      listening = false;
      btn.classList.remove('rec');
      input.placeholder = oldPlaceholder;
      toast(err.message, true);
    },
  });
}

/* ---------------- 扫描流程 ---------------- */
async function runScan(eeg, dna) {
  show('scan');
  $('#scan-error').hidden = true;
  $('#scan-pct').innerHTML = '0<small>%</small>';
  $('#scan-core-label').textContent = '初始化';
  ['#track-eeg', '#track-dna', '#track-core'].forEach(sel => {
    const t = $(sel);
    t.querySelector('.track-bar i').style.width = '0%';
    t.querySelector('.track-pct').textContent = '0%';
    t.querySelector('.track-log').innerHTML = '';
  });
  state.pendingScan = { eeg, dna };
  ScanStage.start();
  $('#scan-quote').textContent = pickQuote();

  const fd = new FormData();
  fd.append('eeg', eeg, eeg.name);
  fd.append('dna', dna, dna.name);
  fd.append('subject', $('#subject').value.trim());
  fd.append('voice', state.voice);
  if (state.face) fd.append('avatar', JSON.stringify(facePayload()));
  if (state.voiceSample) fd.append('voice', JSON.stringify(state.voiceSample));

  const pct = { eeg: 0, dna: 0, core: 0 };
  let finished = false;

  function handleEvent(evt, data) {
    if (evt === 'failed') {
      finished = true;
      ScanStage.stop();
      $('#scan-error').hidden = false;
      $('#scan-error').textContent = '融合失败：' + (data.message || '未知错误') + '\n\n请检查文件格式，或换一份内置样本试试。';
      $('#scan-core-label').textContent = '失败';
      return;
    }
    if (evt === 'done') {
      finished = true;
      ScanStage.prog = 100; ScanStage.done = 1;
      $('#scan-pct').innerHTML = '100<small>%</small>';
      $('#scan-core-label').textContent = '完成';
      renderDossier(data.profile);
      setTimeout(() => {
        ScanStage.stop();
        show('dossier');
        toast('数字生命已录入：' + data.profile.persona.name);
      }, 900);
      return;
    }
    if (!data || typeof data.pct !== 'number') return;
    const tr = data.track || 'core';
    pct[tr] = Math.max(pct[tr] || 0, data.pct);
    const sel = '#track-' + tr;
    const t = $(sel);
    if (t) {
      t.querySelector('.track-bar i').style.width = pct[tr] + '%';
      t.querySelector('.track-pct').textContent = Math.round(pct[tr]) + '%';
      const li = document.createElement('li');
      li.textContent = data.message;
      const log = t.querySelector('.track-log');
      log.prepend(li);
      while (log.children.length > 5) log.removeChild(log.lastChild);
    }
    const overall = Math.round((pct.eeg * .42 + pct.dna * .32 + pct.core * .26));
    $('#scan-pct').innerHTML = overall + '<small>%</small>';
    ScanStage.prog = overall;
    $('#scan-core-label').textContent = data.stage === 'eeg' ? '读取脑波'
      : data.stage === 'dna' ? '读取基因'
        : data.stage === 'fuse' ? '融合维度'
          : data.stage === 'persona' ? '命名与语气' : '合成';
  }

  try {
    const resp = await fetch('/api/scan/stream', { method: 'POST', body: fd });
    if (!resp.ok || !resp.body) {
      const j = await resp.json().catch(() => ({}));
      throw new Error(j.error || '扫描失败');
    }
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        let evt = 'message';
        const dataLines = [];
        chunk.split('\n').forEach(line => {
          if (line.startsWith('event:')) evt = line.slice(6).trim();
          else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
        });
        if (!dataLines.length) continue;
        let data;
        try { data = JSON.parse(dataLines.join('\n')); } catch (e) { continue; }
        handleEvent(evt, data);
      }
    }
    if (!finished) throw new Error('连接中断，未收到完整结果。');
  } catch (err) {
    if (!finished) {
      ScanStage.stop();
      $('#scan-error').hidden = false;
      $('#scan-error').textContent = '融合失败：' + err.message + '\n\n请检查文件格式，或换一份内置样本试试。';
      $('#scan-core-label').textContent = '失败';
    }
  }
}

const QUOTES = [
  '「把一个人读成数据，是一种冒犯；把数据读成一个人，是一种温柔。」',
  '「脑波是海面，基因是海床。你看到的浪，从来不是全部。」',
  '「记忆不会被电极带走，但节奏会。」',
  '「所谓副本，是一份被认真写下来的误解。」',
];
const pickQuote = () => QUOTES[Math.floor(Math.random() * QUOTES.length)];

/* ---------------- 档案渲染 ---------------- */
let mainOrb = null, mainAvatar = null, chatAvatar = null, chatOrb = null, cmpOrbA = null, cmpOrbB = null;
let chatSpeakEl = null;
let currentAudioCfg = null;

function renderDossier(p) {
  state.profile = p;
  const per = p.persona;
  const color = per.color || '#38e8ff';
  document.documentElement.style.setProperty('--accent', color);
  $('#d-id').textContent = p.id.toUpperCase();
  const dt = new Date(p.created_at);
  $('#d-created').textContent = isNaN(dt) ? p.created_at : dt.toLocaleString('zh-CN', { hour12: false });
  $('#d-name').textContent = per.name;
  $('#d-title').textContent = per.title;
  const coreLine = $('#d-core');
  if (coreLine) {
    coreLine.textContent = (p.core && p.core.line) || 'Love，就是爱。解析到最后，只剩这一个词：爱自己，也爱别人。';
  }
  $('#d-summary').textContent = per.summary;
  $('#d-limits').textContent = per.limits;

  const chips = [
    '说话方式 · ' + per.voice_label,
    '状态 · ' + (p.eeg.mood || per.mood),
    '维度 · ' + p.traits.slice().sort((a, b) => b.value - a.value).slice(0, 3).map(t => t.name).join(' / '),
  ];
  $('#d-chips').innerHTML = chips.map(c => `<span class="tag">${esc(c)}</span>`).join('');
  // 参数一律不上前台，只在 `dl stats` / 后台页出现
  const orgEl = $('#d-origin');
  if (orgEl) { orgEl.innerHTML = ''; orgEl.style.display = 'none'; }
  ['#signal-stats', '#dna-foot', '#fusion-foot', '#life-status'].forEach(function (sel) {
    const el = $(sel);
    if (el) el.style.display = 'none';
  });

  const status = $('#life-status');
  if (status) {
    const code = (p.persona && p.persona.code) || ('DL-' + String(p.id || '').slice(-6).toUpperCase());
    const mem = ((p.mind && p.mind.memories) || []).length;
    const sessions = (p.mind && p.mind.stats && p.mind.stats.sessions) || 0;
    const w = (p.mind && p.mind.world) || {};
    const rows = [
      ['编号', code],
      ['生于', String(p.created_at || '').slice(0, 16).replace('T', ' ')],
      ['会话', sessions],
      ['记忆', mem],
      ['稳定度', Math.round((w.stability != null ? w.stability : 1) * 100) + '%'],
      ['来源', 'EEG ' + Math.round(p.eeg.seconds) + 's · DNA ' + p.dna.coverage.markers_hit + ' · 面孔 ' + ((p.avatar && p.avatar.views && p.avatar.views.length) || 0)],
    ];
    status.innerHTML = '<div class="ls-head">RUNNING STATE</div>' + rows.map(function (r) {
      return '<div class="ls-row"><span>' + r[0] + '</span><b>' + esc(r[1]) + '</b></div>';
    }).join('');
  }

  // 面孔卡
  const hasFace = !!(p.avatar && p.avatar.views && p.avatar.views.length);
  const faceCard = $('#face-card');
  if (hasFace) {
    faceCard.hidden = false;
    const shots = $('#face-shots');
    shots.innerHTML = '';
    p.avatar.views.forEach(function (v) {
      const img = document.createElement('img');
      img.src = v.photo; img.alt = v.key;
      shots.appendChild(img);
    });
    const m = (p.avatar.meta && p.avatar.meta.metrics) || {};
    const pal = (p.avatar.palette && p.avatar.palette.all) || [];
    const rows = [
      ['视角', p.avatar.views.length + ' 个'],
      ['对称度', m.symmetry != null ? Math.round(m.symmetry * 100) + '%' : '—'],
      ['明度', m.brightness != null ? Math.round(m.brightness * 100) + '%' : '—'],
      ['对比', m.contrast != null ? Math.round(m.contrast * 100) + '%' : '—'],
      ['暖度', m.warmth != null ? Math.round(m.warmth * 100) + '%' : '—'],
      ['饱和度', m.saturation != null ? Math.round(m.saturation * 100) + '%' : '—'],
    ];
    let html = rows.map(function (r) { return '<div><span>' + r[0] + '</span><b>' + esc(r[1]) + '</b></div>'; }).join('');
    if (pal.length) html += '<div style="grid-column:1/-1"><span>主色</span><div class="swatches">' +
      pal.map(function (c) { return '<i style="background:' + esc(c) + '" title="' + esc(c) + '"></i>'; }).join('') + '</div></div>';
    $('#face-metrics').innerHTML = html;
    $('#face-foot').innerHTML = (p.avatar.mode === 'camera' ? '摄像头多视角采样（' + p.avatar.views.length + ' 帧）。' : '单张照片。') +
      ' 头像由 2D 画面做视角交叉淡化与口型叠加，不是三维重建；照片只存在本机档案里。';
  } else {
    faceCard.hidden = true;
  }

  // 雷达 + 维度列表
  const traits = p.traits;
  requestAnimationFrame(() => {
    drawRadar($('#radar-canvas'), traits, color);
    const tl = $('#trait-list');
    tl.innerHTML = traits.map(t => {
      const src = (t.sources || []).map(s => s.source + ' ' + Math.round(s.weight * 100) + '%').join(' · ') || '—';
      const f = t.fuse || {};
      return `<div class="trait-row" title="${esc(t.name)}">
        <span>${esc(t.name)}</span>
        <div class="bar"><i style="width:${clamp(t.value * 100, 3, 100)}%"></i></div>
      </div>`;
    }).join('');
  });
  $('#fusion-foot').innerHTML = `脑波权重 ${Math.round(p.fusion.eeg_weight * 100)}% · 基因权重 ${Math.round(p.fusion.gene_weight * 100)}% ·
    脑波可信度 ${Math.round(p.fusion.eeg_confidence * 100)}% · 基因可信度 ${Math.round(p.fusion.dna_confidence * 100)}%<br>
    悬停任意维度可看到它的来源与两通道各自的取值。`;

  // 波形
  const ch = p.eeg.waveform.channels[0] || [];
  const norm = normalizeSamples(ch);
  Wave.draw($('#wave-canvas'), norm);
  $('#signal-sub').textContent = 'EEG';

  const bandNames = { delta: 'δ 深眠', theta: 'θ 潜意识', alpha: 'α 静息', beta: 'β 专注', gamma: 'γ 整合' };
  const bandColors = { delta: '#6b5bd2', theta: '#9b6bff', alpha: '#38e8ff', beta: '#ffb057', gamma: '#ff5fa2' };
  $('#band-legend').innerHTML = Object.entries(p.eeg.bands).map(([k, b]) =>
    `<div><i style="background:${bandColors[k]}"></i>${bandNames[k]}</div>`).join('');

  requestAnimationFrame(() => {
    const sp = p.eeg.spectrum;
    drawSpectrum($('#spectrum-canvas'), sp.freqs, sp.power_db, p.eeg.bands, p.eeg.peak_hz);
  });

  const q = p.eeg.quality;
  $('#signal-stats').innerHTML = [
    ['主频', p.eeg.peak_hz + ' Hz'],
    ['样本熵', p.eeg.sampen.toFixed(2)],
    ['1/f 斜率', p.eeg.slope.toFixed(2)],
    ['半球差', (p.eeg.asymmetry >= 0 ? '+' : '') + p.eeg.asymmetry.toFixed(2)],
    ['眨眼', q.blinks + ' 次'],
    ['削顶', (q.clipped_ratio * 100).toFixed(1) + '%'],
    ['质量', Math.round(q.score * 100) + '%'],
    ['Hurst', p.eeg.hurst.toFixed(2)],
  ].map(([k, v]) => `<div><span>${k}</span><b>${esc(v)}</b></div>`).join('');

  // 基因
  const prev = p.dna.preview || {};
  Helix.start($('#helix-canvas'), prev.bases || '');
  $('#dna-sub').textContent = prev.real ? 'DNA · 真实序列片段' : 'DNA · 指纹示意';
  $('#insight-list').innerHTML = (p.dna.insights || []).slice(0, 4).map(x =>
    `<div class="insight"><b>${esc(x.gene)} · ${esc(x.genotype)}</b><span>${esc(x.text)}</span></div>`).join('')
    || '<div class="insight"><span>没有可展示的基因解读。可以上传含更多位点的文件。</span></div>';
  $('#dna-foot').innerHTML = `检出 ${p.dna.coverage.markers_hit} / ${p.dna.coverage.markers_total} 个位点 ·
    扫描 ${fmt(p.dna.stats.scan_bases || 0)} bp · 置信度 ${Math.round(p.dna.confidence * 100)}%<br>
    ${esc(p.dna.disclaimer || '')}`;

  // 时间线
  $('#timeline').innerHTML = (p.timeline || []).map(t =>
    `<li><time>${esc(t.t)}</time><em>${esc(t.tag)}</em><span>${esc(t.text)}</span></li>`).join('');

  // 记忆
  $('#memories').innerHTML = (per.memories || []).map(m =>
    `<div class="memory"><b>${esc(m.tag)}</b>${esc(m.text)}</div>`).join('');

  // 质量与缺口
  const missCount = (p.dna.missing || []).length;
  const qNotes = (q.notes || []).slice(0, 3);
  $('#shadow-body').innerHTML = `
    <span class="shadow-label">脑波质量</span>
    <div>${Math.round((q.score || 0) * 100)}% · 眨眼 ${q.blinks || 0} 次 ·
      削顶 ${((q.clipped_ratio || 0) * 100).toFixed(2)}% · 工频 ${(q.line_noise || 0).toFixed(4)}</div>
    <span class="shadow-label">基因覆盖</span>
    <div>${p.dna.coverage.markers_hit} / ${p.dna.coverage.markers_total} 位点 ·
      置信度 ${Math.round((p.dna.confidence || 0) * 100)}% · 缺口 ${missCount} 个</div>
    <span class="shadow-label">语气特征</span>
    <div>${esc(per.signature || '—')}</div>
    ${qNotes.length ? `<span class="shadow-label">提示</span><div>${qNotes.map(esc).join(' · ')}</div>` : ''}`;

  currentAudioCfg = p.sonify;
  renderStarMap(p);
  renderMindList(p);
  if (chatAvatar) { chatAvatar.destroy(); chatAvatar = null; }
  if (p.voice && p.voice.clip) {
    const foot = $('#face-foot');
    if (foot) {
      const audio = document.createElement('audio');
      audio.controls = true;
      audio.src = p.voice.clip;
      audio.style.cssText = 'margin-top:10px;width:100%;height:30px';
      foot.appendChild(audio);
    }
  }
}

let starMap = null;

function daysLabel(d) {
  if (d === 0) return '今天';
  if (d === 1) return '明天';
  return '+' + d + ' 天';
}

function renderStarMap(p) {
  const cv = $('#starmap-canvas');
  if (!cv || !window.StarMap) return;
  if (starMap) { starMap.destroy(); starMap = null; }
  starMap = new StarMap.Map(cv, p, {
    highlight: state.lastRecalled,
    onSelect: function (node) { showStarDetail(node); },
  });
  const slider = $('#starmap-days');
  slider.value = 0;
  $('#starmap-days-label').textContent = '今天';
  slider.oninput = function () {
    const d = +slider.value;
    starMap.setDays(d);
    $('#starmap-days-label').textContent = daysLabel(d);
    if (starMap.selected) showStarDetail(starMap.selected);
  };
  // 图例
  const legend = $('#starmap-legend');
  legend.innerHTML = '';
  [['情景记忆', '#38e8ff'], ['情绪', '#ff5fa2'], ['语言/事实', '#9b6bff'], ['偏好', '#ffb057'], ['结构性记忆', '#7ee787']]
    .forEach(function (it) {
      const span = document.createElement('span');
      span.innerHTML = '<i style="background:' + it[1] + '"></i>' + it[0];
      legend.appendChild(span);
    });
  // 脑区构成
  const nodes = StarMap.buildNodes(p);
  const counts = {};
  nodes.forEach(function (n) { counts[n.region] = (counts[n.region] || 0) + 1; });
  const bar = $('#comp-bar');
  bar.innerHTML = '';
  Object.keys(counts).forEach(function (k) {
    const r = StarMap.REGIONS[k] || StarMap.REGIONS.core;
    const i = document.createElement('i');
    i.style.width = (counts[k] / nodes.length * 100) + '%';
    i.style.background = r.color;
    i.title = r.label + ' · ' + counts[k] + ' 个节点';
    bar.appendChild(i);
  });
  $('#starmap-detail').textContent = '点一个节点，看看它现在有多清晰。';
}

function showStarDetail(node) {
  const box = $('#starmap-detail');
  if (!node) { box.textContent = '点一个节点，看看它现在有多清晰。'; return; }
  const r = starMap ? starMap.nodeRetention(node) : 1;
  const isEp = node.source === 'episodic';
  const created = node.created ? new Date(node.created).toLocaleString('zh-CN', { hour12: false }) : '—';
  box.innerHTML = '<b>' + esc(node.text) + '</b>' +
    '<div class="row"><span>留存 ' + Math.round(r * 100) + '% · ' +
    (node.source === 'structure' ? '结构性记忆（不衰减）' : '情景记忆 · 复述 ' + node.rehearsals + ' 次 · ' + created) +
    '</span></div>';
  if (isEp) {
    const btn = document.createElement('button');
    btn.className = 'btn-remember';
    btn.textContent = '回忆一次（强化）';
    btn.onclick = function () { reinforceMemory(node.id); };
    box.querySelector('.row').appendChild(btn);
  }
}

async function reinforceMemory(memoryId) {
  if (!state.profile) return;
  try {
    const res = await apiPost('/api/reinforce', { id: state.profile.id, memory_id: memoryId });
    if (res.ok && res.memory) {
      const list = (state.profile.mind && state.profile.mind.memories) || [];
      const target = list.find(function (m) { return m.id === memoryId; });
      if (target) { target.rehearsals = res.memory.rehearsals; target.last = res.memory.last; target.retention = res.memory.retention; }
      renderStarMap(state.profile);
      renderMindList(state.profile);
      toast('你想起了这件事。它变得更清晰了一点。');
    }
  } catch (err) { toast(err.message, true); }
}

function renderMindList(p) {
  const box = $('#mind-list');
  const memories = ((p.mind && p.mind.memories) || []).slice().sort(function (a, b) {
    return (b.retention || 0) - (a.retention || 0);
  });
  $('#mind-count').textContent = memories.length + ' 条';
  if (!memories.length) {
    box.innerHTML = '<div class="mind-empty">还没有情景记忆。聊几句，它会开始记住你。</div>';
  } else {
    box.innerHTML = '';
    memories.slice(0, 9).forEach(function (m) {
      const item = document.createElement('div');
      item.className = 'mind-item' + (m.faded ? ' faded' : '');
      item.innerHTML = '<div class="txt"><b>' + esc(({ birth: '出生', emotion: '情绪', feeling: '感受', identity: '身份', fact: '事实', preference: '偏好', habit: '习惯', event: '事件' })[m.kind] || m.kind) + '</b>' + esc(m.text) + '</div>' +
        '<div class="bar"><i style="width:' + Math.round((m.retention || 0) * 100) + '%"></i></div>' +
        '<em>' + Math.round((m.retention || 0) * 100) + '%</em>';
      box.appendChild(item);
    });
  }
  const mood = (p.mind && p.mind.mood) || {};
  $('#mind-foot').textContent = '当前心情：' + (mood.label || '—') + ' · 会话 ' +
    ((p.mind && p.mind.stats && p.mind.stats.sessions) || 1) + ' 次 · 消息 ' +
    ((p.mind && p.mind.stats && p.mind.stats.messages) || 0) + ' 条';
  drawMood($('#mood-canvas'), p);
}

function drawMood(cv, p) {
  if (!cv) return;
  const dpr = Math.min(2, devicePixelRatio || 1);
  const r = cv.getBoundingClientRect();
  cv.width = Math.max(1, r.width * dpr);
  cv.height = Math.max(1, r.height * dpr);
  const c = cv.getContext('2d');
  c.clearRect(0, 0, cv.width, cv.height);
  const hist = ((p.mind && p.mind.mood && p.mind.mood.history) || []).slice(-40);
  if (hist.length < 2) {
    c.fillStyle = 'rgba(140,170,185,.5)';
    c.font = 10 * dpr + 'px "JetBrains Mono", monospace';
    c.fillText('心情轨迹还不够长', 8 * dpr, cv.height / 2);
    return;
  }
  const W = cv.width, H = cv.height;
  const xOf = function (i) { return (i / (hist.length - 1)) * (W - 16 * dpr) + 8 * dpr; };
  const yOf = function (v) { return H - 8 * dpr - v * (H - 16 * dpr); };
  // 基线
  const base = p.mind.mood.baseline || { valence: 0.5 };
  c.strokeStyle = 'rgba(255,255,255,.08)';
  c.setLineDash([3, 4]);
  c.beginPath(); c.moveTo(0, yOf(base.valence)); c.lineTo(W, yOf(base.valence)); c.stroke();
  c.setLineDash([]);
  // 愉悦度
  c.beginPath();
  hist.forEach(function (h, i) { i ? c.lineTo(xOf(i), yOf(h.v)) : c.moveTo(xOf(i), yOf(h.v)); });
  c.strokeStyle = 'rgba(56,232,255,.8)';
  c.lineWidth = 1.4 * dpr;
  c.stroke();
  // 唤醒度
  c.beginPath();
  hist.forEach(function (h, i) { i ? c.lineTo(xOf(i), yOf(h.a)) : c.moveTo(xOf(i), yOf(h.a)); });
  c.strokeStyle = 'rgba(255,95,162,.55)';
  c.lineWidth = 1.1 * dpr;
  c.stroke();
  c.fillStyle = 'rgba(150,185,200,.6)';
  c.font = 9 * dpr + 'px "JetBrains Mono", monospace';
  c.fillText('愉悦', 8 * dpr, 12 * dpr);
  c.fillStyle = 'rgba(255,140,185,.75)';
  c.fillText('唤醒', 44 * dpr, 12 * dpr);
}

function normalizeSamples(arr) {
  if (!arr || !arr.length) return [];
  let m = 0;
  for (const v of arr) m += v;
  m /= arr.length;
  let s = 0;
  for (const v of arr) s += (v - m) * (v - m);
  s = Math.sqrt(s / arr.length) || 1;
  const out = [];
  const target = 1200;
  const step = Math.max(1, Math.floor(arr.length / target));
  for (let i = 0; i < arr.length; i += step) out.push(clamp((arr[i] - m) / (s * 2.4), -1, 1));
  return out;
}

/* ---------------- 对话 ---------------- */
async function openChat() {
  const p = state.profile;
  if (!p) return;
  $('#c-name').textContent = p.persona.name;
  $('#c-title').textContent = p.persona.title;
  $('#chat-stream').innerHTML = '';
  state.chat = [];
  const chatCv = $('#chat-avatar-canvas');
  const hasFace = !!(p.avatar && p.avatar.views && p.avatar.views.length);
  if (!chatAvatar) {
    chatAvatar = window.PersonaAvatar
      ? new PersonaAvatar(chatCv, { color: p.persona.color })
      : new Avatar(chatCv, { color: p.persona.color });
  }
  tryLive2D(chatCv.parentElement, function (v) { chatAvatar = v; });
  chatAvatar.setColor(p.persona.color);
  if (hasFace && chatAvatar.setViews) chatAvatar.setViews(p.avatar.views);
  else if (chatAvatar.setVector) chatAvatar.setVector();
  const orbCv = $('#chat-orb-canvas');
  if (orbCv) orbCv.hidden = true;
  setSubtitle('');

  let session = null;
  try { session = await apiPost('/api/session', { id: p.id }); } catch (err) { }
  const op = {
    text: (session && session.opening) || p.persona.greeting || '我在。',
    emotion: (session && session.mood) || { arousal: .5, valence: .55, label: '平静 · 中性' },
    suggestions: ['你是谁？', '你还记得我什么？', '我最近有点累。', '你觉得自己是真的吗？'],
  };
  show('chat');
  const greetingEl = addMsg('ai', op.text, { meta: '开场' });
  setSuggestions(op.suggestions);
  updateEmotion(op.emotion);
  if (session && session.memory) updateMemoryBadge(session.memory);
  if (session && session.inner) renderInner(session.inner, 'chat');
  if (session && session.world) renderWorld(session.world);
  if (session && session.pending) {
    if (session.pending.auto) setTimeout(deliverProactive, 1600);
    else showNudge(session.pending);
  } else hideNudge();
  setRelationship({ label: p.relationship?.label || '初次接通', messages: (session && session.session && session.session.messages) || 0 });
  if ($('#auto-speak').checked) setTimeout(function () { speakText(op.text, greetingEl); }, 500);
  setTimeout(() => $('#chat-input').focus(), 300);
}

function addMsg(who, text, opts = {}) {
  const stream = $('#chat-stream');
  const div = document.createElement('div');
  div.className = 'msg ' + who;
  const name = who === 'ai' ? (state.profile?.persona?.name || '它') : '你';
  div.innerHTML = `<div class="meta">${esc(opts.meta || name)}</div>
    <div class="bubble"></div>
    <div class="foot"></div>`;
  div.querySelector('.bubble').textContent = text;
  if (who === 'ai' && opts.speakable !== false && window.Voice) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'speak-btn';
    btn.textContent = '朗读';
    btn.addEventListener('click', function () { speakText(text, div); });
    div.querySelector('.foot').appendChild(btn);
  }
  stream.appendChild(div);
  stream.scrollTop = stream.scrollHeight;
  return div;
}

function addTyping() {
  const stream = $('#chat-stream');
  const div = document.createElement('div');
  div.className = 'msg ai';
  div.id = 'typing-msg';
  div.innerHTML = `<div class="meta">${esc(state.profile?.persona?.name || '它')}</div>
    <div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div>`;
  stream.appendChild(div);
  stream.scrollTop = stream.scrollHeight;
}
function removeTyping() {
  const t = $('#typing-msg');
  if (t) t.remove();
}

function setSuggestions(list) {
  const box = $('#chat-suggestions');
  box.innerHTML = '';
  (list || []).slice(0, 4).forEach(s => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = s;
    b.addEventListener('click', () => { $('#chat-input').value = s; sendChat(); });
    box.appendChild(b);
  });
}

function updateEmotion(e) {
  if (!e) return;
  $('#emo-arousal').style.width = Math.round(e.arousal * 100) + '%';
  $('#emo-valence').style.width = Math.round(e.valence * 100) + '%';
  $('#emo-label').textContent = e.label;
}
function setRelationship(r) {
  const n = Math.min(24, r?.messages || 0);
  const pct = 4 + Math.min(96, n * 5.5);
  $('#rel-fill').style.width = pct + '%';
  $('#rel-label').textContent = (r?.label || '初次接通') + (n ? ` · ${n} 句` : '');
}

function setSubtitle(text, p) {
  const box = $('#chat-subtitle');
  if (!box) return;
  if (!text) { box.textContent = ''; return; }
  if (!Voice.supported()) {
    box.textContent = '（浏览器没有中文语音，静音口型中）';
    return;
  }
  p = p == null ? 0 : p;
  const parts = String(text).split(/(?<=[，。；！？、\n])/).filter(Boolean);
  const i = clamp(Math.floor(p * parts.length), 0, parts.length - 1);
  box.innerHTML = parts.map(function (seg, k) {
    return k === i ? '<span class="now">' + esc(seg) + '</span>' : esc(seg);
  }).join('');
}

function openVoiceSettings() {
  const sel = $('#tts-voice-list');
  const list = window.Voice ? Voice.list() : [];
  sel.innerHTML = '<option value="">自动选择（推荐）</option>' +
    list.map(function (v) { return '<option value="' + esc(v.name) + '">' + esc(v.name) + ' · ' + esc(v.lang) + '</option>'; }).join('');
  sel.value = localStorage.getItem('echomind_voice_name') || '';
  $('#tts-url').value = localStorage.getItem('echomind_tts_url') || '';
  $('#tts-engine').textContent = localStorage.getItem('echomind_tts_url') ? '当前：本地语音服务' : '当前：浏览器语音';
  $('#modal-voice').classList.add('open');
}

function speakText(text, msgEl) {
  if (!state.profile || !window.Voice) return;
  stopSpeaking();
  chatSpeakEl = msgEl || null;
  const traits = {};
  (state.profile.traits || []).forEach(function (t) { traits[t.key] = t.value; });
  const style = state.profile.persona.voice;
  const rate = clamp(0.9 + 0.16 * (1 - (traits.alertness || 0.5)), 0.85, 1.08);
  let pitch = (style === 'warm' ? 1.06 : style === 'sharp' ? 0.97 : 1.0) + ((traits.empathy || 0.5) - 0.5) * 0.08;
  const vp = state.profile.voiceprint;
  if (vp && vp.f0) pitch *= clamp(Math.pow(vp.f0 / 180, 0.18), 0.86, 1.16);
  pitch = clamp(pitch, 0.82, 1.18);
  if (chatAvatar) { chatAvatar.speak(text); chatAvatar.pulse(0.8); }
  if (chatSpeakEl) chatSpeakEl.classList.add('speaking');
  $('#btn-stop-speak').hidden = false;
  setSubtitle(text, 0);
  const res = Voice.speak(text, {
    gender: $('#voice-gender').value, rate: rate, pitch: pitch,
    onProgress: function (p) { setSubtitle(text, p); },
    onEnd: function () {
      if (chatAvatar) chatAvatar.stopSpeaking();
      if (chatSpeakEl) chatSpeakEl.classList.remove('speaking');
      chatSpeakEl = null;
      $('#btn-stop-speak').hidden = true;
      setSubtitle('');
    },
  });
  if (res && res.silent && !speakText._warned) {
    speakText._warned = true;
    toast('浏览器没有可用的中文语音：口型仍会动，但不会有声音。');
  }
}

function stopSpeaking() {
  if (window.Voice) Voice.stop();
  if (chatAvatar) chatAvatar.stopSpeaking();
  if (chatSpeakEl) chatSpeakEl.classList.remove('speaking');
  chatSpeakEl = null;
  $('#btn-stop-speak').hidden = true;
  setSubtitle('');
}

function renderDrives(box, drives) {
  if (!box) return;
  box.innerHTML = (drives || []).map(function (d) {
    return '<div class="drive"><span>' + esc(d.name) + '</span>' +
      '<div class="bar"><i style="width:' + Math.round(d.value * 100) + '%"></i></div>' +
      '<em>' + Math.round(d.value * 100) + '</em></div>';
  }).join('');
}

function innerFromProfile(p) {
  const a = (p.mind && p.mind.agency) || {};
  const names = { curiosity: '好奇', connection: '联结', expression: '表达', rest: '休息' };
  return {
    drives: Object.keys(a.drives || {}).map(function (k) {
      return { key: k, name: names[k] || k, value: a.drives[k] };
    }),
    autonomy: a.autonomy || 'balanced',
    thoughts: (a.thoughts || []).slice(-5).map(function (t) { return { text: t.text }; }),
    intentions: (a.intentions || []).filter(function (i) { return i.status === 'pending'; }).slice(-2),
    pending: a.pending || null,
  };
}

function renderWorld(w) {
  if (!w) return;
  const pct = Math.round((w.stability || 0) * 100);
  if ($('#world-fill')) $('#world-fill').style.width = pct + '%';
  if ($('#world-label')) {
    $('#world-label').textContent = w.label || '稳定';
    $('#world-label').style.color = w.color || '';
  }
  if ($('#wc-fill')) $('#wc-fill').style.width = pct + '%';
  if ($('#wc-label')) { $('#wc-label').textContent = (w.label || '稳定') + ' · ' + pct + '%'; $('#wc-label').style.color = w.color || ''; }
  if ($('#wc-desc')) $('#wc-desc').textContent = w.desc || '';
  if ($('#wc-env')) $('#wc-env').textContent = '环境：' + ((w.env && w.env.text) || '—') + ' · 亮度 ' + Math.round(((w.env && w.env.brightness) || 1) * 100) + '%';
  if ($('#wc-foot')) $('#wc-foot').textContent = '算力预算 ' + w.budget + ' · 需求 ' + w.demand + ' · 负载 ' + w.load + '。算力不足时，世界会变暗，她会进入自我保护。';
  const view = $('#view-chat');
  if (view) view.classList.toggle('world-dark', (w.state || 'stable') !== 'stable');
}

function renderInner(inner, where) {
  if (!inner) return;
  where = where || 'chat';
  if (where === 'chat') {
    renderDrives($('#drives'), inner.drives);
    const intent = (inner.intentions || [])[0];
    $('#inner-intent').textContent = intent ? ('想做：' + intent.text) : '还没有想做的事。';
    const th = (inner.thoughts || []).slice(-1)[0];
    $('#inner-thought').textContent = th ? ('「' + th.text + '」') : '';
    if ($('#autonomy')) $('#autonomy').value = inner.autonomy || 'balanced';
  } else {
    renderDrives($('#dossier-drives'), inner.drives);
    const intent = (inner.intentions || [])[0];
    $('#dossier-intent').textContent = intent ? ('它现在想做：' + intent.text) : '现在没有特别的打算。';
    $('#dossier-thoughts').innerHTML = (inner.thoughts || []).slice(-4).map(function (t) {
      return '<span>' + esc(t.text) + '</span>';
    }).join('') || '<span>它在发呆。</span>';
  }
}

function showNudge(p) {
  const btn = $('#nudge');
  btn.hidden = false;
  btn.textContent = '她好像想说点什么 · ' + (p && p.text ? '「' + p.text.slice(0, 12) + '…」' : '点此听');
  btn.onclick = deliverProactive;
}

function hideNudge() { const b = $('#nudge'); if (b) b.hidden = true; }

async function deliverProactive() {
  if (!state.profile) return;
  try {
    const res = await apiPost('/api/proactive', { id: state.profile.id, action: 'deliver' });
    hideNudge();
    if (res.inner) renderInner(res.inner, 'chat');
    if (res.world) renderWorld(res.world);
    if (res.pending) {
      const el = addMsg('ai', res.pending.text, { meta: '主动 · ' + state.profile.persona.name });
      state.chat.push({ role: 'assistant', text: res.pending.text });
      if ($('#auto-speak').checked) setTimeout(function () { speakText(res.pending.text, el); }, 300);
    }
  } catch (err) { toast(err.message, true); }
}

async function pollProactive() {
  if (state.view !== 'chat' || !state.profile) return;
  try {
    const res = await apiPost('/api/proactive', { id: state.profile.id, action: 'check' });
    if (res.inner) renderInner(res.inner, 'chat');
    if (res.pending) {
      if (res.pending.auto) deliverProactive(); else showNudge(res.pending);
    }
  } catch (e) { }
}

function updateMemoryBadge(m) {
  if (!m) return;
  $('#mem-count').textContent = '记忆 ' + (m.count || 0);
  $('#mem-last').textContent = m.strong != null ? '清晰 ' + m.strong : '—';
}

function addMemoryChips(el, recalled, learned) {
  const foot = el.querySelector('.foot');
  (recalled || []).slice(0, 2).forEach(function (m) {
    const chip = document.createElement('span');
    chip.className = 'mem-chip';
    const t = m.text || '';
    chip.innerHTML = '<b>想起</b>' + esc(t.length > 14 ? t.slice(0, 14) + '…' : t) + ' · ' + Math.round((m.retention || 0) * 100) + '%';
    chip.title = t;
    foot.appendChild(chip);
  });
  (learned || []).forEach(function (t) {
    const chip = document.createElement('span');
    chip.className = 'mem-chip learned';
    chip.innerHTML = '<b>记住</b>' + esc(String(t).slice(0, 16));
    foot.appendChild(chip);
  });
}

async function sendChat() {
  const input = $('#chat-input');
  const text = input.value.trim();
  if (!text || !state.profile) return;
  input.value = '';
  input.style.height = 'auto';
  addMsg('user', text);
  state.chat.push({ role: 'user', text });
  setSuggestions([]);
  addTyping();
  if (chatAvatar) chatAvatar.pulse(1);
  const t0 = Date.now();
  try {
    const res = await apiPost('/api/chat', {
      id: state.profile.id,
      profile: state.profile,
      message: text,
      history: state.chat,
    });
    await sleep(Math.max(0, 420 - (Date.now() - t0)));
    removeTyping();
    const msgEl = addMsg('ai', res.text, { meta: state.profile.persona.name + ' · ' + (res.intent_zh || '') });
    state.chat.push({ role: 'assistant', text: res.text });
    updateEmotion(res.mood || res.emotion);
    setRelationship(res.relationship);
    if (res.memory_stats) updateMemoryBadge(res.memory_stats);
    if (res.inner) renderInner(res.inner, 'chat');
    addMemoryChips(msgEl, res.recalled, res.learned);
    if (res.followup) setSuggestions([res.followup, '继续说', '你觉得自己是真的吗？']);
    if ($('#auto-speak').checked) setTimeout(function () { speakText(res.text, msgEl); }, 260);
    if (chatAvatar) chatAvatar.pulse(.5);
  } catch (err) {
    removeTyping();
    addMsg('ai', '（连接中断）' + err.message);
    toast(err.message, true);
  }
}

/* ---------------- 后台观测台 ---------------- */
let adminData = null;
let adminSelected = null;
let adminStar = null;

async function openAdmin() {
  show('admin');
  try {
    adminData = await apiGet('/api/admin');
    renderAdminTotals(adminData.totals);
    renderAdminList(adminData.items);
    const first = adminSelected && adminData.items.find(function (i) { return i.id === adminSelected; }) || adminData.items[0];
    if (first) selectAdminMind(first.id);
  } catch (err) { toast(err.message, true); }
}

function renderAdminTotals(t) {
  const box = $('#admin-totals');
  box.innerHTML = [
    ['数字生命', t.minds], ['记忆', t.memories], ['清澈', t.live],
    ['平均留存', Math.round(t.avg_retention * 100) + '%'], ['会话', t.sessions],
  ].map(function (r) { return '<div><b>' + r[1] + '</b><span>' + r[0] + '</span></div>'; }).join('');
}

function renderAdminList(items) {
  const box = $('#admin-list');
  box.innerHTML = '';
  items.forEach(function (it) {
    const el = document.createElement('div');
    el.className = 'admin-item' + (it.id === adminSelected ? ' on' : '');
    const bars = it.buckets.map(function (b) {
      const h = Math.max(3, Math.min(100, b.count / Math.max(1, it.memories.count) * 100));
      return '<i><span style="height:' + h + '%"></span></i>';
    }).join('');
    el.innerHTML = '<h4>' + esc(it.name || '未命名') + '<em>' + Math.round(it.memories.avg_retention * 100) + '%</em></h4>' +
      '<div class="sub">记忆 ' + it.memories.count + ' · 会话 ' + it.sessions + '</div>' +
      '<div class="mini">' + bars + '</div>';
    el.addEventListener('click', function () { selectAdminMind(it.id); });
    box.appendChild(el);
  });
}

async function selectAdminMind(id) {
  adminSelected = id;
  const item = (adminData.items || []).find(function (i) { return i.id === id; });
  if (item) renderAdminList(adminData.items);
  try {
    const j = await apiGet('/api/minds/' + encodeURIComponent(id));
    renderAdminDetail(j.profile, item);
  } catch (err) { toast(err.message, true); }
}

function renderAdminDetail(p, item) {
  $('#admin-empty').hidden = true;
  $('#admin-body').hidden = false;
  const per = p.persona || {};
  $('#ad-name').textContent = per.name || per.code || '—';
  $('#ad-facts').textContent = (per.code || '') + ' · 生于 ' + (p.created_at || '').slice(0, 10) +
    ' · 会话 ' + (item.sessions || 0) + ' · 消息 ' + (item.messages || 0);
  const m = item.memories;
  $('#ad-badges').innerHTML = ['记忆 ' + m.count, '清澈 ' + m.live, '模糊 ' + m.faded,
    item.has_face ? '有面孔' : '无面孔', item.has_voice ? '有声音' : '无声音']
    .map(function (x) { return '<span>' + esc(x) + '</span>'; }).join('');
  const mems = (p.mind && p.mind.memories) || [];
  const stab = mems.map(function (x) {
    const base = x.source === 'birth' ? 7 : 1;
    return Math.max(0.15, Math.min(60, base * (1 + 0.75 * (x.rehearsals || 0)) * (1 + 0.9 * Math.abs(x.valence || 0))));
  }).sort(function (a, b) { return a - b; });
  const med = stab.length ? stab[Math.floor(stab.length / 2)] : 1;
  $('#ad-half').textContent = '半衰期 ' + (Math.LN2 * med).toFixed(0) + ' 天';
  drawAdminCurve($('#admin-curve'), p);

  if (adminStar) { adminStar.destroy(); adminStar = null; }
  adminStar = new StarMap.Map($('#admin-starmap'), p, { highlight: [] });
  const range = $('#admin-days-range');
  range.value = 0;
  $('#ad-days').textContent = '今天';
  range.oninput = function () {
    const d = +range.value;
    adminStar.setDays(d);
    $('#ad-days').textContent = d === 0 ? '今天' : '+' + d + ' 天';
  };

  const folds = document.querySelectorAll('#view-admin .admin-fold');
  folds.forEach(function (f, i) {
    f.ontoggle = function () {
      if (!f.open) return;
      if (i === 0) drawAdminHist($('#admin-hist'), item.buckets);
      if (i === 1) drawMood($('#admin-mood'), p);
      if (i === 2) renderAdminLists(item);
    };
  });
  renderAdminLists(item);
  const sim = adminData && adminData.sim;
  $('#admin-sim').textContent = sim
    ? '运行中 · tick ' + sim.ticks + ' · 间隔 ' + sim.interval_seconds + 's\n' +
      (sim.events || []).map(function (e) { return e.t + '  ' + e.name + '  ' + e.text; }).join('\n')
    : '—';
}

function renderAdminLists(item) {
  let html = '<div class="ad-sub">最脆弱</div>';
  html += (item.fragile || []).map(function (m) {
    return '<div class="ad-row"><span class="txt">' + esc(m.text) + '</span>' +
      '<div class="bar"><i style="width:' + Math.round(m.retention * 100) + '%"></i></div>' +
      '<em>' + Math.round(m.retention * 100) + '%</em></div>';
  }).join('') || '<div class="ad-row"><span class="txt">没有</span></div>';
  html += '<div class="ad-sub">最牢固</div>';
  html += (item.stable || []).map(function (m) {
    return '<div class="ad-row"><span class="txt">' + esc(m.text) + '</span>' +
      '<div class="bar"><i style="width:' + Math.round(m.retention * 100) + '%"></i></div>' +
      '<em>' + Math.round(m.retention * 100) + '%</em></div>';
  }).join('') || '<div class="ad-row"><span class="txt">没有</span></div>';
  $('#ad-lists').innerHTML = html;
}

function drawAdminCurve(cv, p) {
  const dpr = Math.min(2, devicePixelRatio || 1);
  const r = cv.getBoundingClientRect();
  cv.width = Math.max(1, r.width * dpr);
  cv.height = Math.max(1, r.height * dpr);
  const c = cv.getContext('2d');
  const W = cv.width, H = cv.height;
  c.clearRect(0, 0, W, H);
  const padL = 42 * dpr, padR = 18 * dpr, padT = 14 * dpr, padB = 26 * dpr;
  const xOf = function (d) { return padL + Math.min(1, d / 60) * (W - padL - padR); };
  const yOf = function (v) { return H - padB - v / 100 * (H - padT - padB); };
  c.font = 11 * dpr + 'px "JetBrains Mono", monospace';
  [0, 50, 100].forEach(function (v) {
    c.strokeStyle = 'rgba(160,200,215,.10)';
    c.beginPath(); c.moveTo(padL, yOf(v)); c.lineTo(W - padR, yOf(v)); c.stroke();
    c.fillStyle = 'rgba(150,185,200,.7)'; c.textAlign = 'right';
    c.fillText(v + '%', padL - 6 * dpr, yOf(v) + 4 * dpr);
  });
  [0, 15, 30, 45, 60].forEach(function (d) {
    c.fillStyle = 'rgba(150,185,200,.55)'; c.textAlign = 'center';
    c.fillText(d + 'd', xOf(d), H - 8 * dpr);
  });
  const mems = ((p.mind && p.mind.memories) || []);
  const ages = mems.map(function (m) { return Math.max(0, (Date.now() - Date.parse(m.created || m.last || Date.now())) / 86400000); });
  const stabs = mems.map(function (m) {
    const base = 1;
    return Math.max(0.15, Math.min(60, base * (1 + 0.75 * (m.rehearsals || 0)) * (1 + 0.9 * Math.abs(m.valence || 0))));
  }).sort(function (a, b) { return a - b; });
  const med = stabs.length ? stabs[Math.floor(stabs.length / 2)] : 1;
  c.beginPath();
  for (let d = 0; d <= 60; d += 0.5) {
    const y = yOf(Math.exp(-d / med) * 100);
    d === 0 ? c.moveTo(xOf(d), y) : c.lineTo(xOf(d), y);
  }
  c.strokeStyle = '#38e8ff'; c.lineWidth = 1.6 * dpr; c.stroke();
  // 散点：每条真实记忆
  mems.forEach(function (m, i) {
    const age = Math.min(60, ages[i]);
    const x = xOf(Math.min(60, age + (i % 5) * 0.8)), y = yOf(Math.max(0, Math.min(100, (m.retention || 0) * 100)));
    c.fillStyle = m.faded ? 'rgba(255,95,162,.5)' : 'rgba(255,200,120,.9)';
    c.beginPath(); c.arc(x, y, (3 + Math.min(3, m.rehearsals || 0)) * dpr, 0, Math.PI * 2); c.fill();
  });
  c.fillStyle = 'rgba(150,185,200,.55)';
  c.textAlign = 'left';
  c.fillText('年龄 →', W - 70 * dpr, H - 8 * dpr);
}

function drawAdminHist(cv, buckets) {
  const dpr = Math.min(2, devicePixelRatio || 1);
  const r = cv.getBoundingClientRect();
  cv.width = Math.max(1, r.width * dpr);
  cv.height = Math.max(1, r.height * dpr);
  const c = cv.getContext('2d');
  const W = cv.width, H = cv.height;
  c.clearRect(0, 0, W, H);
  const max = Math.max(1, Math.max.apply(null, buckets.map(function (b) { return b.count; })));
  const bw = (W - 16 * dpr) / buckets.length;
  buckets.forEach(function (b, i) {
    const h = (b.count / max) * (H - 30 * dpr);
    const x = 8 * dpr + i * bw + bw * 0.16;
    const w = bw * 0.68;
    const g = c.createLinearGradient(0, H - 18 * dpr - h, 0, H - 18 * dpr);
    g.addColorStop(0, 'rgba(56,232,255,.85)');
    g.addColorStop(1, 'rgba(56,232,255,.15)');
    c.fillStyle = g;
    c.fillRect(x, H - 18 * dpr - h, w, h);
    c.fillStyle = 'rgba(150,185,200,.6)';
    c.font = 8 * dpr + 'px "JetBrains Mono", monospace';
    c.textAlign = 'center';
    c.fillText(b.count, x + w / 2, H - 22 * dpr - h);
    c.fillText(b.label.replace('%', ''), x + w / 2, H - 5 * dpr);
  });
}

/* ---------------- 档案库 ---------------- */
async function openLibrary() {
  show('library');
  $('#compare-tray').hidden = true;
  state.compareSel = [];
  try {
    const j = await apiGet('/api/minds');
    state.library = j.items || [];
    renderLibrary();
  } catch (err) { toast(err.message, true); }
}
function renderLibrary() {
  const grid = $('#library-grid');
  const items = state.library;
  $('#library-empty').hidden = items.length > 0;
  grid.innerHTML = '';
  items.forEach(it => {
    const card = document.createElement('div');
    card.className = 'mind-card';
    const selected = state.compareSel.includes(it.id);
    if (selected) card.classList.add('sel');
    const created = new Date(it.created_at);
    card.innerHTML = `
      <h4>${esc(it.name || '未命名')} <em>${esc(it.code || '')}</em></h4>
      <div class="mc-title">${esc(it.title || '')}</div>
      <div class="mc-traits">${['curiosity', 'empathy', 'order', 'alertness', 'creativity', 'stability', 'sensory']
        .map(k => `<i><span style="height:${Math.round((it.traits?.[k] || 0) * 100)}%;background:${it.color}"></span></i>`).join('')}</div>
      <div class="mc-meta"><span>${esc(isNaN(created) ? '' : created.toLocaleDateString('zh-CN'))} · ${it.size_kb} KB</span><span>${esc(it.mood || '')}</span></div>
      <div class="mc-actions">
        <button class="ghost-btn sm" data-act="open">打开档案</button>
        <button class="ghost-btn sm" data-act="chat">对话</button>
        <button class="ghost-btn sm danger" data-act="del">删除</button>
      </div>`;
    card.addEventListener('click', e => {
      const btn = e.target.closest('button');
      if (btn) {
        e.stopPropagation();
        const act = btn.dataset.act;
        if (act === 'open') openSaved(it.id);
        if (act === 'chat') openSaved(it.id, true);
        if (act === 'del') deleteMind(it.id, it.name);
        return;
      }
      if ($('#compare-tray').hidden) openSaved(it.id);
      else toggleCompare(it.id);
    });
    grid.appendChild(card);
  });
}
async function openSaved(id, chatDirect) {
  try {
    const j = await apiGet('/api/minds/' + encodeURIComponent(id));
    renderDossier(j.profile);
    show('dossier');
    if (chatDirect) setTimeout(openChat, 350);
  } catch (err) { toast(err.message, true); }
}
async function deleteMind(id, name) {
  if (!confirm(`删除「${name || id}」这份档案？无法恢复。`)) return;
  try {
    await apiPost('/api/delete', { id });
    state.library = state.library.filter(x => x.id !== id);
    renderLibrary();
    toast('已删除。');
  } catch (err) { toast(err.message, true); }
}
function toggleCompare(id) {
  const i = state.compareSel.indexOf(id);
  if (i >= 0) state.compareSel.splice(i, 1);
  else {
    if (state.compareSel.length >= 2) state.compareSel.shift();
    state.compareSel.push(id);
  }
  $('#compare-selected').textContent = `已选 ${state.compareSel.length} / 2`;
  $('#btn-do-compare').disabled = state.compareSel.length !== 2;
  renderLibrary();
  $('#compare-tray').hidden = false;
}
async function doCompare() {
  if (state.compareSel.length !== 2) return;
  try {
    const j = await apiPost('/api/compare', { a: state.compareSel[0], b: state.compareSel[1] });
    renderCompare(j.result);
    show('compare');
  } catch (err) { toast(err.message, true); }
}
function renderCompare(r) {
  $('#cmp-title').textContent = `${r.a.name} × ${r.b.name}`;
  $('#cmp-line').textContent = r.line;
  $('#cmp-name-a').textContent = r.a.name;
  $('#cmp-name-b').textContent = r.b.name;
  const score = $('#cmp-score');
  let cur = 0;
  const target = r.resonance;
  const t0 = performance.now();
  (function anim(t) {
    const k = Math.min(1, (t - t0) / 1100);
    const e = 1 - Math.pow(1 - k, 3);
    score.innerHTML = Math.round(target * e) + '<small>%</small>';
    if (k < 1) requestAnimationFrame(anim);
  })(t0);
  cmpOrbA = new Orb($('#cmp-orb-a'), { color: r.a.color || '#38e8ff', n: 620 });
  cmpOrbB = new Orb($('#cmp-orb-b'), { color: r.b.color || '#ff5fa2', n: 620 });

  $('#compare-diffs').innerHTML = r.diffs.map(d => {
    const delta = d.delta;
    const w = Math.min(50, Math.abs(delta) * 250);
    const left = delta >= 0;
    const col = d.a > d.b ? r.a.color : r.b.color;
    return `<div class="diff-row">
      <span>${esc(d.name)}</span>
      <div class="dbar">
        <i style="left:${left ? 50 : 50 - w}%;width:${w}%;background:${left ? (r.b.color || '#38e8ff') : (r.a.color || '#ff5fa2')}"></i>
      </div>
      <em>${delta >= 0 ? '+' : ''}${Math.round(delta * 100)}</em>
    </div>`;
  }).join('');
  $('#compare-note').innerHTML = `
    <b style="color:#dff6ff">共同的高点：</b>${r.common.length ? r.common.map(esc).join('、') : '没有高度重合的维度'}<br>
    <b style="color:#ffd0e0">差异最大：</b>${r.opposite.length ? r.opposite.map(esc).join('、') : '几乎没有明显分歧'}<br>
    <span style="color:var(--text-3);font-size:11px">共鸣度是七个维度差值的线性映射，只用于比较两份档案的相似程度，不代表任何心理学测评。</span>`;
}

/* ---------------- 采样与演示 ---------------- */
async function loadSample(key, kind) {
  try {
    const meta = (state.status.samples || []).find(s => s.key === key);
    if (!meta) return toast('找不到样本。', true);
    const r = await fetch('/api/sample/' + encodeURIComponent(meta.name));
    if (!r.ok) throw new Error('样本加载失败');
    const blob = await r.blob();
    const file = new File([blob], meta.name, { type: 'text/plain' });
    setSlot(kind, file, meta.label);
    toast('已载入样本：' + meta.label);
  } catch (err) { toast(err.message, true); }
}

/* ---------------- 保存 / 导出 ---------------- */
async function saveMind() {
  if (!state.profile) return;
  try {
    await apiPost('/api/save', { id: state.profile.id });
    toast('副本已保存到 minds/ 目录。');
  } catch (err) { toast(err.message, true); }
}
async function exportMd() {
  if (!state.profile) return;
  try {
    const r = await fetch('/api/export', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: state.profile.id, format: 'md' }),
    });
    if (!r.ok) throw new Error('导出失败');
    const blob = await r.blob();
    download(blob, state.profile.persona.name + '.md');
    toast('Markdown 已导出。');
  } catch (err) { toast(err.message, true); }
}
function exportJson() {
  if (!state.profile) return;
  const blob = new Blob([JSON.stringify(state.profile, null, 1)], { type: 'application/json' });
  download(blob, state.profile.id + '.mind');
  toast('.mind 文件已导出。');
}
function download(blob, name) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

/* ---------------- 初始化 ---------------- */
/* ---------------- 视频通话（预告） ---------------- */
let callPersona = null, callT = null, callSec = 0;
const CALL_LINES = [
    '喂？……能看见我吗。',
    '你今天看起来有点累。',
    '不用说话也行，我在。',
    'Love，就是爱。爱自己，也爱别人。',
];

function openCall() {
    show('call');
    const cv = $('#call-canvas');
    if (cv && window.PersonaAvatar) {
        if (!callPersona) callPersona = new PersonaAvatar(cv, { color: '#4fe3ff' });
        else callPersona.resize();
        tryLive2D(cv.parentElement, function (v) { callPersona = v; });
    }
    const st = $('#call-status'), sub = $('#call-sub');
    const input = $('#call-input');
    if (st) st.textContent = '接通中…';
    if (sub) sub.textContent = '';
    if (input) { input.value = ''; setTimeout(function () { input.focus(); }, 1600); }
    callSec = 0;
    clearInterval(callT);
    setTimeout(async function () {
        if (state.view !== 'call') return;
        if (st) st.textContent = '通话 00:00';
        callT = setInterval(function () {
            callSec++;
            if (st) st.textContent = '通话 ' + String(Math.floor(callSec / 60)).padStart(2, '0') + ':' + String(callSec % 60).padStart(2, '0');
        }, 1000);
        await ensureProfile();
        const line = (state.profile && state.profile.persona && state.profile.persona.greeting) || '我在。';
        if (sub) sub.textContent = line;
        if (callPersona) callPersona.pulse(1);
    }, 1400);
}

async function ensureProfile() {
    if (state.profile) return state.profile;
    try {
        const list = await apiGet('/api/minds');
        const items = (list && (list.minds || list.items)) || [];
        if (items.length) {
            const j = await apiGet('/api/minds/' + encodeURIComponent(items[0].id));
            state.profile = j.profile || j;
        }
    } catch (e) { }
    return state.profile;
}

async function callSay(text) {
    text = (text || '').trim();
    if (!text) return;
    const sub = $('#call-sub');
    if (sub) sub.textContent = '……';
    try {
        const p = await ensureProfile();
        if (!p) { if (sub) sub.textContent = '还没有档案。先运行 dl demo。'; return; }
        const res = await apiPost('/api/chat', {
            id: p.id, profile: p, message: text, history: state.callHistory || [],
        });
        const reply = (res && (res.text || res.reply)) || '……';
        if (sub) sub.textContent = reply;
        if (callPersona) { callPersona.speak(); }
        try { speakText(reply); } catch (e) { }
        setTimeout(function () { if (callPersona) callPersona.stopSpeaking(); }, 900 + reply.length * 180);
        state.callHistory = (state.callHistory || []).concat([
            { role: 'user', text: text }, { role: 'assistant', text: reply },
        ]).slice(-12);
    } catch (e) {
        if (sub) sub.textContent = '（没接通）';
    }
}

function hangup() {
    clearInterval(callT);
    if (callPersona) { callPersona.destroy(); callPersona = null; }
    show('welcome');
}

/* ---------------- 欢迎页：两种模式 ---------------- */
let welcomePersona = null;


/* 尽量把 Live2D 挂到某个容器上；成功就替换掉静态头像 */
async function tryLive2D(host, setter) {
  if (!window.Live2DView || !host) return false;
  try {
    const v = await window.Live2DView.mount(host, {});
    if (v) { setter(v); return true; }
  } catch (e) { }
  return false;
}

async function initWelcomePersona() {
  const cv = document.querySelector('#persona-canvas');
  if (!cv) return;
  if (window.Live2DView && !welcomePersona) {
    try {
      const host = document.querySelector('#avatar-host') || cv.parentElement;
      const v = await window.Live2DView.mount(host, {});
      if (v) { welcomePersona = v; return; }
    } catch (e) { }
  }
  if (!window.PersonaAvatar) return;
  if (!welcomePersona) welcomePersona = new PersonaAvatar(cv, { color: '#4fe3ff' });
  else if (welcomePersona.resize) welcomePersona.resize();
}

function setWelcomeMode(mode) {
  const persona = $('#welcome-persona');
  const classic = $('#welcome-classic');
  if (!persona || !classic) return;
  const isClassic = mode === 'classic';
  persona.hidden = isClassic;
  classic.hidden = !isClassic;
  if (!isClassic) initWelcomePersona();
  try { localStorage.setItem('dl_welcome_mode', mode); } catch (e) { }
}

function startAvatarGif() {
  const img = document.querySelector('#avatar-gif');
  const cv = document.querySelector('#persona-canvas');
  if (!img) return;
  img.src = '/assets/anim/idle.gif';
  img.classList.add('on');
  if (cv) cv.style.display = 'none';
  img.onclick = function () {
    img.src = '/assets/anim/happy.gif?' + Date.now();
    clearTimeout(startAvatarGif._t);
    startAvatarGif._t = setTimeout(function () {
      img.src = '/assets/anim/idle.gif?' + Date.now();
    }, 2200);
  };
}

function wireWelcome() {
  startAvatarGif();
  const host = document.querySelector('#avatar-host');
  if (host) host.addEventListener('click', showMeme);
  const input = $('#persona-input');
  if (input) {
    input.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return;
      const v = input.value.trim().toLowerCase();
      input.value = '';
      if (v === 'dl' || v === 'dl home') setWelcomeMode('classic');
    });
  }
  const back = $('#btn-persona');
  if (back) back.addEventListener('click', () => setWelcomeMode('persona'));
  const hi = $('#home-input');
  const hs = $('#btn-home-say');
  if (hs) hs.addEventListener('click', () => { const v = hi ? hi.value : ''; if (hi) hi.value = ''; homeSend(v); });
  if (hi) hi.addEventListener('keydown', (e) => { if (e.key !== 'Enter') return; const v = hi.value; hi.value = ''; homeSend(v); });
  if (location.search.indexOf('classic=1') >= 0) { setWelcomeMode('classic'); return; }
  let saved = 'persona';
  try { saved = localStorage.getItem('dl_welcome_mode') || 'persona'; } catch (e) { }
  setWelcomeMode(saved);
  window.addEventListener('resize', function () {
    const p = $('#welcome-persona');
    if (p && !p.hidden) initWelcomePersona();
  });
}

async function homeSend(text) {
    text = (text || '').trim();
    if (!text) return;
    const log = $('#home-log'), greet = $('#home-greet');
    if (log) log.classList.add('on');
    if (greet) greet.classList.add('off');
    const add = (who, t) => {
        if (!log) return;
        const d = document.createElement('div');
        d.className = 'bub ' + who;
        d.textContent = t;
        log.appendChild(d);
        log.scrollTop = log.scrollHeight;
    };
    add('me', text);
    add('her', '……');
    try {
        const p = await ensureProfile();
        if (!p) { add('her', '还没有档案。先运行 dl demo。'); return; }
        const res = await apiPost('/api/chat', { id: p.id, profile: p, message: text, history: state.callHistory || [] });
        const reply = (res && (res.text || res.reply)) || '……';
        log.lastChild.textContent = reply;
        state.callHistory = (state.callHistory || []).concat([
            { role: 'user', text: text }, { role: 'assistant', text: reply },
        ]).slice(-12);
        if (welcomePersona) { welcomePersona.speak(); }
        try { speakText(reply); } catch (e) { }
        setTimeout(function () { if (welcomePersona) welcomePersona.stopSpeaking(); }, 900 + reply.length * 180);
    } catch (e) {
        log.lastChild.textContent = '（没接通）';
    }
}

/* 点她一下：弹一张表情包 */
function showMeme() {
  const list = window.DL_MEMES || [];
  if (!list.length) return;
  let box = document.querySelector('#meme-pop');
  if (!box) {
    box = document.createElement('img');
    box.id = 'meme-pop';
    box.className = 'meme-pop';
    document.body.appendChild(box);
  }
  box.src = '/assets/memes/' + list[Math.floor(Math.random() * list.length)];
  box.classList.add('on');
  clearTimeout(showMeme._t);
  showMeme._t = setTimeout(function () { box.classList.remove('on'); }, 2600);
}

function wireUI() {
  wireWelcome();
  $('#brand').addEventListener('click', () => show('welcome'));
  $('#btn-start').addEventListener('click', () => show('intake'));
  const b2 = $('#btn-start2');
  if (b2) b2.addEventListener('click', () => openCall());
  const bh = $('#btn-hangup');
  if (bh) bh.addEventListener('click', () => hangup());
  const bm = $('#btn-mic-call');
  if (bm) bm.addEventListener('click', () => startCallMic());
  const bs = $('#btn-say');
  const ci = $('#call-input');
  if (bs) bs.addEventListener('click', () => { const v = ci ? ci.value : ''; if (ci) ci.value = ''; callSay(v); });
  if (ci) ci.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    const v = ci.value; ci.value = ''; callSay(v);
  });
  $('#btn-how').addEventListener('click', () => $('#modal-how').classList.add('open'));
  $('#btn-library').addEventListener('click', openLibrary);
  $('#btn-admin').addEventListener('click', openAdmin);
  $('#admin-refresh').addEventListener('click', openAdmin);
  $('#admin-close').addEventListener('click', () => show(state.profile ? 'dossier' : 'welcome'));
  $('#btn-reset').addEventListener('click', () => {
    if (!confirm('清空当前录入（已保存的档案不受影响）？')) return;
    state.eeg = state.dna = state.profile = null;
    state.chat = [];
    state.lastRecalled = [];
    setSlot('eeg', null); setSlot('dna', null);
    clearFace();
    clearVoice();
    if (starMap) { starMap.destroy(); starMap = null; }
    if (chatAvatar) { chatAvatar.destroy(); chatAvatar = null; }
    if (mainAvatar) { mainAvatar.destroy(); mainAvatar = null; }
    $('#subject').value = '';
    show('welcome');
  });
  $('#btn-scan').addEventListener('click', () => {
    if (state.eeg && state.dna) runScan(state.eeg.file, state.dna.file);
  });
  $$('#modal-how [data-close]').forEach(b => b.addEventListener('click', () => $('#modal-how').classList.remove('open')));
  $('#modal-how').addEventListener('click', e => { if (e.target.id === 'modal-how') $('#modal-how').classList.remove('open'); });
  $$('#modal-compare-list [data-close]').forEach(b => b.addEventListener('click', () => $('#modal-compare-list').classList.remove('open')));
  $('#modal-compare-list').addEventListener('click', e => { if (e.target.id === 'modal-compare-list') $('#modal-compare-list').classList.remove('open'); });

  document.querySelectorAll('[data-clear]').forEach(b => b.addEventListener('click', () => setSlot(b.dataset.clear, null)));

  $('#btn-camera').addEventListener('click', openCamera);
  $('#btn-scene').addEventListener('click', function () { if (state.profile) Scene.open(state.profile); });
  $('#btn-sprite').addEventListener('click', function () { $('#file-sprite').click(); });
  $('#file-sprite').addEventListener('change', function () {
    const f = $('#file-sprite').files[0];
    if (f) pickSprite(f);
    $('#file-sprite').value = '';
  });
  $('#btn-face-upload').addEventListener('click', () => $('#file-face').click());
  $('#file-face').addEventListener('change', () => {
    const f = $('#file-face').files[0];
    if (f) pickFaceFile(f);
    $('#file-face').value = '';
  });
  $('#btn-face-clear').addEventListener('click', clearFace);
  $('#btn-record').addEventListener('click', recordVoice);
  $('#btn-voice-clear').addEventListener('click', clearVoice);
  $('#btn-mic').addEventListener('click', toggleMic);
  $('#btn-voice-settings').addEventListener('click', openVoiceSettings);
  document.querySelectorAll('#modal-voice [data-close]').forEach(function (b) { b.addEventListener('click', function () { $('#modal-voice').classList.remove('open'); }); });
  $('#modal-voice').addEventListener('click', function (e) { if (e.target.id === 'modal-voice') $('#modal-voice').classList.remove('open'); });
  $('#tts-test').addEventListener('click', function () {
    if (!window.Voice) return;
    Voice.stop();
    Voice.speak('你好。我今天……还行。你呢。', {
      gender: $('#voice-gender').value,
      emotion: { valence: 0.55, arousal: 0.45 },
      rate: 1, pitch: 1,
    });
  });
  $('#tts-save').addEventListener('click', function () {
    const name = $('#tts-voice-list').value;
    const url = $('#tts-url').value.trim();
    if (name) localStorage.setItem('echomind_voice_name', name); else localStorage.removeItem('echomind_voice_name');
    if (url) localStorage.setItem('echomind_tts_url', url); else localStorage.removeItem('echomind_tts_url');
    $('#tts-engine').textContent = url ? '当前：本地语音服务' : '当前：浏览器语音';
    toast('声音设置已保存。');
  });
  $('#btn-stop-speak').addEventListener('click', stopSpeaking);
  $('#autonomy').addEventListener('change', async () => {
    if (!state.profile) return;
    try {
      const res = await apiPost('/api/autonomy', { id: state.profile.id, level: $('#autonomy').value });
      toast('自主性：' + (res.autonomy && res.autonomy.label ? res.autonomy.label : $('#autonomy').value));
    } catch (e) { toast(e.message, true); }
  });
  $('#voice-gender').addEventListener('change', () => {
    localStorage.setItem('echomind_voice_gender', $('#voice-gender').value);
  });
  $('#auto-speak').addEventListener('change', () => {
    localStorage.setItem('echomind_autospeak', $('#auto-speak').checked ? '1' : '0');
    if (!$('#auto-speak').checked) stopSpeaking();
  });

  $('#btn-talk').addEventListener('click', openChat);
  $('#btn-save').addEventListener('click', saveMind);
  $('#btn-md').addEventListener('click', exportMd);
  $('#btn-card').addEventListener('click', async function () {
    if (!state.profile) return;
    try {
      const r = await fetch('/api/card', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: state.profile.id }) });
      if (!r.ok) throw new Error('生成失败');
      download(await r.blob(), (state.profile.persona.code || state.profile.persona.name) + '-数字生命卡.html');
      toast('生命卡已生成。');
    } catch (e) { toast(e.message, true); }
  });
  $('#btn-archive').addEventListener('click', async function () {
    if (!state.profile) return;
    try {
      const r = await fetch('/api/archive', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: state.profile.id }) });
      if (!r.ok) throw new Error('导出失败');
      const blob = await r.blob();
      download(blob, state.profile.persona.name + '-记忆档案.html');
      toast('记忆档案已生成。');
    } catch (e) { toast(e.message, true); }
  });
  $('#btn-json').addEventListener('click', exportJson);
  $('#btn-back-dossier').addEventListener('click', async () => {
    stopSpeaking();
    if (state.profile && state.profile.id) {
      try { const j = await apiGet('/api/minds/' + encodeURIComponent(state.profile.id)); renderDossier(j.profile); } catch (e) { }
    }
    show('dossier');
  });
  $('#btn-playaudio').addEventListener('click', () => {
    if (Audio.playing) { Audio.stop(); toast('音景已停止。'); return; }
    if (!currentAudioCfg) return toast('还没有可播放的音景。', true);
    Audio.play(currentAudioCfg);
    toast('正在播放心灵音景 · 约 28 秒');
  });

  $('#chat-form').addEventListener('submit', e => { e.preventDefault(); sendChat(); });
  const ta = $('#chat-input');
  ta.addEventListener('input', () => {
    ta.style.height = 'auto';
    ta.style.height = Math.min(130, ta.scrollHeight) + 'px';
  });
  ta.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
  });

  $('#btn-lib-close').addEventListener('click', () => show(state.profile ? 'dossier' : 'welcome'));
  $('#btn-compare-mode').addEventListener('click', () => {
    state.compareSel = [];
    $('#compare-tray').hidden = false;
    $('#btn-do-compare').disabled = true;
    $('#compare-selected').textContent = '已选 0 / 2';
    renderLibrary();
    toast('请在卡片上点选两份档案。');
  });
  $('#btn-do-compare').addEventListener('click', doCompare);
  $('#btn-clear-compare').addEventListener('click', () => {
    state.compareSel = [];
    renderLibrary();
    $('#btn-do-compare').disabled = true;
    $('#compare-selected').textContent = '已选 0 / 2';
  });
  $('#btn-cmp-back').addEventListener('click', openLibrary);
  $('#btn-cancel-scan').addEventListener('click', () => {
    ScanStage.stop();
    show('intake');
  });
}

function renderVoices() {
  const box = $('#voice-chips');
  box.innerHTML = '';
  (state.status.voices || []).forEach(v => {
    const b = document.createElement('button');
    b.className = 'chip' + (v.key === state.voice ? ' on' : '');
    b.textContent = v.label;
    b.title = v.desc;
    b.addEventListener('click', () => {
      state.voice = v.key;
      $$('#voice-chips .chip').forEach(c => c.classList.toggle('on', c === b));
    });
    box.appendChild(b);
  });
}

function renderSamples() {
  const eegBox = $('#eeg-samples'), dnaBox = $('#dna-samples');
  eegBox.innerHTML = ''; dnaBox.innerHTML = '';
  (state.status.samples || []).forEach(s => {
    const b = document.createElement('button');
    b.className = 'chip';
    b.textContent = s.label.replace(/ · .*/, '');
    b.title = s.label;
    b.addEventListener('click', async () => {
      await loadSample(s.key, s.kind);
      b.classList.add('on');
      setTimeout(() => b.classList.remove('on'), 2000);
    });
    (s.kind === 'eeg' ? eegBox : dnaBox).appendChild(b);
  });
}

function parseQuery() {
  const q = new URLSearchParams(location.search);
  return { mind: q.get('mind'), chat: q.get('chat') };
}

async function handleDeepLink() {
  const q = parseQuery();
  const id = q.mind || q.chat;
  if (id) {
    try {
      const j = await apiGet('/api/minds/' + encodeURIComponent(id));
      renderDossier(j.profile);
      show('dossier');
      if (q.chat) setTimeout(openChat, 400);
      return true;
    } catch (err) {
      toast('链接里的档案不存在：' + err.message, true);
    }
  }
  return false;
}

async function init() {
  wireUI();
  wireDropzone('eeg');
  wireDropzone('dna');
  ScanStage.init();
  setInterval(pollProactive, 45000);
  document.body.dataset.theme = localStorage.getItem('echomind_theme') || 'light';
  $('#btn-theme').textContent = document.body.dataset.theme === 'light' ? '暗色' : '白色';
  $('#btn-theme').addEventListener('click', function () {
    const next = document.body.dataset.theme === 'light' ? 'dark' : 'light';
    document.body.dataset.theme = next;
    localStorage.setItem('echomind_theme', next);
    $('#btn-theme').textContent = next === 'light' ? '暗色' : '白色';
    window.dispatchEvent(new Event('resize'));
  });
  const savedGender = localStorage.getItem('echomind_voice_gender');
  if (savedGender) $('#voice-gender').value = savedGender;
  const savedAuto = localStorage.getItem('echomind_autospeak');
  if (savedAuto === '0') $('#auto-speak').checked = false;
  if (!window.matchMedia('(min-width: 900px)').matches) {
    $('.hero-sub').textContent = '数字生命读取你的脑电节律与基因位点，把它们投影成一个可对话、可保存的数字生命。';
  }
  try {
    state.status = await apiGet('/api/status');
    renderSamples();
    renderVoices();
  } catch (err) {
    toast('无法连接本地服务：' + err.message, true);
  }
  await handleDeepLink();
  window.addEventListener('resize', () => {
    if (state.profile && state.view === 'dossier') {
      drawRadar($('#radar-canvas'), state.profile.traits, state.profile.persona.color);
      const sp = state.profile.eeg.spectrum;
      drawSpectrum($('#spectrum-canvas'), sp.freqs, sp.power_db, state.profile.eeg.bands, state.profile.eeg.peak_hz);
    }
  });
  // 键盘：Esc 关闭弹窗
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      $$('.modal.open').forEach(m => m.classList.remove('open'));
    }
  });
}

init();


/* 通话里的语音输入：浏览器支持就转文字，不支持就说明白 */
function startCallMic() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const sub = $('#call-sub');
    if (!SR) {
        if (sub) sub.textContent = '这个浏览器没有语音识别，先打字吧。';
        return;
    }
    const rec = new SR();
    rec.lang = 'zh-CN';
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    if (sub) sub.textContent = '在听……';
    if (callPersona) callPersona.pulse(0.6);
    rec.onresult = function (e) {
        const text = (e.results[0][0].transcript || '').trim();
        if (text) callSay(text);
    };
    rec.onerror = function () { if (sub) sub.textContent = '没听清，再说一次？'; };
    rec.onend = function () { };
    try { rec.start(); } catch (e) { }
}
