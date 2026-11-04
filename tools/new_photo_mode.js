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

