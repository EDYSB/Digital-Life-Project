/* ============================================================
   面孔：人像分析、2.5D 全息头像、中文语音与口型
   ------------------------------------------------------------
   诚实边界：
   - 照片只做裁剪、调色、全息化与口型叠加，不做 3D 重建，不生成新的人脸；
   - 口型由文本节奏驱动，不是音素级同步；
   - 不做身份、性格、健康推断；照片只留在本机档案里。
   ============================================================ */
'use strict';

/* ---------------- 人像分析（纯前端，无模型） ---------------- */
const Face = (() => {
  function isSkin(r, g, b) {
    const y = 0.299 * r + 0.587 * g + 0.114 * b;
    const cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b;
    const cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b;
    return y > 50 && y < 250 && cb > 76 && cb < 129 && cr > 132 && cr < 176
      && r > g && r > b * 0.85;
  }

  function quantize(data, w, h, box) {
    const buckets = new Map();
    const step = 3;
    for (let y = box.y; y < box.y + box.h; y += step) {
      for (let x = box.x; x < box.x + box.w; x += step) {
        const i = (y * w + x) * 4;
        const r = data[i], g = data[i + 1], b = data[i + 2];
        if (r < 16 && g < 16 && b < 16) continue;
        const key = ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4);
        const cur = buckets.get(key) || { n: 0, r: 0, g: 0, b: 0 };
        cur.n++; cur.r += r; cur.g += g; cur.b += b;
        buckets.set(key, cur);
      }
    }
    return [...buckets.values()].sort((a, b) => b.n - a.n).slice(0, 7).map(v => ({
      r: Math.round(v.r / v.n), g: Math.round(v.g / v.n), b: Math.round(v.b / v.n), n: v.n,
    }));
  }

  function hex(c) {
    return '#' + [c.r, c.g, c.b].map(v => clamp(v, 0, 255).toString(16).padStart(2, '0')).join('');
  }

  function findFaceBox(data, w, h) {
    let minX = w, minY = h, maxX = 0, maxY = 0, count = 0;
    for (let y = 0; y < h; y += 2) {
      for (let x = 0; x < w; x += 2) {
        const i = (y * w + x) * 4;
        if (isSkin(data[i], data[i + 1], data[i + 2])) {
          count++;
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
      }
    }
    const ratio = count / ((w / 2) * (h / 2));
    if (ratio < 0.015 || maxX <= minX || maxY <= minY) return null;
    return { x: minX, y: minY, w: maxX - minX, h: maxY - minY, ratio };
  }

  function symmetry(data, w, box) {
    const cx = box.x + box.w / 2;
    let diff = 0, n = 0;
    for (let y = box.y; y < box.y + box.h; y += 3) {
      for (let dx = 4; dx < box.w / 2 - 4; dx += 3) {
        const l = (y * w + Math.round(cx - dx)) * 4;
        const r = (y * w + Math.round(cx + dx)) * 4;
        if (l < 0 || r + 2 >= data.length) continue;
        const dl = Math.abs(data[l] - data[r]) + Math.abs(data[l + 1] - data[r + 1]) + Math.abs(data[l + 2] - data[r + 2]);
        diff += dl; n++;
      }
    }
    return n ? clamp(1 - (diff / n) / 220, 0, 1) : 0.5;
  }

  async function analyze(file, opts = {}) {
    if (!file) throw new Error('没有选择照片。');
    if (!/^image\//.test(file.type || '') && !/\.(png|jpe?g|webp)$/i.test(file.name || '')) {
      throw new Error('请选择 PNG / JPG / WebP 图片。');
    }
    if (file.size > 12 * 1024 * 1024) throw new Error('照片超过 12 MB，请先压缩。');
    const bmp = await createImageBitmap(file);
    const maxSide = 900;
    const scale = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
    const w = Math.round(bmp.width * scale), h = Math.round(bmp.height * scale);
    const cv = document.createElement('canvas');
    cv.width = w; cv.height = h;
    const ctx = cv.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(bmp, 0, 0, w, h);

    const img = ctx.getImageData(0, 0, w, h);
    let box = findFaceBox(img.data, w, h);
    if (!box) {
      // 兜底：取中间偏上的 3:4 区域
      const bw = Math.min(w, h * 0.62), bh = bw * 1.32;
      box = { x: (w - bw) / 2, y: Math.max(0, h * 0.08), w: bw, h: bh, ratio: 0 };
    }
    // 扩成 3:4，并留出头顶与肩部
    const targetH = Math.min(h, box.h * 1.42);
    const targetW = Math.min(w, targetH * 0.78);
    const cx = box.x + box.w / 2;
    const cy = box.y + box.h * 0.46;
    let sx = clamp(cx - targetW / 2, 0, Math.max(0, w - targetW));
    let sy = clamp(cy - targetH * 0.42, 0, Math.max(0, h - targetH));

    const cols = quantize(img.data, w, h, box);
    const skin = cols[0] || { r: 205, g: 160, b: 140 };
    const palette = {
      skin: hex(skin),
      all: cols.map(hex),
      accent: hex(cols[1] || skin),
    };

    let lum = 0, lum2 = 0, sat = 0, warm = 0, n = 0;
    for (let y = box.y; y < box.y + box.h; y += 4) {
      for (let x = box.x; x < box.x + box.w; x += 4) {
        const i = (y * w + x) * 4;
        const r = img.data[i], g = img.data[i + 1], b = img.data[i + 2];
        const yv = 0.299 * r + 0.587 * g + 0.114 * b;
        lum += yv; lum2 += yv * yv;
        const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
        sat += mx ? (mx - mn) / mx : 0;
        warm += (r - b) / 255;
        n++;
      }
    }
    lum /= n || 1;
    const contrast = Math.sqrt(Math.max(0, lum2 / (n || 1) - lum * lum)) / 128;
    sat /= n || 1; warm /= n || 1;

    const portrait = document.createElement('canvas');
    portrait.width = 384; portrait.height = 480;
    const pctx = portrait.getContext('2d');
    pctx.imageSmoothingQuality = 'high';
    pctx.drawImage(cv, sx, sy, targetW, targetH, 0, 0, 384, 480);

    // 归一化面部几何（用于口型/眨眼定位）
    const norm = {
      face: {
        x: (box.x - sx) / targetW, y: (box.y - sy) / targetH,
        w: box.w / targetW, h: box.h / targetH,
      },
      mouth: { x: (box.x + box.w / 2 - sx) / targetW, y: (box.y + box.h * 0.72 - sy) / targetH, w: box.w * 0.34 / targetW },
      eyes: { y: (box.y + box.h * 0.40 - sy) / targetH, dx: box.w * 0.19 / targetW },
      skin,
    };
    const meta = {
      box: { x: Math.round(box.x), y: Math.round(box.y), w: Math.round(box.w), h: Math.round(box.h) },
      ratio: Math.round((box.ratio || 0) * 1000) / 1000,
      palette,
      metrics: {
        brightness: Math.round((lum / 255) * 100) / 100,
        contrast: Math.round(contrast * 100) / 100,
        saturation: Math.round(sat * 100) / 100,
        warmth: Math.round((warm + 0.5) * 100) / 100,
        symmetry: Math.round(symmetry(img.data, w, box) * 100) / 100,
      },
      geometry: norm,
      source: { w: bmp.width, h: bmp.height, name: (opts.name || file.name || '').slice(0, 80) },
      kind: 'photo',
    };
    return { photo: portrait.toDataURL('image/jpeg', 0.84), meta };
  }

  return { analyze };
})();

