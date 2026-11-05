/* ============================================================
   录音 / 声纹 / 语音输入
   ------------------------------------------------------------
   诚实边界：
   - 浏览器无法克隆音色。这里只测量基频、频谱重心、能量与语速感，
     用来微调 TTS 的 pitch（"声线拟合"），不生成你的声音；
   - 保留一段你真实录下的短音频作为"初见样本"，可回放、可删除；
   - 语音识别可能由浏览器调用云端服务，默认关闭，开启时明确提示。
   ============================================================ */
'use strict';

const Mic = (() => {
  let rec = null;
  let recognition = null;

  async function getStream() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('这个浏览器不支持麦克风。');
    }
    return navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  }

  function blobToDataURL(blob) {
    return new Promise((resolve, reject) => {
      const fr = new FileReader();
      fr.onload = () => resolve(fr.result);
      fr.onerror = reject;
      fr.readAsDataURL(blob);
    });
  }

  function f0Of(buf, sampleRate) {
    // Normalised autocorrelation; take the 70-400 Hz peak
    const minLag = Math.floor(sampleRate / 400);
    const maxLag = Math.floor(sampleRate / 70);
    let best = -1, bestLag = -1;
    const n = Math.min(buf.length, 2048);
    for (let lag = minLag; lag <= maxLag; lag++) {
      let corr = 0, e1 = 0, e2 = 0;
      for (let i = 0; i < n - lag; i += 2) {
        corr += buf[i] * buf[i + lag];
        e1 += buf[i] * buf[i];
        e2 += buf[i + lag] * buf[i + lag];
      }
      const norm = corr / (Math.sqrt(e1 * e2) + 1e-9);
      if (norm > best) { best = norm; bestLag = lag; }
    }
    if (best < 0.32 || bestLag < 0) return 0;
    return sampleRate / bestLag;
  }

  function centroidOf(freq, sampleRate) {
    let num = 0, den = 0;
    for (let i = 1; i < freq.length; i++) {
      const f = i * sampleRate / 2 / freq.length;
      const v = freq[i];
      num += f * v; den += v;
    }
    return den > 0 ? num / den : 0;
  }

  /**
   * 录一段声音并做声纹测量。
   * @returns {clip, metrics:{f0, centroid, energy, voiced, duration}, duration}
   */
  async function record(ms = 3200, onTick) {
    const stream = await getStream();
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    const src = ctx.createMediaStreamSource(stream);
    const an = ctx.createAnalyser();
    an.fftSize = 2048;
    an.smoothingTimeConstant = 0.6;
    src.connect(an);
    const buf = new Float32Array(an.fftSize);
    const freq = new Uint8Array(an.frequencyBinCount);
    const f0s = [];
    const cents = [];
    const energies = [];
    let voiced = 0, frames = 0;

    const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
    const recorder = new MediaRecorder(stream, { mimeType: mime });
    const chunks = [];
    recorder.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
    const stopped = new Promise(res => { recorder.onstop = res; });
    rec = recorder;
    recorder.start(120);

    const started = performance.now();
    const timer = setInterval(() => {
      an.getFloatTimeDomainData(buf);
      an.getByteFrequencyData(freq);
      let e = 0;
      for (let i = 0; i < buf.length; i += 4) e += buf[i] * buf[i];
      e = Math.sqrt(e / (buf.length / 4));
      energies.push(e);
      if (e > 0.012) {
        const f = f0Of(buf, ctx.sampleRate);
        if (f > 60 && f < 420) { f0s.push(f); voiced++; }
        cents.push(centroidOf(freq, ctx.sampleRate));
      }
      frames++;
      if (onTick) onTick(Math.min(1, (performance.now() - started) / ms), e);
    }, 110);

    await new Promise(r => setTimeout(r, ms));
    clearInterval(timer);
    try { recorder.stop(); } catch (e) { }
    await stopped;
    stream.getTracks().forEach(t => t.stop());
    try { await ctx.close(); } catch (e) { }
    rec = null;

    const sorted = f0s.slice().sort((a, b) => a - b);
    const f0 = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
    const metrics = {
      f0: Math.round(f0),
      centroid: Math.round(cents.length ? cents.reduce((a, b) => a + b, 0) / cents.length : 0),
      energy: Math.round((energies.reduce((a, b) => a + b, 0) / Math.max(1, energies.length)) * 1000) / 1000,
      voiced: Math.round((voiced / Math.max(1, frames)) * 100) / 100,
      duration: Math.round(ms / 100) / 10,
    };
    const blob = new Blob(chunks, { type: 'audio/webm' });
    const clip = blob.size < 2_500_000 ? await blobToDataURL(blob) : null;
    return { clip, metrics, duration: ms / 1000, size: blob.size };
  }

  function stopRecord() {
    if (rec && rec.state === 'recording') { try { rec.stop(); } catch (e) { } }
  }

  function speechSupported() {
    return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  }

  /**
   * 一次性中文语音输入。
   * 注意：语音识别可能由浏览器调用云端服务；UI 必须提示。
   */
  function listen({ onText, onInterim, onEnd, onError }) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { if (onError) onError(new Error('这个浏览器不支持语音识别，请用键盘输入。')); return null; }
    if (recognition) { try { recognition.abort(); } catch (e) { } }
    const r = new SR();
    recognition = r;
    r.lang = 'zh-CN';
    r.interimResults = true;
    r.continuous = false;
    r.maxAlternatives = 1;
    let finalText = '';
    r.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalText += t;
        else interim += t;
      }
      if (interim && onInterim) onInterim(interim);
      if (finalText && onText) onText(finalText.trim());
    };
    r.onerror = (e) => { if (onError) onError(new Error(e.error === 'not-allowed' ? '麦克风权限被拒绝。' : '语音识别失败：' + e.error)); };
    r.onend = () => { recognition = null; if (onEnd) onEnd(finalText.trim()); };
    try { r.start(); } catch (e) { if (onError) onError(e); return null; }
    return {
      stop: () => { try { r.stop(); } catch (e) { } },
      abort: () => { try { r.abort(); } catch (e) { } },
    };
  }

  function stopListen() {
    if (recognition) { try { recognition.abort(); } catch (e) { } recognition = null; }
  }

  return { record, stopRecord, listen, stopListen, speechSupported };
})();

window.Mic = Mic;
