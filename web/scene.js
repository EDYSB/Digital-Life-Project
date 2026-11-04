/* 游戏模式：全屏视觉小说场景 */
'use strict';

const Scene = (() => {
  let root = null, char = null, textEl = null, nameEl = null, choicesEl = null, inputEl = null;
  let typing = null, history = [];
  let world = null;

  function $(s) { return document.querySelector(s); }

  function init() {
    if (root) return;
    root = $('#scene');
    char = $('#scene-char');
    textEl = $('#scene-text');
    nameEl = $('#scene-name');
    choicesEl = $('#scene-choices');
    inputEl = $('#scene-input');
    $('#scene-exit').addEventListener('click', close);
    $('#scene-form').addEventListener('submit', e => { e.preventDefault(); send(); });
    for (let i = 0; i < 26; i++) {
      const d = document.createElement('i');
      d.style.cssText = `position:absolute;width:${1 + Math.random() * 2}px;height:${1 + Math.random() * 2}px;border-radius:50%;background:rgba(56,232,255,${0.1 + Math.random() * 0.3});left:${Math.random() * 100}%;top:${Math.random() * 100}%;animation:float ${8 + Math.random() * 10}s ease-in-out infinite`;
      $('#scene-particles').appendChild(d);
    }
  }

  function open(profile) {
    init();
    if (!profile) return;
    const a = profile.avatar || {};
    const src = a.sprite || a.primary || (a.views && a.views[0] && a.views[0].photo) || '';
    if (src) {
      char.src = src;
      char.hidden = false;
      const ph = root.querySelector('.scene-char-placeholder');
      if (ph) ph.remove();
    } else {
      char.hidden = true;
      if (!root.querySelector('.scene-char-placeholder')) {
        const ph = document.createElement('div');
        ph.className = 'scene-char-placeholder';
        root.querySelector('.scene-char-wrap').appendChild(ph);
      }
    }
    nameEl.textContent = profile.persona.name;
    root.hidden = false;
    history = [];
    world = (profile.mind && profile.mind.world) || null;
    applyWorld(world);
    const greeting = profile.persona.greeting || '我在。';
    say(greeting);
    choices(['你是谁？', '你还记得我什么？', '我最近有点累。', '你觉得自己是真的吗？']);
    inputEl.focus();
    setTimeout(() => speak(greeting), 500);
  }

  function close() {
    if (root) root.hidden = true;
    if (typing) clearInterval(typing);
    if (window.Voice) Voice.stop();
  }

  function applyWorld(w) {
    if (!w || !root) return;
    root.classList.toggle('dark', (w.state || 'stable') !== 'stable');
    $('#scene-shade').style.background = w.state === 'protective'
      ? 'radial-gradient(45% 40% at 50% 45%, rgba(0,0,0,.5), rgba(0,0,0,.92))'
      : '';
  }

  function say(text) {
    if (typing) clearInterval(typing);
    textEl.textContent = '';
    let i = 0;
    typing = setInterval(() => {
      i += 1;
      textEl.textContent = text.slice(0, i);
      if (i >= text.length) { clearInterval(typing); typing = null; }
    }, 26);
  }

  function speak(text) {
    if (!window.Voice) return;
    const profile = window.state && state.profile;
    if (!profile) return;
    const mood = (profile.mind && profile.mind.mood) || { valence: .55, arousal: .5 };
    Voice.speak(text, {
      gender: 'female',
      emotion: { valence: mood.valence, arousal: mood.arousal },
      rate: 0.98, pitch: 1.02,
    });
    char.style.animation = 'none';
    void char.offsetWidth;
    char.style.animation = 'sceneBreathe 5.5s ease-in-out infinite, sceneTalk .35s ease-in-out 3';
  }

  function choices(list) {
    choicesEl.innerHTML = '';
    (list || []).slice(0, 4).forEach(t => {
      const b = document.createElement('button');
      b.textContent = t;
      b.onclick = () => { inputEl.value = t; send(); };
      choicesEl.appendChild(b);
    });
  }

  async function send() {
    const text = inputEl.value.trim();
    if (!text || !state.profile) return;
    inputEl.value = '';
    choicesEl.innerHTML = '';
    say('……');
    history.push({ role: 'user', text });
    try {
      const res = await fetch('/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: state.profile.id, message: text, history: history.slice(-10) }),
      }).then(r => r.json());
      const reply = res.text || '……';
      history.push({ role: 'assistant', text: reply });
      say(reply);
      speak(reply);
      if (res.world) { world = res.world; applyWorld(world); }
      if (res.mood && state.profile.mind) state.profile.mind.mood = { ...(state.profile.mind.mood || {}), ...res.mood };
      const next = ['继续说', '你还记得什么？', '我有点累。', '你在想什么？'];
      choices(next);
    } catch (e) {
      say('（连接断了。）');
    }
  }

  return { open, close };
})();

window.Scene = Scene;