/* ---------------- 语音（Web Speech API） ---------------- */
const Voice = (() => {
  const synth = window.speechSynthesis;
  let voices = [];
  let cache = [];
  let timer = null;
  let audioEl = null;
  let cancelled = false;

  function load() {
    if (!synth) return [];
    voices = synth.getVoices().filter(v => /^zh/i.test(v.lang) || /chinese|中文|普通话/i.test(v.name));
    voices.sort((a, b) => score(b) - score(a));
    return voices;
  }

  function score(v) {
    let s = 0;
    if (/natural|neural|online|premium|enhanced/i.test(v.name)) s += 5;
    if (/xiaoxiao|xiaoyi|xiaohan|yunxi|yunjian|晓晓|云希|晓伊/i.test(v.name)) s += 4;
    if (/female|女/i.test(v.name)) s += 1;
    if (/^zh-CN/i.test(v.lang)) s += 2;
    return s;
  }

  function list() { return load().map(v => ({ name: v.name, lang: v.lang })); }

  function pick(gender) {
    load();
    const saved = localStorage.getItem('echomind_voice_name');
    if (saved) {
      const hit = voices.find(v => v.name === saved);
      if (hit) return hit;
    }
    if (!voices.length) return null;
    const female = /xiaoxiao|xiaoyi|xiaohan|huihui|yaoyao|tingting|meijia|晓晓|晓伊|女/i;
    const male = /yunxi|yunjian|kangkang|liang|云希|云健|男/i;
    const want = gender === 'male' ? male : female;
    return voices.find(v => want.test(v.name)) || voices[0];
  }

  function supported() { return !!synth && load().length > 0; }

  if (synth) {
    load();
    if ('onvoiceschanged' in synth) synth.onvoiceschanged = load;
    if (synth.addEventListener) synth.addEventListener('voiceschanged', load);
  }

  function estimate(text) {
    const t = String(text || '');
    const zh = (t.match(/[\u4e00-\u9fff]/g) || []).length;
    const other = t.replace(/[\u4e00-\u9fff]/g, '').replace(/\s/g, '').length;
    const pauses = (t.match(/[，。；！？、,.!?;]/g) || []).length;
    return Math.max(0.8, (zh / 4.4 + other / 9 + pauses * 0.13) * 1000);
  }

  function split(text) {
    const parts = String(text || '').split(/(?<=[，。；！？、\n])/).filter(s => s.trim());
    return parts.map(p => {
      const last = p.trim().slice(-1);
      const pause = /[。！？\n]/.test(last) ? 260 : /[，、；]/.test(last) ? 110 : 40;
      return { text: p.trim(), pause, est: estimate(p) };
    });
  }

  function prosody(opts) {
    const emo = opts.emotion || {};
    const v = typeof emo.valence === 'number' ? emo.valence : 0.55;
    const a = typeof emo.arousal === 'number' ? emo.arousal : 0.5;
    const female = (opts.gender || 'female') === 'female';
    const baseRate = (opts.rate || 1) * (0.93 + 0.14 * a);
    const rate = clamp(baseRate - (v < 0.35 ? 0.05 : 0), 0.82, 1.12);
    const pitch = clamp((opts.pitch || 1) * (0.98 + 0.09 * (v - 0.5) * 2) + (female ? 0.03 : -0.02), 0.8, 1.22);
    return { rate, pitch };
  }

  function stop() {
    cancelled = true;
    if (timer) clearInterval(timer);
    timer = null;
    if (audioEl) { try { audioEl.pause(); } catch (e) { } audioEl = null; }
    if (synth) { try { synth.cancel(); } catch (e) { } }
  }

  function playLocal(text, opts, pros) {
    const url = localStorage.getItem('echomind_tts_url');
    if (!url) return false;
    const body = JSON.stringify({
      text,
      speaker: opts.gender === 'male' ? 'male' : 'female',
      emotion: opts.emotion || {},
      speed: Math.round((pros.rate - 1) * 100) / 100,
      pitch: Math.round((pros.pitch - 1) * 100) / 100,
    });
    fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body })
      .then(r => { if (!r.ok) throw new Error('TTS ' + r.status); return r.blob(); })
      .then(blob => {
        if (cancelled) return;
        const audio = new Audio(URL.createObjectURL(blob));
        audioEl = audio;
        const start = performance.now();
        const dur = isFinite(audio.duration) && audio.duration > 0 ? audio.duration : estimate(text) / 1000;
        if (opts.onStart) opts.onStart(dur * 1000);
        timer = setInterval(() => {
          const p = Math.min(1, (performance.now() - start) / (dur * 1000));
          if (opts.onProgress) opts.onProgress(p);
        }, 40);
        audio.onended = () => {
          if (timer) clearInterval(timer);
          if (opts.onEnd) opts.onEnd();
        };
        audio.play().catch(() => { if (opts.onEnd) opts.onEnd(); });
      })
      .catch(() => {
        // 本地服务不可用：退回浏览器语音
        browserSpeak(text, opts, pros);
      });
    return true;
  }

  function browserSpeak(text, opts, pros) {
    const voice = pick(opts.gender);
    if (!synth || !text || !voice) {
      // 静音口型
      const dur = estimate(text);
      const start = performance.now();
      cancelled = false;
      if (opts.onStart) opts.onStart(dur);
      timer = setInterval(() => {
        const p = Math.min(1, (performance.now() - start) / dur);
        if (opts.onProgress) opts.onProgress(p);
        if (p >= 1) { clearInterval(timer); if (opts.onEnd) opts.onEnd(); }
      }, 40);
      return { duration: dur, silent: true, engine: 'silent' };
    }
    const clauses = split(text);
    const total = clauses.reduce((s, c) => s + c.est + c.pause, 0);
    const start = performance.now();
    let idx = 0;
    cancelled = false;
    if (opts.onStart) opts.onStart(total);
    timer = setInterval(() => {
      const p = Math.min(1, (performance.now() - start) / total);
      if (opts.onProgress) opts.onProgress(p);
    }, 40);

    const next = () => {
      if (cancelled) return;
      if (idx >= clauses.length) {
        if (timer) clearInterval(timer);
        if (opts.onEnd) opts.onEnd();
        return;
      }
      const c = clauses[idx++];
      const u = new SpeechSynthesisUtterance(c.text);
      u.voice = voice;
      u.lang = voice.lang || 'zh-CN';
      u.rate = pros.rate;
      u.pitch = pros.pitch;
      u.volume = 1;
      u.onend = () => { if (!cancelled) setTimeout(next, c.pause); };
      u.onerror = () => { if (!cancelled) setTimeout(next, 80); };
      synth.speak(u);
    };
    next();
    return { duration: total, silent: false, engine: 'browser', voice: voice.name };
  }

  function speak(text, opts = {}) {
    stop();
    cancelled = false;
    const pros = prosody(opts);
    if (localStorage.getItem('echomind_tts_url')) {
      if (playLocal(text, opts, pros)) return { duration: estimate(text), engine: 'local' };
    }
    return browserSpeak(text, opts, pros);
  }

  return { supported, list, pick, speak, stop, estimate, estimateDuration: estimate };
})();

