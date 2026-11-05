/* 数字生命 · DeepSeek 拟人形象
   纯 canvas 绘制：剪影肖像 + 发光眼睛 + 鲸鱼水印 + 呼吸/眨眼。
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
    this.particles = Array.from({ length: 42 }, () => ({
      x: Math.random(), y: Math.random(),
      r: 0.5 + Math.random() * 1.6,
      s: 0.02 + Math.random() * 0.06,
      p: Math.random() * Math.PI * 2,
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
  speak() { this.speaking = true; this.pulse(0.5); }
  stopSpeaking() { this.speaking = false; }

  destroy() {
    this.alive = false;
    cancelAnimationFrame(this.raf);
  }

  _loop(ts) {
    if (!this.alive) return;
    this.t += 0.016;
    this.pulseV *= 0.94;
    const dt = 0.016;

    // 眨眼调度
    this.nextBlink -= dt;
    if (this.nextBlink <= 0 && this.blink <= 0) { this.blink = 1; this.nextBlink = 3 + Math.random() * 4; }
    if (this.blink > 0) this.blink = Math.max(0, this.blink - dt * 7);

    this.draw();
    this.raf = requestAnimationFrame(this._loop);
  }

  draw() {
    const c = this.ctx, w = this.w, h = this.h;
    const cx = w * 0.5, cy = h * 0.5;
    const S = Math.min(w, h * 0.78);            // 绘制基准
    const breathe = 1 + Math.sin(this.t * 1.1) * 0.004 + this.pulseV * 0.01;
    const accent = this.color;

    c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    c.clearRect(0, 0, w, h);

    /* 背景 */
    const bg = c.createRadialGradient(cx, h * 0.40, 10, cx, h * 0.45, Math.max(w, h) * 0.95);
    bg.addColorStop(0, '#0a1725');
    bg.addColorStop(0.55, '#050b13');
    bg.addColorStop(1, '#020509');
    c.fillStyle = bg;
    c.fillRect(0, 0, w, h);

    /* 鲸鱼水印（DeepSeek 意象） */
    c.save();
    c.globalAlpha = 0.06;
    c.translate(cx, h * 0.44);
    c.scale(S / 300, S / 300);
    c.fillStyle = accent;
    c.beginPath();
    c.moveTo(-96, 6);
    c.bezierCurveTo(-96, -34, -34, -52, 14, -34);
    c.bezierCurveTo(40, -24, 56, -16, 74, -10);
    c.bezierCurveTo(70, -30, 74, -44, 88, -58);
    c.bezierCurveTo(86, -34, 96, -18, 108, -8);
    c.bezierCurveTo(92, 2, 78, 8, 72, 20);
    c.bezierCurveTo(52, 40, 6, 50, -34, 40);
    c.bezierCurveTo(-66, 32, -96, 26, -96, 6);
    c.fill();
    c.beginPath();
    c.arc(-58, -6, 4.2, 0, 7);
    c.fillStyle = '#020509';
    c.fill();
    c.restore();

    /* 光环 + 刻度 */
    c.save();
    c.globalAlpha = 0.5;
    c.strokeStyle = accent + '33';
    c.lineWidth = 1;
    c.beginPath();
    c.arc(cx, cy * 0.98, S * 0.46, 0, Math.PI * 2);
    c.stroke();
    c.globalAlpha = 0.35;
    for (let i = 0; i < 72; i++) {
      const a = (i / 72) * Math.PI * 2 + this.t * 0.05;
      const r1 = S * 0.46, r2 = r1 + (i % 6 === 0 ? 7 : 3);
      c.beginPath();
      c.moveTo(cx + Math.cos(a) * r1, cy * 0.98 + Math.sin(a) * r1);
      c.lineTo(cx + Math.cos(a) * r2, cy * 0.98 + Math.sin(a) * r2);
      c.stroke();
    }
    c.restore();

    /* 漂浮粒子 */
    c.save();
    c.globalCompositeOperation = 'lighter';
    for (const p of this.particles) {
      p.y -= p.s * 0.004;
      if (p.y < -0.05) { p.y = 1.05; p.x = Math.random(); }
      const px = p.x * w, py = p.y * h;
      const a = 0.10 + 0.22 * (0.5 + 0.5 * Math.sin(this.t * 1.6 + p.p));
      c.fillStyle = accent + Math.round(a * 255).toString(16).padStart(2, '0');
      c.beginPath(); c.arc(px, py, p.r, 0, 7); c.fill();
    }
    c.restore();

    /* 人物剪影 */
    const headY = h * 0.40;
    const headRX = S * 0.155, headRY = S * 0.185;
    const shoulderY = h * 0.78;

    c.save();
    c.translate(cx, h * 0.5);
    c.scale(breathe, breathe);
    c.translate(-cx, -h * 0.5);

    // 肩膀
    const bodyG = c.createLinearGradient(0, shoulderY - 30, 0, h);
    bodyG.addColorStop(0, '#0b1420');
    bodyG.addColorStop(1, '#050a11');
    c.fillStyle = bodyG;
    c.beginPath();
    c.moveTo(cx - w * 0.5, h + 10);
    c.bezierCurveTo(cx - w * 0.44, shoulderY - 26, cx - w * 0.15, shoulderY - 52, cx, shoulderY - 52);
    c.bezierCurveTo(cx + w * 0.15, shoulderY - 52, cx + w * 0.44, shoulderY - 26, cx + w * 0.5, h + 10);
    c.closePath();
    c.fill();

    // 脖子
    c.fillStyle = '#080f18';
    c.beginPath();
    c.ellipse(cx, headY + headRY * 0.92, S * 0.052, S * 0.10, 0, 0, 7);
    c.fill();

    // 后发
    c.fillStyle = '#070d16';
    c.beginPath();
    c.ellipse(cx, headY + S * 0.015, headRX * 1.22, headRY * 1.16, 0, 0, 7);
    c.fill();

    // 头
    const faceG = c.createLinearGradient(cx - headRX, headY - headRY, cx + headRX, headY + headRY);
    faceG.addColorStop(0, '#132132');
    faceG.addColorStop(0.55, '#0c1622');
    faceG.addColorStop(1, '#070e17');
    c.fillStyle = faceG;
    c.beginPath();
    c.ellipse(cx, headY, headRX, headRY, 0, 0, 7);
    c.fill();

    // 刘海
    c.fillStyle = '#080e17';
    c.beginPath();
    c.moveTo(cx - headRX * 1.05, headY - headRY * 0.15);
    c.bezierCurveTo(cx - headRX * 1.0, headY - headRY * 1.25, cx + headRX * 1.0, headY - headRY * 1.25, cx + headRX * 1.05, headY - headRY * 0.15);
    c.bezierCurveTo(cx + headRX * 0.55, headY - headRY * 0.55, cx - headRX * 0.15, headY - headRY * 0.72, cx - headRX * 1.05, headY - headRY * 0.15);
    c.closePath();
    c.fill();

    // 轮廓光
    c.strokeStyle = accent + '55';
    c.lineWidth = 1.4;
    c.beginPath();
    c.ellipse(cx, headY, headRX, headRY, 0, Math.PI * 0.62, Math.PI * 1.42);
    c.stroke();

    // 肩线光
    c.strokeStyle = accent + '40';
    c.lineWidth = 1.2;
    c.beginPath();
    c.moveTo(cx - w * 0.46, h);
    c.bezierCurveTo(cx - w * 0.40, shoulderY - 22, cx - w * 0.15, shoulderY - 50, cx - w * 0.02, shoulderY - 50);
    c.stroke();
    c.restore();

    /* 眼睛 */
    const eyeY = headY + headRY * 0.12;
    const eyeDX = headRX * 0.46;
    const eyeW = headRX * 0.40;
    const eyeH = headRY * 0.20;
    const open = 1 - this.blink;

    const glow = 0.55 + 0.45 * Math.sin(this.t * 2.2) + this.pulseV * 0.6;
    [-1, 1].forEach(side => {
      const ex = cx + side * eyeDX;
      c.save();
      c.translate(ex, eyeY);

      // 眼窝阴影
      c.fillStyle = 'rgba(2,6,12,0.85)';
      c.beginPath();
      c.ellipse(0, 0, eyeW * 1.30, eyeH * 1.55, 0, 0, 7);
      c.fill();

      if (open > 0.05) {
        c.save();
        c.scale(1, open);
        // 虹膜
        const ir = c.createRadialGradient(0, 0, 0, 0, 0, eyeH * 1.1);
        ir.addColorStop(0, '#f2ffff');
        ir.addColorStop(0.28, accent);
        ir.addColorStop(1, accent + '22');
        c.shadowColor = accent;
        c.shadowBlur = 22 * (0.6 + glow * 0.7);
        c.fillStyle = ir;
        c.beginPath();
        c.ellipse(0, 0, eyeW * 0.52, eyeH * 0.92, 0, 0, 7);
        c.fill();
        c.shadowBlur = 0;
        // 瞳孔
        c.fillStyle = '#02060c';
        c.beginPath();
        c.ellipse(0, 0, eyeW * 0.18, eyeH * 0.52, 0, 0, 7);
        c.fill();
        // 高光
        c.fillStyle = 'rgba(255,255,255,0.92)';
        c.beginPath();
        c.arc(-eyeW * 0.16, -eyeH * 0.30, eyeH * 0.17, 0, 7);
        c.fill();
        c.restore();
      } else {
        // 闭眼：一条细线
        c.strokeStyle = accent + '99';
        c.lineWidth = 1.6;
        c.beginPath();
        c.moveTo(-eyeW * 0.5, 0); c.quadraticCurveTo(0, eyeH * 0.35, eyeW * 0.5, 0);
        c.stroke();
      }
      c.restore();
    });

    /* 眼神光晕 */
    c.save();
    c.globalCompositeOperation = 'lighter';
    const eg = c.createRadialGradient(cx, eyeY, 0, cx, eyeY, S * 0.30);
    eg.addColorStop(0, accent + '22');
    eg.addColorStop(1, accent + '00');
    c.fillStyle = eg;
    c.fillRect(0, 0, w, h);
    c.restore();

    /* 边框 */
    c.strokeStyle = 'rgba(120,190,225,0.18)';
    c.lineWidth = 1;
    c.strokeRect(0.5, 0.5, w - 1, h - 1);
  }
}

window.PersonaAvatar = PersonaAvatar;
