/* ============================================================
   记忆星图：按"脑区"排布的记忆网络
   ------------------------------------------------------------
   - 结构性记忆：脑波频带、基因位点、面孔视角（真实测量，不衰减）
   - 情景记忆：对话里被记住的片段（按艾宾浩斯曲线衰减）
   - 连边：共享关键词或同脑区；点击节点可"回忆一次"（真实强化）
   ============================================================ */
'use strict';

const StarMap = (() => {
  const REGIONS = {
    perception: { label: '感知', zh: '枕叶 · 视觉', x: 0.42, y: -0.08, color: '#38e8ff' },
    language: { label: '语言', zh: '额叶 · 表达', x: -0.46, y: -0.18, color: '#9b6bff' },
    emotion: { label: '情绪', zh: '边缘系统', x: -0.04, y: 0.16, color: '#ff5fa2' },
    relation: { label: '关系', zh: '颞叶 · 他人', x: 0.34, y: 0.34, color: '#ffb057' },
    body: { label: '身体', zh: '顶叶 · 内感受', x: -0.18, y: -0.46, color: '#7ee787' },
    core: { label: '记忆核', zh: '海马体', x: 0.0, y: 0.42, color: '#e8f6ff' },
  };
  const KIND_COLOR = {
    birth: '#e8f6ff',
    emotion: '#ff5fa2',
    feeling: '#ff8bbd',
    identity: '#9b6bff',
    fact: '#b79bff',
    preference: '#ffb057',
    habit: '#ffc98a',
    event: '#38e8ff',
    insight: '#e8f6ff',
    structure_eeg: '#38e8ff',
    structure_dna: '#7ee787',
    structure_face: '#ffb057',
    structure_voice: '#7ee787',
  };

  function hash(str) {
    let h = 2166136261;
    for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  function rnd(seed) {
    let s = seed >>> 0;
    return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
  }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

  function bigrams(text) {
    const s = String(text || '').replace(/[^\u4e00-\u9fffA-Za-z0-9]/g, '');
    const out = new Set();
    for (let i = 0; i < s.length - 1; i++) out.add(s.slice(i, i + 2));
    return out;
  }

  function retentionAt(mem, days) {
    const now = Date.now();
    const last = mem.last ? Date.parse(mem.last) : (mem.created ? Date.parse(mem.created) : now);
    const dt = Math.max(0, (now - last) / 86400000) + days;
    const s = clamp(1.0 * (1 + 0.75 * (mem.rehearsals || 0)) * (1 + 0.9 * Math.abs(mem.valence || 0)), 0.15, 60);
    return Math.exp(-dt / s);
  }

  /* ---------- 从档案构造节点 ---------- */
  function buildNodes(profile) {
    const nodes = [];
    const add = (n) => { n.seed = hash(n.id); nodes.push(n); };

    // 结构性：脑波频带
    const bands = (profile.eeg && profile.eeg.bands) || {};
    Object.keys(bands).forEach((k, i) => {
      const b = bands[k];
      add({
        id: 'band_' + k, kind: 'structure_eeg', region: 'perception', source: 'structure',
        title: b.label || k, text: '12 秒记录中占 ' + Math.round((b.rel || 0) * 100) + '%（' + (b.db || 0) + ' dB）',
        retention: 1, weight: 0.55 + (b.rel || 0) * 0.8, rehearsals: 0, valence: 0,
      });
    });
    // 结构性：基因位点（取前 6 个有洞察的）
    const markers = ((profile.dna && profile.dna.markers) || []).slice(0, 6);
    markers.forEach((m) => {
      add({
        id: 'snp_' + m.rsid, kind: 'structure_dna', region: 'body', source: 'structure',
        title: m.gene + ' ' + (m.genotype || ''),
        text: m.effect + '（' + m.rsid + '）',
        retention: 1, weight: 0.45, rehearsals: 0, valence: 0,
      });
    });
    // 结构性：面孔视角
    const views = (profile.avatar && profile.avatar.views) || [];
    views.forEach((v, i) => {
      add({
        id: 'face_' + (v.key || i), kind: 'structure_face', region: 'perception', source: 'structure',
        title: '面孔 · ' + ({ front: '正面', left: '左转', right: '右转', up: '抬头', smile: '微笑' }[v.key] || v.key),
        text: '录入时的第 ' + (i + 1) + ' 个视角',
        retention: 1, weight: 0.4, rehearsals: 0, valence: 0,
      });
    });
    // 结构性：声音样本
    if (profile.voice && profile.voice.metrics && profile.voice.metrics.f0) {
      add({
        id: 'voice_sample', kind: 'structure_voice', region: 'language', source: 'structure',
        title: '声音 · ' + profile.voice.metrics.f0 + ' Hz',
        text: '你留下的一小段声音，基频约 ' + profile.voice.metrics.f0 + ' Hz',
        retention: 1, weight: 0.5, rehearsals: 0, valence: 0,
      });
    }
    // 情景 + 出生记忆
    const mems = (profile.mind && profile.mind.memories) || [];
    mems.forEach((m) => {
      const kind = m.kind || 'fact';
      const region = kind === 'birth' ? 'core'
        : (kind === 'emotion' || kind === 'feeling') ? 'emotion'
          : (kind === 'identity' || kind === 'fact') ? 'language'
            : (kind === 'preference' || kind === 'habit') ? 'body'
              : kind === 'event' ? 'relation' : kind === 'insight' ? 'core' : 'core';
      add({
        id: m.id, kind: m.source === 'birth' ? 'birth' : kind, region, source: 'episodic',
        title: m.text.length > 22 ? m.text.slice(0, 22) + '…' : m.text,
        text: m.text, retention: m.retention != null ? m.retention : retentionAt(m, 0),
        weight: 0.5 + Math.min(1, (m.rehearsals || 0) * 0.25),
        rehearsals: m.rehearsals || 0, valence: m.valence || 0,
        created: m.created, last: m.last, faded: !!m.faded, raw: m,
      });
    });
    return nodes;
  }

  /* ---------- 布局：脑形轮廓内按脑区散布 ---------- */
  function brainPoint(angle, radius) {
    // 侧视脑轮廓的极坐标近似：前额略窄、后枕略宽、底部收
    const rx = 0.94, ry = 0.64;
    const bump = 1 + 0.06 * Math.cos(angle * 3) + 0.04 * Math.sin(angle * 5);
    return { x: Math.cos(angle) * rx * radius * bump, y: Math.sin(angle) * ry * radius * bump };
  }

  function layout(nodes) {
    const groups = {};
    nodes.forEach(n => { (groups[n.region] = groups[n.region] || []).push(n); });
    Object.keys(groups).forEach(key => {
      const region = REGIONS[key] || REGIONS.core;
      const list = groups[key];
      list.forEach((n, i) => {
        const r = rnd(n.seed);
        const angle = (i / Math.max(1, list.length)) * Math.PI * 2 + r() * 0.8;
        const ring = 0.16 + 0.26 * Math.sqrt((i + 0.5) / Math.max(1, list.length)) + r() * 0.05;
        n.x = region.x + Math.cos(angle) * ring * 0.95;
        n.y = region.y + Math.sin(angle) * ring * 0.75;
      });
    });
    // 简单排斥，避免重叠
    for (let iter = 0; iter < 26; iter++) {
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          let dx = b.x - a.x, dy = b.y - a.y;
          let d2 = dx * dx + dy * dy;
          const min = 0.085;
          if (d2 < min * min && d2 > 1e-6) {
            const d = Math.sqrt(d2);
            const push = (min - d) / 2;
            dx /= d; dy /= d;
            a.x -= dx * push; a.y -= dy * push;
            b.x += dx * push; b.y += dy * push;
          }
        }
      }
      // 收回轮廓内
      nodes.forEach(n => {
        const r = Math.hypot(n.x / 0.94, n.y / 0.64);
        if (r > 0.86) { n.x *= 0.86 / r; n.y *= 0.86 / r; }
      });
    }
    return nodes;
  }

  function buildEdges(nodes) {
    const edges = [];
    const link = new globalThis.Map();
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      const ga = bigrams(a.text);
      const scored = [];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        const gb = bigrams(b.text);
        let inter = 0;
        ga.forEach(g => { if (gb.has(g)) inter++; });
        const sim = inter / Math.max(1, Math.sqrt(ga.size * gb.size));
        const same = a.region === b.region ? 0.12 : 0;
        const score = sim + same;
        if (score > 0.2) scored.push({ j, score });
      }
      scored.sort((x, y) => y.score - x.score);
      scored.slice(0, 2).forEach(s => {
        const key = i + '-' + s.j;
        if (link.has(key)) return;
        link.set(key, true);
        edges.push({ a: i, b: s.j, strength: Math.min(1, s.score), phase: Math.random() });
      });
    }
    return edges;
  }

  class Map {
    constructor(canvas, profile, opts = {}) {
      this.cv = canvas;
      this.ctx = canvas.getContext('2d');
      this.profile = profile;
      this.days = 0;
      this.nodes = layout(buildNodes(profile));
      this.edges = buildEdges(this.nodes);
      this.hover = null;
      this.selected = null;
      this.t = 0;
      this.last = performance.now();
      this.onSelect = opts.onSelect || null;
      this.highlight = new Set((opts.highlight || []).slice());
      this.paused = false;
      this._bind();
      this.resize();
      this.loop();
    }

    destroy() {
      cancelAnimationFrame(this._raf);
      window.removeEventListener('resize', this._onResize);
      this.cv.removeEventListener('pointermove', this._onMove);
      this.cv.removeEventListener('pointerleave', this._onLeave);
      this.cv.removeEventListener('pointerdown', this._onDown);
    }

    _bind() {
      this._onResize = () => this.resize();
      window.addEventListener('resize', this._onResize);
      this._onMove = (e) => {
        const p = this.toMap(e);
        let best = null, bd = 0.045;
        for (const n of this.nodes) {
          const d = Math.hypot(n.x - p.x, n.y - p.y);
          if (d < bd) { bd = d; best = n; }
        }
        this.hover = best;
        this.cv.style.cursor = best ? 'pointer' : 'default';
      };
      this._onLeave = () => { this.hover = null; };
      this._onDown = (e) => {
        const p = this.toMap(e);
        let best = null, bd = 0.05;
        for (const n of this.nodes) {
          const d = Math.hypot(n.x - p.x, n.y - p.y);
          if (d < bd) { bd = d; best = n; }
        }
        this.selected = best;
        if (this.onSelect) this.onSelect(best);
      };
      this.cv.addEventListener('pointermove', this._onMove);
      this.cv.addEventListener('pointerleave', this._onLeave);
      this.cv.addEventListener('pointerdown', this._onDown);
      this.cv.style.touchAction = 'manipulation';
    }

    resize() {
      const r = this.cv.getBoundingClientRect();
      const dpr = Math.min(2, devicePixelRatio || 1);
      this.cv.width = Math.max(1, Math.floor(r.width * dpr));
      this.cv.height = Math.max(1, Math.floor(r.height * dpr));
      this.dpr = dpr;
    }

    toMap(e) {
      const r = this.cv.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width;
      const y = (e.clientY - r.top) / r.height;
      return { x: (x - 0.5) / 0.405, y: (y - 0.52) / 0.368 };
    }

    toScreen(n, W, H) {
      return {
        x: W * 0.5 + n.x * W * 0.405,
        y: H * 0.52 + n.y * H * 0.368,
      };
    }



    setDays(d) { this.days = d; }

    setHighlight(ids) { this.highlight = new Set(ids || []); }

    nodeRetention(n) {
      if (n.source !== 'episodic' || !n.raw) return 1;
      return retentionAt(n.raw, this.days);
    }

    loop() {
      this._raf = requestAnimationFrame(() => this.loop());
      const now = performance.now();
      const dt = Math.min(0.05, (now - this.last) / 1000);
      this.last = now;
      if (!this.paused) this.t += dt;
      const c = this.ctx, W = this.cv.width, H = this.cv.height;
      if (!W || !H) return;
      const dpr = this.dpr || 1;
      c.clearRect(0, 0, W, H);

      // 背景
      const bg = c.createRadialGradient(W * 0.5, H * 0.48, 0, W * 0.5, H * 0.48, Math.max(W, H) * 0.62);
      bg.addColorStop(0, 'rgba(14,30,42,0.55)');
      bg.addColorStop(0.6, 'rgba(8,16,24,0.25)');
      bg.addColorStop(1, 'rgba(4,8,12,0)');
      c.fillStyle = bg;
      c.fillRect(0, 0, W, H);

      // 脑轮廓
      c.save();
      c.translate(W * 0.5, H * 0.52);
      const sx = W * 0.405, sy = H * 0.368;
      // 小脑
      c.beginPath();
      c.ellipse(sx * 0.62, sy * 0.66, sx * 0.2, sy * 0.15, 0.15, 0, Math.PI * 2);
      c.strokeStyle = 'rgba(120,190,210,0.08)';
      c.lineWidth = 1 * dpr;
      c.stroke();
      // 大脑轮廓
      c.beginPath();
      for (let i = 0; i <= 120; i++) {
        const a = i / 120 * Math.PI * 2;
        const p = brainPoint(a, 1);
        i ? c.lineTo(p.x * sx, p.y * sy) : c.moveTo(p.x * sx, p.y * sy);
      }
      c.closePath();
      c.strokeStyle = 'rgba(120,190,210,0.18)';
      c.lineWidth = 1.2 * dpr;
      c.stroke();
      // 中央沟
      c.beginPath();
      c.moveTo(-sx * 0.16, -sy * 0.92);
      c.quadraticCurveTo(sx * 0.08, -sy * 0.2, -sx * 0.2, sy * 0.28);
      c.strokeStyle = 'rgba(120,190,210,0.08)';
      c.setLineDash([3, 5]);
      c.stroke();
      c.setLineDash([]);

      // 脑区标签
      c.font = 9 * dpr + 'px "JetBrains Mono", monospace';
      c.textAlign = 'center';
      Object.keys(REGIONS).forEach(k => {
        const r = REGIONS[k];
        c.fillStyle = 'rgba(140,180,195,0.35)';
        c.fillText(r.label, r.x * sx, r.y * sy + (k === 'core' ? 18 : -12) * dpr);
      });
      c.restore();

      // 连边
      const pos = this.nodes.map(n => this.toScreen(n, W, H));
      this.edges.forEach(e => {
        const a = this.nodes[e.a], b = this.nodes[e.b];
        const ra = this.nodeRetention(a), rb = this.nodeRetention(b);
        const live = Math.min(ra, rb);
        const on = this.highlight.has(a.id) || this.highlight.has(b.id);
        const alpha = 0.03 + live * (on ? 0.22 : 0.09) + (this.hover === a || this.hover === b ? 0.18 : 0);
        if (alpha < 0.015) return;
        const pa = pos[e.a], pb = pos[e.b];
        const mx = (pa.x + pb.x) / 2, my = (pa.y + pb.y) / 2 - 14 * dpr;
        c.beginPath();
        c.moveTo(pa.x, pa.y);
        c.quadraticCurveTo(mx, my, pb.x, pb.y);
        c.strokeStyle = 'rgba(120,210,230,' + alpha.toFixed(3) + ')';
        c.lineWidth = (0.6 + e.strength * 0.9) * dpr;
        c.stroke();
        // 脉冲
        if (this.t > 0.3) {
          const k = ((this.t * 0.18 + e.phase) % 1);
          const q = quad(pa, { x: mx, y: my }, pb, k);
          c.fillStyle = 'rgba(200,245,255,' + (0.18 + live * 0.5).toFixed(3) + ')';
          c.beginPath(); c.arc(q.x, q.y, 1.1 * dpr, 0, Math.PI * 2); c.fill();
        }
      });

      // 节点
      this.nodes.forEach((n, i) => {
        const p = pos[i];
        const r = this.nodeRetention(n);
        const faded = n.source === 'episodic' && r < 0.06;
        const base = n.source === 'structure' ? 2.2 : 2.8;
        const size = (base + Math.min(1, r) * 3.4 + (n.kind === 'birth' ? 1.6 : 0)) * dpr;
        const color = KIND_COLOR[n.kind] || '#9fb4c0';
        const alpha = faded ? 0.16 : 0.25 + Math.min(1, r) * 0.75;
        const drift = Math.sin(this.t * 0.6 + n.seed % 7) * 1.2 * dpr;
        const x = p.x + drift, y = p.y + Math.cos(this.t * 0.5 + n.seed % 5) * 1.2 * dpr;
        n._sx = x; n._sy = y;
        const hl = this.highlight.has(n.id);
        const hov = this.hover === n;

        // 光晕
        if (!faded) {
          const g = c.createRadialGradient(x, y, 0, x, y, size * 4);
          g.addColorStop(0, hexA(color, 0.35 * alpha));
          g.addColorStop(1, hexA(color, 0));
          c.fillStyle = g;
          c.beginPath(); c.arc(x, y, size * 4, 0, Math.PI * 2); c.fill();
        }
        // 出生节点的环
        if (n.kind === 'birth') {
          c.strokeStyle = hexA(color, 0.35 * alpha);
          c.lineWidth = 1 * dpr;
          c.beginPath(); c.arc(x, y, size * 2.6, 0, Math.PI * 2); c.stroke();
        }
        if (hl || hov) {
          c.strokeStyle = hexA(color, 0.85);
          c.lineWidth = 1.2 * dpr;
          c.beginPath(); c.arc(x, y, size * 2.2, 0, Math.PI * 2); c.stroke();
        }
        // 结构节点：菱形
        c.fillStyle = hexA(color, alpha);
        if (n.source === 'structure') {
          c.save();
          c.translate(x, y);
          c.rotate(Math.PI / 4);
          c.fillRect(-size * 0.75, -size * 0.75, size * 1.5, size * 1.5);
          c.restore();
        } else {
          c.beginPath(); c.arc(x, y, size, 0, Math.PI * 2); c.fill();
          c.fillStyle = hexA('#ffffff', alpha * 0.75);
          c.beginPath(); c.arc(x - size * 0.25, y - size * 0.25, size * 0.3, 0, Math.PI * 2); c.fill();
        }
      });

      // 悬停提示
      if (this.hover) {
        const n = this.hover;
        const r = this.nodeRetention(n);
        const x = n._sx, y = n._sy;
        const lines = [n.title, (n.source === 'structure' ? '结构性记忆' : '情景记忆 · 留存 ' + Math.round(r * 100) + '%')];
        c.font = 10 * dpr + 'px "PingFang SC", sans-serif';
        const w = Math.min(W * 0.5, Math.max(...lines.map(l => c.measureText(l).width)) + 20 * dpr);
        const bx = clamp(x - w / 2, 6 * dpr, W - w - 6 * dpr);
        const by = clamp(y - 46 * dpr, 6 * dpr, H - 46 * dpr);
        c.fillStyle = 'rgba(6,12,18,0.9)';
        c.strokeStyle = 'rgba(120,210,230,0.3)';
        c.lineWidth = 1 * dpr;
        roundRect(c, bx, by, w, 38 * dpr, 7 * dpr);
        c.fill(); c.stroke();
        c.fillStyle = 'rgba(230,245,250,0.95)';
        c.textAlign = 'left';
        c.fillText(lines[0], bx + 10 * dpr, by + 15 * dpr);
        c.fillStyle = 'rgba(150,190,205,0.8)';
        c.font = 9 * dpr + 'px "JetBrains Mono", monospace';
        c.fillText(lines[1], bx + 10 * dpr, by + 29 * dpr);
      }
    }
  }

  function roundRect(c, x, y, w, h, r) {
    c.beginPath();
    c.moveTo(x + r, y);
    c.arcTo(x + w, y, x + w, y + h, r);
    c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r);
    c.arcTo(x, y, x + w, y, r);
    c.closePath();
  }
  function quad(a, b, c2, t) {
    const u = 1 - t;
    return { x: u * u * a.x + 2 * u * t * b.x + t * t * c2.x, y: u * u * a.y + 2 * u * t * b.y + t * t * c2.y };
  }
  function hexA(hex, a) {
    const h = hex.replace('#', '');
    const n = parseInt(h.length === 3 ? h.split('').map(x => x + x).join('') : h, 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a.toFixed(3) + ')';
  }

  return { Map, REGIONS, KIND_COLOR, buildNodes, retentionAt };
})();

window.StarMap = StarMap;