/* ---------------- 口型时间轴 ---------------- */
function buildVisemes(text, durationMs) {
  const chars = [...String(text || '')];
  const frames = [];
  const n = Math.max(8, Math.floor(durationMs / 33));
  // 每个字分配一个口型；标点处闭合
  const per = chars.length ? n / chars.length : n;
  let seed = 0;
  for (const ch of chars) seed = (seed * 31 + ch.codePointAt(0)) >>> 0;
  const rnd = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
  for (let i = 0; i < n; i++) {
    const ci = Math.min(chars.length - 1, Math.floor(i / per));
    const ch = chars[ci] || '';
    let open = 0.12 + rnd() * 0.6, wide = 0.35 + rnd() * 0.4;
    if (/[，。；！？、,.!?;\s]/.test(ch)) { open = 0.02; wide = 0.3; }
    else if (/[aāáǎà]/.test(ch)) { open = 0.85; wide = 0.8; }
    else if (/[oōóǒòuūúǔù]/.test(ch)) { open = 0.7; wide = 0.28; }
    else if (/[iīíǐìeēéěè]/.test(ch)) { open = 0.4; wide = 0.75; }
    // 音节感：每 3 帧有一个开合起伏
    const wave = 0.5 + 0.5 * Math.sin((i / Math.max(1, per)) * Math.PI * 2);
    open *= 0.55 + 0.45 * wave;
    frames.push({ t: i / n, open, wide });
  }
  // 平滑
  for (let pass = 0; pass < 2; pass++) {
    for (let i = 1; i < frames.length - 1; i++) {
      frames[i].open = (frames[i - 1].open + frames[i].open * 2 + frames[i + 1].open) / 4;
      frames[i].wide = (frames[i - 1].wide + frames[i].wide * 2 + frames[i + 1].wide) / 4;
    }
  }
  frames[0].open = 0.02;
  if (frames.length > 1) frames[frames.length - 1].open = 0.02;
  return frames;
}

