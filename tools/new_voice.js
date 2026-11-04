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

  return { supported, list, pick, speak, stop, estimate };
})();
