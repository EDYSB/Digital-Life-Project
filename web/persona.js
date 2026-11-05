/* 数字生命 · DeepSeek 拟人形象（蓝鲸少女）
   纯 canvas 绘制：蓝发、青色眼睛、鲸鱼发夹。会呼吸、眨眼、说话时轻微点头。
   接口与 Avatar 兼容：setColor / setViews / setVector / speak / stopSpeaking / pulse / destroy。 */

class PersonaAvatar {
  constructor(canvas, opts = {}) {
    this.cv = canvas;
    this.ctx = canvas.getContext('2d');
    this.color = opts.color || '#4fe3ff';
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.t = 0;
    this.pulseV = 0;
    this.speaking = false;
    this.blink = 0;
    this.nextBlink = 2.5 + Math.random() * 3;
    this.particles = Array.from({ length: 26 }, () => ({
      x: Math.random(), y: Math.random(), r: 0.6 + Math.random() * 1.4,
      s: 0.01 + Math.random() * 0.04, p: Math.random() * Math.PI * 2,
    }));
    this.alive = true;
    this.resize();
    this._loop = this._loop.bind(this);
    this.raf = requestAnimationFrame(this._loop);
  }

  resize() {
    const rect = this.cv.getBoundingClientRect();
    const w = Math.max(1, Math.round(rect.width || 320));
    const h = Math.max(1, Math.round(rect.height || 420));
    if (this.cv.width !== w * this.dpr || this.cv.height !== h * this.dpr) {
      this.cv.width = w * this.dpr;
      this.cv.height = h * this.dpr;
    }
    this.w = w; this.h = h;
  }

  setColor(c) { this.color = c || '#4fe3ff'; }
  setViews() { }
  setVector() { }
  pulse(v = 1) { this.pulseV = Math.min(1, this.pulseV + v); }
  speak() { this.speaking = true; this.pulse(0.4); }
  stopSpeaking() { this.speaking = false; }

  destroy() { this.alive = false; cancelAnimationFrame(this.raf); }

  _loop() {
    if (!this.alive) return;
    this.t += 0.016;
    this.pulseV *= 0.94;
    this.nextBlink -= 0.016;
    if (this.nextBlink <= 0 && this.blink <= 0) { this.blink = 1; this.nextBlink = 3 + Math.random() * 4; }
    if (this.blink > 0) this.blink = Math.max(0, this.blink - 0.016 * 7);
    this.draw();
    this.raf = requestAnimationFrame(this._loop);
  }