/* ---------------- 头像渲染 ---------------- */
class Avatar {
  constructor(canvas, opts = {}) {
    this.cv = canvas;
    this.ctx = canvas.getContext('2d');
    this.color = opts.color || '#38e8ff';
    this.mode = 'vector';
    this.photo = null;
    this.photoImg = null;
    this.meta = null;
    this.views = [];          // [{key, angle, turn, img, meta}]
    this.turnViews = [];      // 仅左/正/右，用于转头
    this.viewPos = 1;
    this.viewTarget = 1;
    this.autoTurn = true;
    this.dragging = false;
    this.t = 0;
    this.speaking = false;
    this.visemes = [];
    this.progress = 0;
    this.blinkAt = 2.5 + Math.random() * 3;
    this.blinkPhase = 0;
    this.last = performance.now();
    this.glow = 0;
    this._raf = null;
    this.resize();
    this._onResize = () => this.resize();
    window.addEventListener('resize', this._onResize);
    this._bindDrag();
    this.loop();
  }

  destroy() {
    cancelAnimationFrame(this._raf);
    window.removeEventListener('resize', this._onResize);
  }

  resize() {
    const r = this.cv.getBoundingClientRect();
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    this.cv.width = Math.max(1, Math.floor((r.width || 320) * dpr));
    this.cv.height = Math.max(1, Math.floor((r.height || 400) * dpr));
  }

  setColor(c) { this.color = c || '#38e8ff'; }

  setPhoto(photo, meta) {
    if (!photo) { this.mode = 'vector'; this.photo = null; this.photoImg = null; return; }
    this.setViews([{ key: 'front', angle: 0, turn: 0, photo, meta }]);
  }

  setViews(views) {
    this.views = (views || []).filter(v => v && v.photo);
    if (!this.views.length) { this.mode = 'vector'; return; }
    this.mode = 'photo';
    this.photo = this.views[0].photo;
    this.meta = this.views[0].meta;
    this.views.forEach(v => {
      v.img = new Image();
      v.img.src = v.photo;
    });
    // 转头只使用左/正/右三个视角
    const horiz = this.views.filter(v => Math.abs(v.turn || 0) <= 1);
    const left = horiz.filter(v => v.turn < 0);
    const front = horiz.filter(v => !v.turn);
    const right = horiz.filter(v => v.turn > 0);
    this.turnViews = [...left.slice(-1), ...front.slice(0, 1), ...right.slice(0, 1)];
    if (this.turnViews.length < 2) this.turnViews = this.views.slice(0, 2);
    this.viewPos = this.turnViews.length > 1 ? (this.turnViews.some(v => v.turn < 0) ? 1 : 0) : 0;
    this.viewPos = Math.min(this.viewPos, this.turnViews.length - 1);
    this.viewTarget = this.viewPos;
  }

  setVector(meta) {
    this.mode = 'vector';
    this.meta = meta || null;
  }

  _bindDrag() {
    const cv = this.cv;
    let startX = 0, startPos = 0;
    cv.style.touchAction = 'none';
    cv.addEventListener('pointerdown', e => {
      if (this.mode !== 'photo' || this.turnViews.length < 2) return;
      this.dragging = true;
      this.autoTurn = false;
      startX = e.clientX;
      startPos = this.viewPos;
      cv.setPointerCapture(e.pointerId);
    });
    cv.addEventListener('pointermove', e => {
      if (!this.dragging) return;
      const span = Math.max(90, cv.clientWidth * 0.55);
      const delta = (e.clientX - startX) / span;
      this.viewTarget = clamp(startPos + delta * (this.turnViews.length - 1), 0, this.turnViews.length - 1);
    });
    const end = () => {
      if (!this.dragging) return;
      this.dragging = false;
      setTimeout(() => { if (!this.dragging) this.autoTurn = true; }, 3200);
    };
    cv.addEventListener('pointerup', end);
    cv.addEventListener('pointercancel', end);
    cv.addEventListener('pointerleave', () => { if (this.dragging) end(); });
  }

  speak(text) {
    const dur = Voice.estimateDuration(text);
    this.visemes = buildVisemes(text, dur);
    this.speaking = true;
    this.progress = 0;
    this.speakStart = performance.now();
    this.speakDur = dur;
  }

  stopSpeaking() { this.speaking = false; this.progress = 0; }

  pulse(v = 1) { this.glow = Math.min(1, this.glow + v * 0.4); }

  emotion(e) { this.emo = e; }

  loop() {
    this._raf = requestAnimationFrame(() => this.loop());
    const now = performance.now();
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    this.t += dt;
    this.glow *= 0.96;
    if (this.mode === 'photo' && this.turnViews.length > 1) {
      if (this.autoTurn && !this.dragging) {
        const span = this.turnViews.length - 1;
        this.viewTarget = clamp((0.5 + 0.42 * Math.sin(this.t * 0.23)) * span, 0, span);
      }
      this.viewPos += (this.viewTarget - this.viewPos) * Math.min(1, dt * 3.2);
    }

    // 眨眼节律
    this.blinkPhase -= dt;
    if (this.blinkPhase <= -0.02 && this.t > this.blinkAt) {
      this.blinkPhase = 0.13;
      this.blinkAt = this.t + 2.8 + Math.random() * 3.6;
    }
    if (this.blinkPhase > 0) this.blinkPhase = Math.max(0, this.blinkPhase - dt);
    const blink = this.blinkPhase > 0 ? Math.sin((1 - this.blinkPhase / 0.13) * Math.PI) : 0;

    // 说话进度
    let mouth = { open: 0, wide: 0.4 };
    if (this.speaking) {
      const p = Math.min(1, (now - this.speakStart) / this.speakDur);
      this.progress = p;
      const idx = Math.min(this.visemes.length - 1, Math.floor(p * this.visemes.length));
      mouth = this.visemes[idx] || mouth;
      if (p >= 1) this.speaking = false;
    }

    this.draw(dt, blink, mouth);
  }

