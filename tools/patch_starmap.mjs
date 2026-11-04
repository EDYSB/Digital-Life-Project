import fs from 'node:fs';

const p = 'web/starmap.js';
let lines = fs.readFileSync(p, 'utf8').split('\n');

const start = lines.findIndex(l => l.trim() === 'toMap(e) {');
const endMarker = lines.findIndex((l, i) => i > start && l.trim() === 'setDays(d) { this.days = d; }');
if (start < 0 || endMarker < 0) throw new Error('anchors not found');

const replacement = `    toMap(e) {
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

`.split('\n');

lines = [...lines.slice(0, start), ...replacement, ...lines.slice(endMarker - 1)];
let s = lines.join('\n');

// 脑轮廓
const brainStart = s.indexOf("      c.translate(W * 0.5, H * 0.52);");
const brainEnd = s.indexOf("      // 脑区标签");
if (brainStart < 0 || brainEnd < 0) throw new Error('brain anchors not found');
const brainNew = `      c.translate(W * 0.5, H * 0.52);
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

`;
s = s.slice(0, brainStart) + brainNew + s.slice(brainEnd);
s = s.replace("if (r > 0.92) { n.x *= 0.92 / r; n.y *= 0.92 / r; }", "if (r > 0.86) { n.x *= 0.86 / r; n.y *= 0.86 / r; }");

fs.writeFileSync(p, s);
console.log('patched');