  draw() {
    const c = this.ctx, w = this.w, h = this.h;
    c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    c.clearRect(0, 0, w, h);

    /* 背景：深海 */
    const bg = c.createLinearGradient(0, 0, 0, h);
    bg.addColorStop(0, '#071527');
    bg.addColorStop(0.55, '#0a1e33');
    bg.addColorStop(1, '#050d18');
    c.fillStyle = bg;
    c.fillRect(0, 0, w, h);

    /* 房间 + 夜景窗 */
    const wx0 = w * 0.13, wx1 = w * 0.87, wy0 = h * 0.08, wy1 = h * 0.60;
    const winG = c.createLinearGradient(0, wy0, 0, wy1);
    winG.addColorStop(0, '#0b1d31');
    winG.addColorStop(1, '#194566');
    c.fillStyle = winG;
    c.fillRect(wx0, wy0, wx1 - wx0, wy1 - wy0);

    let seed = 7;
    const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    for (let i = 0; i < 24; i++) {
      const bw = w * (0.02 + rnd() * 0.055);
      const bx = wx0 + rnd() * (wx1 - wx0 - bw);
      const bh = (wy1 - wy0) * (0.22 + rnd() * 0.62);
      c.fillStyle = 'rgba(7,16,27,0.96)';
      c.fillRect(bx, wy1 - bh, bw, bh);
      c.fillStyle = 'rgba(130,205,255,0.30)';
      for (let k = 0; k < 7; k++) {
        if (rnd() > 0.5) c.fillRect(bx + 2, wy1 - bh + 5 + k * 7, 2, 2);
      }
    }
    // 远处光晕
    const glow = c.createRadialGradient(w * 0.30, wy1, 0, w * 0.30, wy1, w * 0.5);
    glow.addColorStop(0, 'rgba(90,190,255,0.18)');
    glow.addColorStop(1, 'rgba(90,190,255,0)');
    c.fillStyle = glow;
    c.fillRect(wx0, wy0, wx1 - wx0, wy1 - wy0);

    // 窗框
    c.strokeStyle = 'rgba(8,16,26,0.92)';
    c.lineWidth = Math.max(4, w * 0.012);
    c.strokeRect(wx0, wy0, wx1 - wx0, wy1 - wy0);
    c.beginPath();
    c.moveTo((wx0 + wx1) / 2, wy0);
    c.lineTo((wx0 + wx1) / 2, wy1);
    c.stroke();

    // 地板反光
    const fl = c.createLinearGradient(0, wy1, 0, h);
    fl.addColorStop(0, 'rgba(40,95,140,0.32)');
    fl.addColorStop(1, 'rgba(3,7,12,0)');
    c.fillStyle = fl;
    c.fillRect(0, wy1, w, h - wy1);

    /* 泡泡 */
    c.save();
    c.globalAlpha = 0.5;
    for (const p of this.particles) {
      p.y -= p.s * 0.0025;
      if (p.y < -0.05) { p.y = 1.05; p.x = Math.random(); }
      c.fillStyle = `rgba(150,225,255,${0.10 + 0.18 * (0.5 + 0.5 * Math.sin(this.t * 1.4 + p.p))})`;
      c.beginPath(); c.arc(p.x * w, p.y * h, p.r, 0, 7); c.fill();
    }
    c.restore();

    const breathe = 1 + Math.sin(this.t * 1.2) * 0.008 + this.pulseV * 0.012;
    const cx = w * 0.5;
    const headY = h * 0.40 + (this.speaking ? Math.sin(this.t * 6) * 1.5 : 0);
    const headR = Math.min(w * 0.30, h * 0.26);   // 大头，Q 版比例

    c.save();
    c.translate(cx, h * 0.55);
    c.scale(breathe, breathe);
    c.translate(-cx, -h * 0.55);

    /* 肩膀：蓝色卫衣 */
    const bodyG = c.createLinearGradient(0, h * 0.68, 0, h);
    bodyG.addColorStop(0, '#1b6fd6');
    bodyG.addColorStop(1, '#0d3f86');
    c.fillStyle = bodyG;
    c.beginPath();
    c.moveTo(cx - w * 0.46, h + 8);
    c.bezierCurveTo(cx - w * 0.34, h * 0.70, cx - w * 0.14, h * 0.66, cx, h * 0.66);
    c.bezierCurveTo(cx + w * 0.14, h * 0.66, cx + w * 0.34, h * 0.70, cx + w * 0.46, h + 8);
    c.closePath();
    c.fill();
    // 领口
    c.fillStyle = 'rgba(255,255,255,0.12)';
    c.beginPath();
    c.ellipse(cx, h * 0.675, headR * 0.62, headR * 0.18, 0, 0, 7);
    c.fill();

    /* 后发 */
    const hairG = c.createLinearGradient(cx - headR, headY - headR, cx + headR, headY + headR);
    hairG.addColorStop(0, '#2f7fe0');
    hairG.addColorStop(0.5, '#4aa8f0');
    hairG.addColorStop(1, '#2b6cd0');
    c.fillStyle = hairG;
    c.beginPath();
    c.ellipse(cx, headY + headR * 0.18, headR * 1.30, headR * 1.22, 0, 0, 7);
    c.fill();

    /* 脸 */
    const faceG = c.createLinearGradient(cx, headY - headR, cx, headY + headR);
    faceG.addColorStop(0, '#ffe7d6');
    faceG.addColorStop(1, '#f6c8ac');
    c.fillStyle = faceG;
    c.beginPath();
    c.ellipse(cx, headY + headR * 0.06, headR * 0.92, headR * 0.95, 0, 0, 7);
    c.fill();

    /* 刘海 */
    c.fillStyle = hairG;
    c.beginPath();
    c.moveTo(cx - headR * 0.96, headY + headR * 0.02);
    c.bezierCurveTo(cx - headR * 0.98, headY - headR * 1.22, cx + headR * 0.98, headY - headR * 1.22, cx + headR * 0.96, headY + headR * 0.02);
    c.bezierCurveTo(cx + headR * 0.80, headY - headR * 0.30, cx + headR * 0.55, headY - headR * 0.46, cx + headR * 0.26, headY - headR * 0.44);
    c.bezierCurveTo(cx + headR * 0.10, headY - headR * 0.62, cx - headR * 0.10, headY - headR * 0.62, cx - headR * 0.26, headY - headR * 0.44);
    c.bezierCurveTo(cx - headR * 0.55, headY - headR * 0.46, cx - headR * 0.80, headY - headR * 0.30, cx - headR * 0.96, headY + headR * 0.02);
    c.closePath();
    c.fill();

    /* 侧发 */
    c.beginPath();
    c.moveTo(cx - headR * 0.92, headY - headR * 0.05);
    c.bezierCurveTo(cx - headR * 1.20, headY + headR * 0.55, cx - headR * 1.02, headY + headR * 1.05, cx - headR * 0.74, headY + headR * 1.10);
    c.bezierCurveTo(cx - headR * 0.88, headY + headR * 0.60, cx - headR * 0.80, headY + headR * 0.20, cx - headR * 0.72, headY - headR * 0.02);
    c.closePath();
    c.fill();
    c.beginPath();
    c.moveTo(cx + headR * 0.92, headY - headR * 0.05);
    c.bezierCurveTo(cx + headR * 1.20, headY + headR * 0.55, cx + headR * 1.02, headY + headR * 1.05, cx + headR * 0.74, headY + headR * 1.10);
    c.bezierCurveTo(cx + headR * 0.88, headY + headR * 0.60, cx + headR * 0.80, headY + headR * 0.20, cx + headR * 0.72, headY - headR * 0.02);
    c.closePath();
    c.fill();

    /* 鲸鱼发夹 */
    c.save();
    c.translate(cx + headR * 0.74, headY - headR * 0.72);
    c.rotate(-0.35);
    c.fillStyle = '#8fe3ff';
    c.beginPath();
    c.ellipse(0, 0, headR * 0.20, headR * 0.12, 0, 0, 7);
    c.fill();
    c.beginPath();
    c.moveTo(headR * 0.16, -headR * 0.02);
    c.lineTo(headR * 0.30, -headR * 0.14);
    c.lineTo(headR * 0.30, headR * 0.10);
    c.closePath();
    c.fill();
    c.fillStyle = '#0a1e33';
    c.beginPath(); c.arc(-headR * 0.07, 0, headR * 0.022, 0, 7); c.fill();
    c.restore();

    /* 眼睛 */
    const eyeY = headY + headR * 0.10;
    const eyeDX = headR * 0.40;
    const open = 1 - this.blink;
    [-1, 1].forEach(side => {
      const ex = cx + side * eyeDX;
      c.save();
      c.translate(ex, eyeY);
      if (open > 0.08) {
        c.save();
        c.scale(1, open);
        // 眼白
        c.fillStyle = '#ffffff';
        c.beginPath(); c.ellipse(0, 0, headR * 0.21, headR * 0.25, 0, 0, 7); c.fill();
        // 虹膜
        const ir = c.createLinearGradient(0, -headR * 0.2, 0, headR * 0.2);
        ir.addColorStop(0, '#1f7fe0');
        ir.addColorStop(0.6, '#4fd0ff');
        ir.addColorStop(1, '#a8f0ff');
        c.fillStyle = ir;
        c.beginPath(); c.ellipse(0, headR * 0.02, headR * 0.15, headR * 0.20, 0, 0, 7); c.fill();
        // 瞳孔
        c.fillStyle = '#0a1830';
        c.beginPath(); c.ellipse(0, headR * 0.03, headR * 0.065, headR * 0.11, 0, 0, 7); c.fill();
        // 高光
        c.fillStyle = 'rgba(255,255,255,0.95)';
        c.beginPath(); c.arc(-headR * 0.055, -headR * 0.07, headR * 0.045, 0, 7); c.fill();
        c.beginPath(); c.arc(headR * 0.05, headR * 0.10, headR * 0.022, 0, 7); c.fill();
        c.restore();
        // 上睫毛
        c.strokeStyle = '#12365c'; c.lineWidth = headR * 0.045; c.lineCap = 'round';
        c.beginPath();
        c.moveTo(-headR * 0.20, -headR * 0.12);
        c.quadraticCurveTo(0, -headR * 0.26, headR * 0.20, -headR * 0.12);
        c.stroke();
      } else {
        c.strokeStyle = '#12365c'; c.lineWidth = headR * 0.04; c.lineCap = 'round';
        c.beginPath();
        c.moveTo(-headR * 0.18, 0);
        c.quadraticCurveTo(0, headR * 0.10, headR * 0.18, 0);
        c.stroke();
      }
      c.restore();
    });

    /* 腮红 */
    c.fillStyle = 'rgba(255,150,160,0.22)';
    [-1, 1].forEach(side => {
      c.beginPath();
      c.ellipse(cx + side * headR * 0.62, eyeY + headR * 0.34, headR * 0.16, headR * 0.08, 0, 0, 7);
      c.fill();
    });

    /* 嘴 */
    c.strokeStyle = '#c96b6b'; c.lineWidth = headR * 0.03; c.lineCap = 'round';
    c.beginPath();
    c.moveTo(cx - headR * 0.07, eyeY + headR * 0.46);
    c.quadraticCurveTo(cx, eyeY + headR * 0.53, cx + headR * 0.07, eyeY + headR * 0.46);
    c.stroke();

    /* 眼神光 */
    c.save();
    c.globalCompositeOperation = 'lighter';
    const eg = c.createRadialGradient(cx, eyeY, 0, cx, eyeY, headR * 1.2);
    eg.addColorStop(0, `rgba(79,227,255,${0.10 + this.pulseV * 0.10})`);
    eg.addColorStop(1, 'rgba(79,227,255,0)');
    c.fillStyle = eg;
    c.fillRect(0, 0, w, h);
    c.restore();

    c.restore();
  }
}

window.PersonaAvatar = PersonaAvatar;