  geom() {
    const g = this.meta && this.meta.geometry;
    return g && g.face ? g : null;
  }

  draw(dt, blink, mouth) {
    const c = this.ctx, W = this.cv.width, H = this.cv.height;
    if (!W || !H) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    c.clearRect(0, 0, W, H);
    const cx = W / 2, cy = H * 0.46;
    const breathe = Math.sin(this.t * 1.15) * 0.5 + 0.5;
    const sway = Math.sin(this.t * 0.62) * 0.008 + Math.sin(this.t * 0.27) * 0.004;
    const rgb = hexRgb(this.color);

    // 背光
    const halo = c.createRadialGradient(cx, cy, 0, cx, cy, Math.min(W, H) * 0.62);
    halo.addColorStop(0, `rgba(${rgb},${0.16 + this.glow * 0.12})`);
    halo.addColorStop(0.55, `rgba(${rgb},0.05)`);
    halo.addColorStop(1, 'rgba(0,0,0,0)');
    c.fillStyle = halo;
    c.fillRect(0, 0, W, H);

    if (this.mode === 'photo' && this.photoImg) {
      this.drawPhoto(c, W, H, dpr, sway, breathe, mouth, blink);
    } else {
      this.drawVector(c, W, H, dpr, sway, breathe, mouth, blink);
    }

    // 扫描线
    c.save();
    c.globalAlpha = 0.12;
    c.fillStyle = '#04121a';
    for (let y = 0; y < H; y += 4 * dpr) c.fillRect(0, y, W, 1 * dpr);
    c.restore();

    // 横向扫描光带
    const scanY = ((this.t * 0.09) % 1) * H;
    const sg = c.createLinearGradient(0, scanY - 40 * dpr, 0, scanY + 40 * dpr);
    sg.addColorStop(0, 'rgba(56,232,255,0)');
    sg.addColorStop(0.5, `rgba(${rgb},0.10)`);
    sg.addColorStop(1, 'rgba(56,232,255,0)');
    c.fillStyle = sg;
    c.fillRect(0, scanY - 40 * dpr, W, 80 * dpr);
  }

