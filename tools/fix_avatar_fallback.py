import io

W = r"D:\EDY_POWERQ\Digital Life Project\web"

a = io.open(W + r"\app.js", encoding="utf-8").read()
if "avatarFallback" not in a:
    a = a.replace("""function startAvatarGif() {
  const img = document.querySelector('#avatar-gif');
  const cv = document.querySelector('#persona-canvas');
  if (!img) return;
  img.src = '/assets/anim/idle.gif';""",
"""let avatarFallback = 0;

function startAvatarGif() {
  const img = document.querySelector('#avatar-gif');
  const cv = document.querySelector('#persona-canvas');
  if (!img) return;
  // 加载失败时依次回退：当前动作 → 静态立绘 → 画布版本，避免出现裂图
  img.onerror = function () {
    avatarFallback += 1;
    if (avatarFallback === 1) {
      img.src = '/assets/df-idle.png';
    } else if (avatarFallback === 2) {
      img.classList.remove('on');
      if (cv) cv.style.display = '';
      if (window.PersonaAvatar && !welcomePersona) {
        welcomePersona = new PersonaAvatar(cv, { color: '#4fe3ff' });
      }
    }
  };
  avatarFallback = 0;
  img.src = '/assets/anim/idle.gif';""", 1)
    io.open(W + r"\app.js", "w", encoding="utf-8").write(a)
print("fallback:", "avatarFallback" in a)

h = io.open(W + r"\index.html", encoding="utf-8").read()
h = h.replace('<img id="avatar-gif" class="avatar-gif" alt="">',
              '<img id="avatar-gif" class="avatar-gif" alt="" decoding="async">')
io.open(W + r"\index.html", "w", encoding="utf-8").write(h)
print("html:", 'decoding="async"' in h)
