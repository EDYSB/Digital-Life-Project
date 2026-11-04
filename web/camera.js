/* ============================================================
   摄像头多视角录入
   ------------------------------------------------------------
   浏览器只能拿到 2D 画面：这里做的是"多角度采样 + 视角交叉淡化"，
   不是三维重建。所有帧只在本地处理，不上传。
   ============================================================ */
'use strict';

const CameraCapture = (() => {
  const STEPS = [
    { key: 'front', label: '正视', title: '正视镜头', hint: '把脸放进虚线椭圆，眼睛看镜头', angle: 0, turn: 0 },
    { key: 'left', label: '左转', title: '向左转一点', hint: '大约 15–20°，肩膀保持不动', angle: -1, turn: -1 },
    { key: 'right', label: '右转', title: '向右转一点', hint: '大约 15–20°，回到中间再转', angle: 1, turn: 1 },
    { key: 'up', label: '抬头', title: '微微抬头', hint: '下巴抬一点，别仰太多', angle: 2, turn: 0 },
    { key: 'smile', label: '微笑', title: '自然笑一下', hint: '眼睛看着镜头，不用露牙', angle: 3, turn: 0 },
  ];

  let modal = null;
  let video = null;
  let overlay = null;
  let stream = null;
  let stepIndex = 0;
  let shots = [];           // {key, photo, meta, thumb}
  let raf = null;
  let stable = 0;
  let lastCheck = 0;
  let adjust = { zoom: 1, x: 0, y: 0 };
  let onDone = null;
  let busy = false;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function buildModal() {
    if (modal) return modal;
    modal = el('div', 'modal camera-modal');
    modal.id = 'modal-camera';
    modal.innerHTML = `
      <div class="cam-body">
        <button class="x-btn cam-x" data-close aria-label="关闭">×</button>
        <div class="cam-head">
          <div>
            <div class="eyebrow">FACE CAPTURE · 多视角录入</div>
            <h3>让镜头记住你的五个角度。</h3>
            <p>正面、左转、右转、抬头、微笑。每一帧都只在这台机器上处理。</p>
          </div>
          <div class="cam-progress" id="cam-progress"></div>
        </div>
        <div class="cam-stage">
          <video id="cam-video" playsinline autoplay muted></video>
          <canvas id="cam-overlay"></canvas>
          <div class="cam-guide" id="cam-guide">
            <svg viewBox="0 0 300 380" preserveAspectRatio="none">
              <ellipse cx="150" cy="168" rx="92" ry="118" fill="none" stroke="rgba(56,232,255,.55)" stroke-width="1.5" stroke-dasharray="6 6"/>
              <path d="M150 286 L150 330 M96 330 Q150 356 204 330" fill="none" stroke="rgba(56,232,255,.22)" stroke-width="1.2"/>
            </svg>
          </div>
          <div class="cam-count" id="cam-count"></div>
          <div class="cam-hint" id="cam-hint">正在启动摄像头…</div>
          <div class="cam-flash" id="cam-flash"></div>
        </div>
        <div class="cam-controls">
          <button class="ghost-btn" id="cam-retake" hidden>重拍当前</button>
          <button class="primary-btn" id="cam-shoot" disabled><span>拍摄</span><i class="arrow">◎</i></button>
          <button class="ghost-btn" id="cam-skip">跳过这一步</button>
        </div>
        <div class="cam-strip" id="cam-strip"></div>
        <div class="cam-foot">
          <span class="cam-note">2D 多视角采样，不是三维扫描。照片只写入本机档案。</span>
          <button class="primary-btn sm" id="cam-finish" disabled>完成录入</button>
        </div>
        <div class="cam-error" id="cam-error" hidden></div>
      </div>`;
    document.body.appendChild(modal);
    return modal;
  }

  function progressUI() {
    const box = modal.querySelector('#cam-progress');
    box.innerHTML = '';
    STEPS.forEach((s, i) => {
      const d = el('div', 'cam-dot' + (i === stepIndex ? ' on' : '') + (shots[i] ? ' done' : ''));
      d.innerHTML = `<i>${i + 1}</i><span>${s.label}</span>`;
      box.appendChild(d);
    });
  }

  function stripUI() {
    const strip = modal.querySelector('#cam-strip');
    strip.innerHTML = '';
    STEPS.forEach((s, i) => {
      const item = el('div', 'cam-thumb' + (i === stepIndex ? ' on' : ''));
      if (shots[i]) {
        const img = new Image();
        img.src = shots[i].photo;
        item.appendChild(img);
      } else {
        item.appendChild(el('span', 'ph', String(i + 1)));
      }
      item.appendChild(el('b', null, s.label));
      item.addEventListener('click', () => {
        if (shots[i]) { stepIndex = i; syncStep(); }
      });
      strip.appendChild(item);
    });
  }

  function syncStep() {
    const s = STEPS[stepIndex];
    modal.querySelector('#cam-hint').textContent = s.title + ' · ' + s.hint;
    modal.querySelector('#cam-retake').hidden = !shots[stepIndex];
    modal.querySelector('#cam-finish').disabled = shots.filter(Boolean).length < 3;
    progressUI();
    stripUI();
    stable = 0;
  }

  async function start(cb) {
    onDone = cb;
    shots = [];
    stepIndex = 0;
    buildModal();
    modal.classList.add('open');
    modal.querySelector('#cam-error').hidden = true;
    modal.querySelector('#cam-finish').disabled = true;
    syncStep();

    modal.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', close, { once: true }));
    modal.querySelector('#cam-shoot').addEventListener('click', () => shoot(0));
    modal.querySelector('#cam-retake').addEventListener('click', () => {
      shots[stepIndex] = null;
      syncStep();
    });
    modal.querySelector('#cam-skip').addEventListener('click', () => {
      if (stepIndex < STEPS.length - 1) { stepIndex++; syncStep(); }
    });
    modal.querySelector('#cam-finish').addEventListener('click', finish);

    video = modal.querySelector('#cam-video');
    overlay = modal.querySelector('#cam-overlay');

    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('这个浏览器不支持摄像头访问。请用 Chrome / Edge 打开 127.0.0.1 或 localhost。');
      }
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      video.srcObject = stream;
      await video.play();
      modal.querySelector('#cam-shoot').disabled = false;
      modal.querySelector('#cam-hint').textContent = '摄像头已就绪。' + STEPS[0].hint;
      checkLoop();
    } catch (err) {
      const box = modal.querySelector('#cam-error');
      box.hidden = false;
      box.innerHTML = '无法打开摄像头：' + escapeHtml(err.message) +
        '<br><br>常见原因：<br>· 用 <b>http://127.0.0.1:8017</b> 或 <b>localhost</b> 访问（局域网 IP 下浏览器会禁用摄像头）<br>' +
        '· 浏览器地址栏的摄像头权限被拒绝<br>· 摄像头正被其他程序占用';
      modal.querySelector('#cam-hint').textContent = '摄像头不可用';
    }
  }

  function checkLoop() {
    cancelAnimationFrame(raf);
    let last = 0;
    const loop = (ts) => {
      raf = requestAnimationFrame(loop);
      if (ts - last < 90) return;
      last = ts;
      if (!video || video.readyState < 2) return;
      drawOverlay(ts);
      const now = performance.now();
      if (now - lastCheck > 260) {
        lastCheck = now;
        const st = detect(video);
        const hint = modal.querySelector('#cam-hint');
        if (!st.ok) {
          stable = 0;
          hint.textContent = st.msg;
          hint.classList.add('warn');
        } else {
          hint.classList.remove('warn');
          hint.textContent = STEPS[stepIndex].title + ' · 位置不错，保持住';
          stable += 1;
          if (stable > 7 && !busy) shoot(0);
        }
        modal.querySelector('#cam-shoot').disabled = busy;
      }
    };
    raf = requestAnimationFrame(loop);
  }

  function detect(v) {
    const w = 160, h = 120;
    const cv = detect.cv || (detect.cv = document.createElement('canvas'));
    cv.width = w; cv.height = h;
    const ctx = cv.getContext('2d', { willReadFrequently: true });
    try {
      ctx.drawImage(v, 0, 0, w, h);
    } catch (e) { return { ok: false, msg: '画面还没准备好' }; }
    const d = ctx.getImageData(0, 0, w, h).data;
    let minX = w, minY = h, maxX = 0, maxY = 0, count = 0;
    for (let y = 2; y < h - 2; y += 2) {
      for (let x = 2; x < w - 2; x += 2) {
        const i = (y * w + x) * 4;
        const r = d[i], g = d[i + 1], b = d[i + 2];
        const yy = 0.299 * r + 0.587 * g + 0.114 * b;
        const cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b;
        const cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b;
        if (yy > 55 && cb > 76 && cb < 129 && cr > 132 && cr < 176 && r > g && r > b * 0.85) {
          count++;
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
      }
    }
    const ratio = count / ((w / 2) * (h / 2));
    if (ratio < 0.02) return { ok: false, msg: '没有找到脸 · 靠近一点，让光从正面来', box: null };
    const bw = maxX - minX, bh = maxY - minY;
    const cx = (minX + maxX) / w / 2, cy = (minY + maxY) / h / 2;
    if (bw < 28 || bh < 32) return { ok: false, msg: '脸太小了 · 再靠近一点', box: null };
    if (bw > 110 || bh > 108) return { ok: false, msg: '脸太近了 · 稍微退后半步', box: null };
    if (Math.abs(cx - 0.5) > 0.14) return { ok: false, msg: '把脸移到画面中间', box: null };
    if (Math.abs(cy - 0.46) > 0.16) return { ok: false, msg: '调整一下高度，让脸在椭圆里', box: null };
    return { ok: true, msg: '位置不错', box: { x: minX, y: minY, w: bw, h: bh } };
  }

  function drawOverlay(ts) {
    const r = overlay.getBoundingClientRect();
    const dpr = Math.min(2, devicePixelRatio || 1);
    overlay.width = Math.max(1, r.width * dpr);
    overlay.height = Math.max(1, r.height * dpr);
    const c = overlay.getContext('2d');
    c.clearRect(0, 0, overlay.width, overlay.height);
    const st = detect(video);
    if (st.ok && st.box) {
      const sx = overlay.width / 160, sy = overlay.height / 120;
      c.strokeStyle = 'rgba(56,232,255,.7)';
      c.lineWidth = 1.4 * dpr;
      c.strokeRect(st.box.x * sx, st.box.y * sy, st.box.w * sx, st.box.h * sy);
    }
    if (busy) {
      const p = Math.min(1, (performance.now() - busy) / 700);
      c.strokeStyle = `rgba(255,95,162,${0.8 - p * 0.5})`;
      c.lineWidth = 2 * dpr;
      c.beginPath();
      c.arc(overlay.width / 2, overlay.height / 2, 40 * dpr + p * 30 * dpr, -Math.PI / 2, -Math.PI / 2 + p * Math.PI * 2);
      c.stroke();
    }
  }

  async function shoot(auto) {
    if (busy || !video) return;
    busy = performance.now();
    const count = modal.querySelector('#cam-count');
    for (let n = 3; n >= 1; n--) {
      count.textContent = String(n);
      count.classList.add('show');
      await sleep(420);
    }
    count.classList.remove('show');
    const flash = modal.querySelector('#cam-flash');
    flash.classList.add('on');
    setTimeout(() => flash.classList.remove('on'), 180);

    const vw = video.videoWidth, vh = video.videoHeight;
    if (!vw || !vh) { busy = false; return; }
    const cv = document.createElement('canvas');
    cv.width = Math.min(900, vw);
    cv.height = Math.round(cv.width * vh / vw);
    const ctx = cv.getContext('2d');
    // 自拍镜像只用于预览；这里保留真实朝向
    ctx.drawImage(video, 0, 0, cv.width, cv.height);
    const blob = await new Promise(res => cv.toBlob(res, 'image/jpeg', 0.92));
    const file = new File([blob], `view_${STEPS[stepIndex].key}.jpg`, { type: 'image/jpeg' });
    try {
      const analyzed = await Face.analyze(file, { name: file.name });
      shots[stepIndex] = {
        key: STEPS[stepIndex].key,
        angle: STEPS[stepIndex].angle,
        turn: STEPS[stepIndex].turn,
        photo: analyzed.photo,
        meta: analyzed.meta,
      };
      const thumb = new Image();
      thumb.src = analyzed.photo;
      const strip = modal.querySelector('#cam-strip');
      if (strip.children[stepIndex]) {
        strip.children[stepIndex].innerHTML = '';
        strip.children[stepIndex].appendChild(thumb);
        strip.children[stepIndex].appendChild(el('b', null, STEPS[stepIndex].label));
      }
      if (stepIndex < STEPS.length - 1) stepIndex++;
      syncStep();
    } catch (err) {
      const box = modal.querySelector('#cam-error');
      box.hidden = false;
      box.textContent = '这一帧没拍好：' + err.message + '。再试一次。';
    } finally {
      setTimeout(() => { busy = false; }, 350);
    }
  }

  function finish() {
    const views = shots.filter(Boolean).map(s => ({
      key: s.key, angle: s.angle, turn: s.turn, photo: s.photo, meta: s.meta,
    }));
    if (views.length < 3) return;
    const primary = views.find(v => v.key === 'front') || views[0];
    const avatar = {
      mode: 'camera',
      views,
      primary: primary.photo,
      meta: primary.meta,
      palette: primary.meta.palette,
      captured_at: new Date().toISOString(),
    };
    close();
    if (onDone) onDone(avatar);
  }

  function close() {
    cancelAnimationFrame(raf);
    if (stream) stream.getTracks().forEach(t => t.stop());
    stream = null;
    if (modal) modal.classList.remove('open');
    shots = [];
    busy = false;
  }

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  return { start, close, STEPS };
})();

window.CameraCapture = CameraCapture;