  /* ---------- 照片模式：真实照片 + 局部形变 ----------
     不重着色、不换脸。只做：
     - 柔边羽化 + 轻微暗角，让照片融进背景
     - 呼吸、极轻的头部摆动
     - 下颌切片下移 + 口腔/牙齿，模拟说话
     - 眼带压缩 + 眼睑覆盖，模拟眨眼
  ------------------------------------------------ */
  _prepareView(view) {
    if (!view || !view.img || !view.img.complete || !view.img.naturalWidth) return null;
    if (view._buf) return view._buf;
    const img = view.img;
    const w = 384, h = 480;
    const cv = document.createElement('canvas');
    cv.width = w; cv.height = h;
    const c = cv.getContext('2d');
    // cover
    const s = Math.max(w / img.naturalWidth, h / img.naturalHeight);
    const dw = img.naturalWidth * s, dh = img.naturalHeight * s;
    c.drawImage(img, (w - dw) / 2, (h - dh) / 2, dw, dh);
    // 采样唇色/肤色
    try {
      const data = c.getImageData(0, 0, w, h);
      const geo = view.meta && view.meta.geometry;
      const sample = (nx, ny, rad) => {
        let r = 0, g = 0, b = 0, n = 0;
        const cx = Math.round(nx * w), cy = Math.round(ny * h);
        for (let y = cy - rad; y <= cy + rad; y += 2) {
          for (let x = cx - rad; x <= cx + rad; x += 2) {
            if (x < 0 || y < 0 || x >= w || y >= h) continue;
            const i = (y * w + x) * 4;
            r += data.data[i]; g += data.data[i + 1]; b += data.data[i + 2]; n++;
          }
        }
        return n ? [Math.round(r / n), Math.round(g / n), Math.round(b / n)] : [200, 150, 130];
      };
      if (geo && geo.mouth) {
        view._lip = sample(geo.mouth.x, geo.mouth.y, 3);
        const lip = view._lip;
        view._inner = [Math.max(8, lip[0] * 0.34), Math.max(6, lip[1] * 0.26), Math.max(6, lip[2] * 0.28)];
        view._teeth = [235, 228, 214];
        view._skin = sample(geo.mouth.x, Math.max(0.05, geo.mouth.y - 0.18), 4);
      }
    } catch (e) { /* 跨域图片无法采样时用默认色 */ }
    if (!view._lip) {
      view._lip = [196, 130, 120];
      view._inner = [72, 30, 30];
      view._teeth = [232, 224, 210];
      view._skin = [214, 168, 146];
    }
    // 柔边：径向羽化
    c.globalCompositeOperation = 'destination-in';
    const g = c.createRadialGradient(w / 2, h * 0.48, w * 0.18, w / 2, h * 0.48, w * 0.62);
    g.addColorStop(0, 'rgba(0,0,0,1)');
    g.addColorStop(0.72, 'rgba(0,0,0,1)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    c.fillStyle = g;
    c.fillRect(0, 0, w, h);
    c.globalCompositeOperation = 'source-over';
    view._buf = cv;
    return cv;
  }

  drawPhoto(c, W, H, dpr, sway, breathe, mouth, blink) {
    const views = this.turnViews.length ? this.turnViews : this.views;
    if (!views.length) return;
    const pos = clamp(this.viewPos, 0, views.length - 1);
    const i = Math.floor(pos), f = pos - i;
    const a = views[i], b = views[Math.min(views.length - 1, i + 1)];
    const rgb = hexRgb(this.color);
    const cx = W / 2, cy = H * 0.5;
    const bob = Math.sin(this.t * 1.15) * 1.8 * dpr;
    const rot = sway;

    const drawView = (view, alpha, offsetX) => {
      const buf = this._prepareView(view);
      if (!buf) return;
      const scale = Math.min(W / buf.width, H / buf.height) * 1.0;
      const dw = buf.width * scale, dh = buf.height * scale;
      const geo = view.meta && view.meta.geometry;
      const mouthY = (geo && geo.mouth ? geo.mouth.y : 0.72) * dh;
      const mouthX = (geo && geo.mouth ? geo.mouth.x : 0.5) * dw;
      const eyeY = (geo && geo.eyes ? geo.eyes.y : 0.4) * dh;
      const open = mouth.open || 0;

      c.save();
      c.globalAlpha = alpha;
      c.translate(cx + offsetX, cy + bob);
      c.rotate(rot);
      c.translate(-dw / 2, -dh / 2);

      // 切片绘制：嘴以下逐渐下移，眼睛附近压缩
      const slice = Math.max(2, Math.round(dh / 110));
      for (let y = 0; y < dh; y += slice) {
        let dy = 0;
        if (y > mouthY - slice) {
          const t = Math.min(1, (y - (mouthY - slice)) / Math.max(1, dh - mouthY));
          dy = open * dh * 0.045 * (t * t);
        }
        let sy = y, sh = slice + 1, destY = y + dy;
        // 眨眼：眼带压缩
        if (blink > 0.02 && y > eyeY - 16 * dpr && y < eyeY + 14 * dpr) {
          const k = 1 - 0.55 * blink;
          const cye = eyeY;
          sy = cye + (y - cye) * k;
          sh = (slice + 1) * k;
          destY = y;
        }
        const syH = Math.min(buf.height - sy, sh);
        c.drawImage(buf, 0, sy, buf.width, syH, 0, destY, dw, syH * (dh / buf.height));
      }

      // 口腔
      if (open > 0.02) {
        const ow = (geo && geo.mouth ? geo.mouth.w : 0.18) * dw * (0.8 + (mouth.wide || 0.4) * 0.5);
        const oh = Math.max(2, open * dh * 0.05);
        c.fillStyle = 'rgb(' + view._inner.join(',') + ')';
        c.beginPath();
        c.ellipse(mouthX, mouthY + oh * 0.15, ow * 0.55, oh * 0.62, 0, 0, Math.PI * 2);
        c.fill();
        // 牙
        c.fillStyle = 'rgba(' + view._teeth.join(',') + ',0.82)';
        c.beginPath();
        c.ellipse(mouthX, mouthY - oh * 0.18, ow * 0.42, Math.max(0.6, oh * 0.18), 0, 0, Math.PI * 2);
        c.fill();
      }
      // 唇线（闭口时也很淡）
      c.strokeStyle = 'rgba(' + view._lip.join(',') + ',0.5)';
      c.lineWidth = 0.8 * dpr;
      c.beginPath();
      c.moveTo(mouthX - (mouth.wide || 0.4) * dw * 0.13, mouthY);
      c.quadraticCurveTo(mouthX, mouthY + 1.4 * dpr, mouthX + (mouth.wide || 0.4) * dw * 0.13, mouthY);
      c.stroke();

      // 眼睑（眨眼时覆盖）
      if (blink > 0.02 && geo && geo.eyes) {
        const edx = (geo.eyes.dx || 0.18) * dw;
        const lidH = blink * 9 * dpr;
        c.fillStyle = 'rgba(' + view._skin.join(',') + ',0.92)';
        [-1, 1].forEach(function (dir) {
          c.beginPath();
          c.ellipse(dw / 2 + dir * edx, eyeY - 1 * dpr, dw * 0.068, lidH, 0, 0, Math.PI * 2);
          c.fill();
        });
      }
      c.restore();
    };

    drawView(a, 1 - f, -f * 9 * dpr);
    if (b !== a) drawView(b, f, (1 - f) * 9 * dpr);

    // 极轻的冷色轮廓光
    c.save();
    c.globalCompositeOperation = 'screen';
    const rim = c.createRadialGradient(cx, cy, W * 0.18, cx, cy, W * 0.52);
    rim.addColorStop(0, 'rgba(0,0,0,0)');
    rim.addColorStop(0.75, 'rgba(0,0,0,0)');
    rim.addColorStop(1, 'rgba(' + rgb + ',0.10)');
    c.fillStyle = rim;
    c.fillRect(0, 0, W, H);
    c.restore();

    // 视角指示
    if (views.length > 1) {
      for (let k = 0; k < views.length; k++) {
        c.fillStyle = k === Math.round(pos) ? 'rgba(' + rgb + ',0.85)' : 'rgba(' + rgb + ',0.22)';
        c.beginPath();
        c.arc(cx + (k - (views.length - 1) / 2) * 11 * dpr, H - 12 * dpr, 1.9 * dpr, 0, Math.PI * 2);
        c.fill();
      }
    }
  }

  /* ---------- 矢量模式：程序化数字人 ---------- */
  drawVector(c, W, H, dpr, sway, breathe, mouth, blink) {
    const rgb = hexRgb(this.color);
    const s = Math.min(W / 600, H / 720);
    const cx = W / 2 + Math.sin(this.t * 0.55) * 4 * dpr;
    const cy = H * 0.47 + Math.sin(this.t * 1.1) * 2.5 * dpr;
    const bob = Math.sin(this.t * 1.15) * 3 * dpr;
    c.save();
    c.translate(cx, cy + bob);
    c.rotate(sway);
    c.scale(s, s);

    const skinA = '#e8c3ab', skinB = '#b98570', skinC = '#8d5f52';
    const hair = '#241a23', hairHi = '#3b2a37';
    const blinkOpen = 1 - blink;

    // 肩
    const sh = c.createLinearGradient(0, 190, 0, 340);
    sh.addColorStop(0, '#1b2836');
    sh.addColorStop(1, '#0e1720');
    c.fillStyle = sh;
    c.beginPath();
    c.moveTo(-230, 340);
    c.quadraticCurveTo(-190, 210, -70, 196);
    c.lineTo(70, 196);
    c.quadraticCurveTo(190, 210, 230, 340);
    c.closePath();
    c.fill();
    c.strokeStyle = `rgba(${rgb},0.35)`;
    c.lineWidth = 1.2;
    c.stroke();

    // 颈
    const neck = c.createLinearGradient(-40, 0, 40, 0);
    neck.addColorStop(0, skinB);
    neck.addColorStop(0.45, skinA);
    neck.addColorStop(1, skinC);
    c.fillStyle = neck;
    c.beginPath();
    c.moveTo(-34, 96); c.lineTo(-30, 208); c.quadraticCurveTo(0, 224, 30, 208); c.lineTo(34, 96);
    c.closePath(); c.fill();

    // 后发
    c.fillStyle = hair;
    c.beginPath();
    c.ellipse(0, -18, 150, 172, 0, 0, Math.PI * 2);
    c.fill();

    // 脸
    const face = c.createLinearGradient(-90, -80, 90, 130);
    face.addColorStop(0, '#f0cfb8');
    face.addColorStop(0.45, skinA);
    face.addColorStop(0.82, skinB);
    face.addColorStop(1, skinC);
    c.fillStyle = face;
    c.beginPath();
    c.moveTo(-96, -84);
    c.bezierCurveTo(-104, 4, -92, 78, -46, 118);
    c.bezierCurveTo(-20, 142, 20, 142, 46, 118);
    c.bezierCurveTo(92, 78, 104, 4, 96, -84);
    c.bezierCurveTo(70, -128, -70, -128, -96, -84);
    c.closePath();
    c.fill();
    c.strokeStyle = 'rgba(255,225,205,0.18)';
    c.lineWidth = 1.2;
    c.stroke();

    // 颧骨与下颌阴影
    c.save();
    c.globalAlpha = 0.35;
    const sh2 = c.createRadialGradient(66, 44, 4, 66, 44, 80);
    sh2.addColorStop(0, 'rgba(120,68,58,0.55)');
    sh2.addColorStop(1, 'rgba(120,68,58,0)');
    c.fillStyle = sh2;
    c.beginPath(); c.ellipse(66, 44, 80, 86, 0, 0, Math.PI * 2); c.fill();
    c.restore();

    // 颊部柔光
    c.save();
    c.globalAlpha = 0.22;
    c.fillStyle = '#ff9d8a';
    c.beginPath(); c.ellipse(-58, 34, 32, 20, 0, 0, Math.PI * 2); c.fill();
    c.beginPath(); c.ellipse(58, 34, 32, 20, 0, 0, Math.PI * 2); c.fill();
    c.restore();

    // 眉
    c.strokeStyle = '#3a2622';
    c.lineWidth = 7;
    c.lineCap = 'round';
    c.beginPath();
    c.moveTo(-78, -46); c.quadraticCurveTo(-52, -62, -26, -48); c.stroke();
    c.beginPath();
    c.moveTo(26, -48); c.quadraticCurveTo(52, -62, 78, -46); c.stroke();

    // 眼
    const eyeY = -14, eyeDX = 44;
    for (const dir of [-1, 1]) {
      const ex = dir * eyeDX;
      // 眼白
      c.fillStyle = '#f4ece4';
      c.beginPath();
      c.ellipse(ex, eyeY, 26, 12 * blinkOpen + 1.2, 0, 0, Math.PI * 2);
      c.fill();
      if (blinkOpen > 0.25) {
        // 虹膜
        const iris = c.createRadialGradient(ex + 2, eyeY - 2, 1, ex, eyeY, 12);
        iris.addColorStop(0, '#8a6238');
        iris.addColorStop(0.7, '#5c3d24');
        iris.addColorStop(1, '#302014');
        c.fillStyle = iris;
        c.beginPath(); c.arc(ex, eyeY, 10.5, 0, Math.PI * 2); c.fill();
        c.fillStyle = '#120c0a';
        c.beginPath(); c.arc(ex, eyeY + 1, 4.4, 0, Math.PI * 2); c.fill();
        c.fillStyle = 'rgba(255,255,255,0.95)';
        c.beginPath(); c.arc(ex - 3.4, eyeY - 4, 2.4, 0, Math.PI * 2); c.fill();
        c.fillStyle = 'rgba(255,255,255,0.5)';
        c.beginPath(); c.arc(ex + 3, eyeY + 3, 1.2, 0, Math.PI * 2); c.fill();
      }
      // 上眼睑与睫毛
      c.strokeStyle = '#2a1a18';
      c.lineWidth = 4;
      c.beginPath();
      c.moveTo(ex - 27, eyeY - 2);
      c.quadraticCurveTo(ex, eyeY - 17 * blinkOpen - 2, ex + 27, eyeY - 2);
      c.stroke();
      if (blink > 0.55) {
        c.strokeStyle = '#c99a83';
        c.lineWidth = 2;
        c.beginPath();
        c.moveTo(ex - 24, eyeY - 1);
        c.quadraticCurveTo(ex, eyeY + 6, ex + 24, eyeY - 1);
        c.stroke();
      }
    }

    // 鼻
    c.save();
    c.globalAlpha = 0.5;
    c.strokeStyle = '#9d6a58';
    c.lineWidth = 3;
    c.beginPath();
    c.moveTo(4, -4);
    c.quadraticCurveTo(10, 34, 2, 44);
    c.stroke();
    c.globalAlpha = 0.35;
    c.fillStyle = '#7d4c40';
    c.beginPath(); c.ellipse(-9, 44, 4.5, 3, 0, 0, Math.PI * 2); c.fill();
    c.beginPath(); c.ellipse(11, 44, 4.5, 3, 0, 0, Math.PI * 2); c.fill();
    c.restore();
    c.save();
    c.globalAlpha = 0.5;
    c.fillStyle = 'rgba(255,235,220,0.6)';
    c.beginPath(); c.ellipse(2, 30, 4, 8, 0, 0, Math.PI * 2); c.fill();
    c.restore();

    // 嘴
    const my = 82 + mouth.open * 10;
    const mw = 30 + mouth.wide * 16;
    // 口腔
    if (mouth.open > 0.06) {
      c.fillStyle = '#3b1418';
      c.beginPath();
      c.ellipse(0, my + 2, mw * 0.62, 2 + mouth.open * 12, 0, 0, Math.PI * 2);
      c.fill();
      // 牙
      c.fillStyle = 'rgba(255,248,240,0.9)';
      c.beginPath();
      c.ellipse(0, my - 2, mw * 0.42, 1 + mouth.open * 3.4, 0, 0, Math.PI * 2);
      c.fill();
    }
    // 上唇
    const lip = c.createLinearGradient(0, my - 10, 0, my + 10);
    lip.addColorStop(0, '#b26663');
    lip.addColorStop(1, '#d98a84');
    c.fillStyle = lip;
    c.beginPath();
    c.moveTo(-mw, my);
    c.quadraticCurveTo(-mw * 0.5, my - 9 - mouth.open * 2, 0, my - 4);
    c.quadraticCurveTo(mw * 0.5, my - 9 - mouth.open * 2, mw, my);
    c.quadraticCurveTo(mw * 0.5, my + 3, 0, my + 3);
    c.quadraticCurveTo(-mw * 0.5, my + 3, -mw, my);
    c.closePath();
    c.fill();
    // 下唇
    c.fillStyle = '#cf7e78';
    c.beginPath();
    c.moveTo(-mw * 0.92, my + 3);
    c.quadraticCurveTo(0, my + 9 + mouth.open * 14, mw * 0.92, my + 3);
    c.quadraticCurveTo(0, my + 5, -mw * 0.92, my + 3);
    c.closePath();
    c.fill();
    // 唇高光
    c.fillStyle = 'rgba(255,225,215,0.35)';
    c.beginPath(); c.ellipse(-mw * 0.2, my + 6 + mouth.open * 6, mw * 0.32, 1.6 + mouth.open * 2.4, 0, 0, Math.PI * 2); c.fill();

    // 前发
    c.fillStyle = hair;
    c.beginPath();
    c.moveTo(-104, -92);
    c.quadraticCurveTo(-116, -190, 0, -196);
    c.quadraticCurveTo(116, -190, 104, -92);
    c.quadraticCurveTo(86, -140, 46, -132);
    c.quadraticCurveTo(-10, -122, -58, -134);
    c.quadraticCurveTo(-92, -140, -104, -92);
    c.closePath();
    c.fill();
    // 发丝高光
    c.strokeStyle = hairHi;
    c.lineWidth = 2;
    for (let i = -3; i <= 3; i++) {
      c.beginPath();
      c.moveTo(i * 26, -186);
      c.quadraticCurveTo(i * 30 + 8, -150, i * 34 + 14, -128);
      c.stroke();
    }

    // 侧发
    c.fillStyle = hair;
    c.beginPath();
    c.moveTo(-104, -84);
    c.quadraticCurveTo(-124, 60, -108, 148);
    c.quadraticCurveTo(-92, 130, -92, 60);
    c.quadraticCurveTo(-96, -20, -96, -80);
    c.closePath(); c.fill();
    c.beginPath();
    c.moveTo(104, -84);
    c.quadraticCurveTo(124, 60, 108, 148);
    c.quadraticCurveTo(92, 130, 92, 60);
    c.quadraticCurveTo(96, -20, 96, -80);
    c.closePath(); c.fill();

    // 轮廓光
    c.strokeStyle = `rgba(${rgb},0.75)`;
    c.lineWidth = 2.4;
    c.beginPath();
    c.moveTo(96, -84);
    c.bezierCurveTo(104, 4, 92, 78, 46, 118);
    c.stroke();
    c.strokeStyle = 'rgba(255,95,162,0.35)';
    c.beginPath();
    c.moveTo(-96, -84);
    c.bezierCurveTo(-104, 4, -92, 78, -46, 118);
    c.stroke();

    c.restore();

    // 粒子重构
    c.save();
    for (let i = 0; i < 26; i++) {
      const a = this.t * 0.12 + i * 2.4;
      const rr = Math.min(W, H) * (0.36 + (i % 5) * 0.03) + Math.sin(this.t + i) * 5;
      const x = cx + Math.cos(a) * rr * 0.72;
      const y = cy - H * 0.02 + Math.sin(a * 1.3) * rr * 0.5;
      c.fillStyle = `rgba(${rgb},${0.1 + (i % 4) * 0.09})`;
      c.beginPath(); c.arc(x, y, (1 + (i % 3)) * dpr, 0, Math.PI * 2); c.fill();
    }
    c.restore();
  }
}

window.Face = Face;
window.Voice = Voice;
window.Avatar = Avatar;
window.buildVisemes = buildVisemes;
