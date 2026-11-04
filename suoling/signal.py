"""纯标准库信号处理：FFT、Welch 功率谱、频带功率、熵、Hjorth、伪迹检测。

不依赖 numpy。所有函数输入为 Python list[float]，采样率单位 Hz。
"""

from __future__ import annotations

import cmath
import math
import random
from dataclasses import dataclass, field

# ---------------------------------------------------------------- 频带定义
# 名称, 下限, 上限, 中文名
BANDS: tuple[tuple[str, float, float, str], ...] = (
    ("delta", 1.0, 4.0, "δ 深眠"),
    ("theta", 4.0, 8.0, "θ 潜意识"),
    ("alpha", 8.0, 13.0, "α 静息"),
    ("beta", 13.0, 30.0, "β 专注"),
    ("gamma", 30.0, 45.0, "γ 整合"),
)
BAND_COLORS = {
    "delta": "#6b5bd2",
    "theta": "#9b6bff",
    "alpha": "#38e8ff",
    "beta": "#ffb057",
    "gamma": "#ff5fa2",
}
BAND_ZH = {b[0]: b[3] for b in BANDS}


# ---------------------------------------------------------------- 基础统计
def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def variance(xs: list[float], mu: float | None = None) -> float:
    if not xs:
        return 0.0
    m = mean(xs) if mu is None else mu
    return sum((x - m) ** 2 for x in xs) / len(xs)


def stdev(xs: list[float]) -> float:
    return math.sqrt(max(0.0, variance(xs)))


def median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def mad(xs: list[float], med: float | None = None) -> float:
    """中位数绝对偏差（稳健尺度）。"""
    m = median(xs) if med is None else med
    return median([abs(x - m) for x in xs])


def clip01(v: float) -> float:
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


# ---------------------------------------------------------------- 预处理
def detrend(xs: list[float]) -> list[float]:
    """最小二乘去线性趋势（去直流漂移）。"""
    n = len(xs)
    if n < 3:
        return list(xs)
    t_mean = (n - 1) / 2.0
    mu = mean(xs)
    num = sum((i - t_mean) * (xs[i] - mu) for i in range(n))
    den = sum((i - t_mean) ** 2 for i in range(n))
    slope = num / den if den else 0.0
    return [xs[i] - (mu + slope * (i - t_mean)) for i in range(n)]


def moving_average(xs: list[float], win: int) -> list[float]:
    if win <= 1 or len(xs) < win:
        return list(xs)
    out: list[float] = []
    acc = sum(xs[:win])
    out.append(acc / win)
    for i in range(win, len(xs)):
        acc += xs[i] - xs[i - win]
        out.append(acc / win)
    return out


def bandpass(xs: list[float], fs: float, lo: float, hi: float) -> list[float]:
    """零相位的高/低通近似：先减去滑动均值（去低频），再滑动均值（去高频）。

    这是廉价但稳定的实现，足以用于可视化与包络特征；频谱特征由 Welch 直接估计，
    不依赖此滤波器。
    """
    y = list(xs)
    if lo > 0:
        win = max(3, int(round(fs / lo)))
        base = moving_average(y, win)
        y = [a - b for a, b in zip(y, base)]
    if hi < fs / 2:
        win = max(2, int(round(fs / (2 * hi))))
        y = moving_average(y, win)
    return y


def normalize_signal(xs: list[float]) -> list[float]:
    """按稳健尺度归一化到约 ±1，抗尖峰。"""
    if not xs:
        return []
    m = median(xs)
    s = mad(xs, m) * 1.4826
    if s < 1e-9:
        s = stdev(xs) or 1.0
    return [clamp((x - m) / (6.0 * s), -1.0, 1.0) for x in xs]


def resample_linear(xs: list[float], fs_in: float, fs_out: float) -> list[float]:
    if fs_in == fs_out or not xs:
        return list(xs)
    dur = len(xs) / fs_in
    n_out = max(2, int(round(dur * fs_out)))
    out = []
    for i in range(n_out):
        pos = i * fs_in / fs_out
        i0 = int(pos)
        frac = pos - i0
        a = xs[i0] if i0 < len(xs) else xs[-1]
        b = xs[i0 + 1] if i0 + 1 < len(xs) else a
        out.append(a + (b - a) * frac)
    return out


# ---------------------------------------------------------------- FFT / Welch
def _fft(a: list[complex]) -> list[complex]:
    """迭代式基 2 FFT。长度必须是 2 的幂。"""
    n = len(a)
    if n & (n - 1):
        raise ValueError("FFT length must be a power of two")
    if n == 1:
        return a
    reordered = [0j] * n
    bits = n.bit_length() - 1
    for i, v in enumerate(a):
        r = 0
        x = i
        for _ in range(bits):
            r = (r << 1) | (x & 1)
            x >>= 1
        reordered[r] = v
    size = 2
    while size <= n:
        half = size // 2
        step = cmath.exp(-2j * math.pi / size)
        for start in range(0, n, size):
            w = 1 + 0j
            for k in range(start, start + half):
                even = reordered[k]
                odd = reordered[k + half] * w
                reordered[k] = even + odd
                reordered[k + half] = even - odd
                w *= step
        size <<= 1
    return reordered


def hann(n: int) -> list[float]:
    if n <= 1:
        return [1.0] * n
    return [0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1)) for i in range(n)]


@dataclass
class Spectrum:
    freqs: list[float] = field(default_factory=list)
    power: list[float] = field(default_factory=list)  # 单边 PSD，单位 μV²/Hz
    resolution: float = 0.0
    segments: int = 0
    window_seconds: float = 0.0

    def band_power(self, lo: float, hi: float) -> float:
        return sum(p for f, p in zip(self.freqs, self.power) if lo <= f < hi)


def welch(
    xs: list[float],
    fs: float,
    nfft: int = 1024,
    overlap: float = 0.5,
    max_segments: int = 24,
) -> Spectrum:
    """Welch 法估计单边功率谱密度，返回 Hz 与 μV²/Hz。"""
    n = len(xs)
    nfft = min(nfft, 1 << max(6, (n - 1).bit_length()))
    if n < nfft:
        nfft = max(64, 1 << max(6, (n - 1).bit_length() // 1))
    nfft = max(64, min(nfft, 8192))
    step = max(1, int(nfft * (1 - overlap)))
    starts = list(range(0, max(1, n - nfft + 1), step))
    if not starts:
        starts = [0]
    if len(starts) > max_segments:
        picks = [starts[round(i * (len(starts) - 1) / (max_segments - 1))] for i in range(max_segments)]
        starts = sorted(set(picks))
    win = hann(nfft)
    win_energy = sum(w * w for w in win)
    acc = [0.0] * (nfft // 2 + 1)
    used = 0
    for st in starts:
        seg = xs[st : st + nfft]
        if len(seg) < nfft:
            seg = seg + [0.0] * (nfft - len(seg))
        m = mean(seg)
        buf = [complex((seg[i] - m) * win[i], 0.0) for i in range(nfft)]
        spec = _fft(buf)
        for k in range(nfft // 2 + 1):
            p = (spec[k].real ** 2 + spec[k].imag ** 2) / (fs * win_energy)
            acc[k] += p * (1.0 if k in (0, nfft // 2) else 2.0)
        used += 1
    df = fs / nfft
    freqs = [k * df for k in range(nfft // 2 + 1)]
    power = [v / max(1, used) for v in acc]
    return Spectrum(freqs, power, df, used, nfft / fs)


# ---------------------------------------------------------------- 谱特征
def peak_in_band(spec: Spectrum, lo: float, hi: float) -> tuple[float, float]:
    """返回带内峰值频率（抛物线插值）与峰值功率。"""
    idx = [i for i, f in enumerate(spec.freqs) if lo <= f <= hi]
    if not idx:
        return (lo + hi) / 2, 0.0
    best = max(idx, key=lambda i: spec.power[i])
    f = spec.freqs[best]
    p = spec.power[best]
    if 0 < best < len(spec.power) - 1:
        a, b, c = spec.power[best - 1], p, spec.power[best + 1]
        denom = a - 2 * b + c
        if abs(denom) > 1e-15:
            delta = 0.5 * (a - c) / denom
            delta = clamp(delta, -0.5, 0.5)
            f += delta * spec.resolution
            p = b - 0.25 * (a - c) * delta
    return f, max(0.0, p)


def spectral_centroid(spec: Spectrum, lo: float = 1.0, hi: float = 45.0) -> float:
    tot = 0.0
    num = 0.0
    for f, p in zip(spec.freqs, spec.power):
        if lo <= f <= hi:
            tot += p
            num += f * p
    return num / tot if tot > 0 else 0.0


def spectral_edge(spec: Spectrum, pct: float = 0.95, lo: float = 1.0, hi: float = 45.0) -> float:
    total = sum(p for f, p in zip(spec.freqs, spec.power) if lo <= f <= hi)
    if total <= 0:
        return 0.0
    acc = 0.0
    for f, p in zip(spec.freqs, spec.power):
        if lo <= f <= hi:
            acc += p
            if acc >= total * pct:
                return f
    return hi


def spectral_slope(spec: Spectrum, lo: float = 2.0, hi: float = 40.0) -> float:
    """1/f 斜率（log-log 线性回归）。越负越"安静"，接近 0 越接近白噪。"""
    pts = [(math.log10(f), math.log10(p)) for f, p in zip(spec.freqs, spec.power) if lo <= f <= hi and p > 1e-14]
    n = len(pts)
    if n < 4:
        return -2.0
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    num = sum((x - mx) * (y - my) for x, y in pts)
    den = sum((x - mx) ** 2 for x, _ in pts)
    return num / den if den else -2.0


def spectral_entropy(spec: Spectrum, lo: float = 1.0, hi: float = 45.0) -> float:
    vals = [p for f, p in zip(spec.freqs, spec.power) if lo <= f <= hi]
    total = sum(vals)
    if total <= 0:
        return 0.0
    h = 0.0
    for p in vals:
        if p > 0:
            q = p / total
            h -= q * math.log2(q)
    return h / math.log2(len(vals)) if len(vals) > 1 else 0.0


# ---------------------------------------------------------------- 熵 / 复杂度
def _phi(xs: list[float], m: int, r: float) -> float:
    """SampEn 的匹配概率（含自身匹配，最后在 SampEn 中约去）。"""
    n = len(xs)
    if n <= m:
        return 0.0
    count = 0
    for i in range(n - m):
        xi = xs[i]
        for j in range(n - m):
            ok = True
            for k in range(1, m):
                if abs(xs[i + k] - xs[j + k]) > r:
                    ok = False
                    break
            if ok and abs(xi - xs[j]) <= r:
                count += 1
    total = (n - m) * (n - m)
    return count / total if total else 0.0


def sample_entropy(xs: list[float], m: int = 2, r_factor: float = 0.2, max_points: int = 320) -> float:
    """样本熵。为控制 O(n²) 开销，超长序列等间隔抽样。高=复杂/清醒，低=规律/困倦。"""
    if len(xs) < m + 3:
        return 0.0
    if len(xs) > max_points:
        step = len(xs) / max_points
        xs = [xs[int(i * step)] for i in range(max_points)]
    r = r_factor * (stdev(xs) or 1e-9)
    a = _phi(xs, m + 1, r)
    b = _phi(xs, m, r)
    if a <= 0 or b <= 0:
        return 0.0
    return clamp(-math.log(a / b), 0.0, 3.0)


def hurst_exponent(xs: list[float], max_lag: int = 24) -> float:
    """R/S 分析的 Hurst 指数，约 0.5 白噪，>0.5 持续相关。"""
    n = len(xs)
    if n < 64:
        return 0.5
    lags = [2, 4, 8, 16, 32, 64, 128, 256]
    lags = [l for l in lags if l * 2 <= n][:max_lag // 4 or 1] or [max(2, n // 8)]
    pts: list[tuple[float, float]] = []
    for lag in lags:
        chunks = n // lag
        if chunks < 2:
            continue
        rs_vals = []
        for c in range(min(chunks, 8)):
            seg = xs[c * lag : (c + 1) * lag]
            mu = mean(seg)
            dev = [0.0]
            for v in seg:
                dev.append(dev[-1] + (v - mu))
            rng = max(dev) - min(dev)
            sd = stdev(seg)
            if sd > 1e-12 and rng > 0:
                rs_vals.append(rng / sd)
        if rs_vals:
            pts.append((math.log10(lag), math.log10(mean(rs_vals))))
    if len(pts) < 2:
        return 0.5
    mx = mean([p[0] for p in pts])
    my = mean([p[1] for p in pts])
    num = sum((x - mx) * (y - my) for x, y in pts)
    den = sum((x - mx) ** 2 for x, _ in pts)
    return clamp(num / den if den else 0.5, 0.05, 1.0)


def hjorth(xs: list[float]) -> tuple[float, float, float]:
    """Hjorth 活动度/移动度/复杂度。"""
    d1 = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
    d2 = [d1[i + 1] - d1[i] for i in range(len(d1) - 1)]
    v0, v1, v2 = variance(xs), variance(d1), variance(d2)
    mob = math.sqrt(v1 / v0) if v0 > 1e-15 else 0.0
    mob_d = math.sqrt(v2 / v1) if v1 > 1e-15 else 0.0
    comp = mob_d / mob if mob > 1e-15 else 0.0
    return math.sqrt(v0), mob, comp


def envelope(xs: list[float], fs: float, win_seconds: float = 0.5) -> list[float]:
    """滑动 RMS 包络，用于"意识强度"曲线。"""
    win = max(2, int(fs * win_seconds))
    if win > len(xs):
        win = max(2, len(xs))
    sq = [x * x for x in xs]
    ma = moving_average(sq, win)
    return [math.sqrt(max(0.0, v)) for v in ma]


def blink_events(xs: list[float], fs: float) -> list[float]:
    """在额区导联上检测眨眼样大慢波，返回发生时刻（秒）。"""
    if len(xs) < fs:
        return []
    smooth = moving_average(xs, max(3, int(fs * 0.05)))
    med = median(smooth)
    scale = mad(smooth, med) * 1.4826 or stdev(smooth) or 1.0
    thr = 3.2 * scale
    times: list[float] = []
    min_gap = int(fs * 0.35)
    last = -min_gap
    for i in range(1, len(smooth) - 1):
        v = smooth[i] - med
        if v > thr and smooth[i] >= smooth[i - 1] and smooth[i] >= smooth[i + 1]:
            if i - last >= min_gap:
                times.append(round(i / fs, 2))
                last = i
    return times


def noise_floor(xs: list[float], fs: float) -> dict[str, float]:
    """伪迹与噪声估计：削顶比例、工频泄漏、基线漂移能量。"""
    n = len(xs)
    hi = max(xs)
    lo = min(xs)
    clip_eps = 1e-9
    clipped = sum(1 for v in xs if abs(v - hi) < clip_eps or abs(v - lo) < clip_eps) / max(1, n)
    spec = welch(xs, fs, nfft=min(1024, 1 << max(6, (n - 1).bit_length())))
    total = sum(p for f, p in zip(spec.freqs, spec.power) if 1 <= f <= 45.0) or 1e-12

    def around(f0: float) -> float:
        return sum(p for f, p in zip(spec.freqs, spec.power) if abs(f - f0) <= 1.0)

    line50 = around(50.0) / total
    line60 = around(60.0) / total
    drift = sum(p for f, p in zip(spec.freqs, spec.power) if f < 1.0) / (total + sum(
        p for f, p in zip(spec.freqs, spec.power) if f < 1.0))
    return {
        "clipped_ratio": round(clipped, 4),
        "line_noise": round(max(line50, line60), 4),
        "drift_ratio": round(drift, 4),
    }


# ---------------------------------------------------------------- 合成脑电
@dataclass
class SynthPreset:
    key: str
    name: str
    subtitle: str
    desc: str
    state: str
    amplitude: float = 32.0


SYNTH_PRESETS: list[SynthPreset] = [
    SynthPreset(
        key="meditation",
        name="静息冥想",
        subtitle="闭眼 · α 波主导",
        desc="枕区 α 节律强盛，θ 波缓慢起伏。像午后窗边的半梦半醒。",
        state="meditation",
        amplitude=38.0,
    ),
    SynthPreset(
        key="focus",
        name="深度专注",
        subtitle="睁眼 · β 波主导",
        desc="额区高频低幅快波，α 被抑制。解题时的那盏冷白灯。",
        state="focus",
        amplitude=22.0,
    ),
    SynthPreset(
        key="flow",
        name="心流创作",
        subtitle="θ+γ 混合 · 高复杂度",
        desc="θ 与 γ 跨频耦合，长程相关增强。写作者最容易忘记时间的状态。",
        state="flow",
        amplitude=30.0,
    ),
    SynthPreset(
        key="fatigue",
        name="疲惫深夜",
        subtitle="δ/θ 抬头 · α 崩解",
        desc="低频功率上升，高频塌陷。凌晨三点，意识开始漏水。",
        state="fatigue",
        amplitude=45.0,
    ),
]


def _pink(n: int, rng: random.Random, beta: float = 1.0) -> list[float]:
    """1/f^beta 噪声：构造共轭对称频谱，再做逆 FFT。"""
    size = 1 << max(6, (n - 1).bit_length())
    spec: list[complex] = [0j] * size
    for k in range(1, size // 2 + 1):
        f = k / size
        mag = (f ** (-beta / 2.0)) * (0.55 + 0.9 * rng.random())
        phase = rng.random() * 2 * math.pi
        v = cmath.rect(mag, phase)
        spec[k] = v
        spec[size - k] = v.conjugate()
    spec[0] = 0j
    inv = [v.conjugate() for v in _fft([v.conjugate() for v in spec])]
    out = [v.real / size for v in inv]
    m = mean(out)
    s = stdev(out) or 1.0
    return [(v - m) / s for v in out[:n]]


def _band_component(n: int, fs: float, f0: float, amp: float, rng: random.Random, mod: float = 0.35) -> list[float]:
    """窄带振荡：中心频率缓慢漂移 + 幅度包络调制，比纯正弦更像真实节律。"""
    out = []
    phase = rng.random() * 2 * math.pi
    drift = 0.0
    mod_phase = rng.random() * 2 * math.pi
    for i in range(n):
        t = i / fs
        drift = 0.92 * drift + 0.08 * (rng.random() - 0.5)
        f = f0 * (1.0 + 0.02 * drift)
        phase += 2 * math.pi * f / fs
        mod_phase += 2 * math.pi * (0.07 + 0.03 * rng.random()) / fs
        env = 1.0 + mod * math.sin(mod_phase) + 0.15 * (rng.random() - 0.5)
        out.append(amp * env * math.sin(phase))
    return out


def synthesize_eeg(
    state: str = "meditation",
    fs: int = 128,
    seconds: float = 12.0,
    seed: int | None = None,
    channels: int = 4,
) -> tuple[list[list[float]], list[str]]:
    """生成多导联合成 EEG（μV）。仅用于演示与教学，不冒充真实记录。"""
    rng = random.Random(seed if seed is not None else random.randrange(1 << 30))
    n = max(64, int(fs * seconds))
    presets = {p.key: p for p in SYNTH_PRESETS}
    preset = presets.get(state, presets["meditation"])
    amp = preset.amplitude

    # 每个状态的频带权重（相对幅度）
    profiles = {
        "meditation": {"delta": 0.18, "theta": 0.85, "alpha": 1.75, "beta": 0.22, "gamma": 0.10},
        "focus": {"delta": 0.22, "theta": 0.32, "alpha": 0.28, "beta": 1.15, "gamma": 0.32},
        "flow": {"delta": 0.22, "theta": 1.05, "alpha": 0.70, "beta": 0.70, "gamma": 0.72},
        "fatigue": {"delta": 1.20, "theta": 0.90, "alpha": 0.22, "beta": 0.15, "gamma": 0.06},
    }
    weights = profiles.get(state, profiles["meditation"])
    centers = {"delta": 2.2, "theta": 5.8, "alpha": 10.0, "beta": 19.0, "gamma": 38.0}
    if state == "meditation":
        centers["alpha"] = 9.4 + rng.random() * 1.2
    if state == "focus":
        centers["beta"] = 20.0 + rng.random() * 4.0
    if state == "flow":
        centers["alpha"] = 8.6 + rng.random() * 0.8

    names = ["Fp1", "Fp2", "C3", "C4", "O1", "O2", "T3", "T4"][:channels]
    # 额/中央/枕的空间增益：α 在枕区最强，β 在额区更强，θ 在中线
    gains_by_pos = {
        "Fp1": {"delta": 1.6, "theta": 1.2, "alpha": 0.55, "beta": 1.25, "gamma": 1.1},
        "Fp2": {"delta": 1.6, "theta": 1.2, "alpha": 0.55, "beta": 1.2, "gamma": 1.05},
        "C3": {"delta": 0.9, "theta": 1.1, "alpha": 0.95, "beta": 1.0, "gamma": 0.95},
        "C4": {"delta": 0.9, "theta": 1.1, "alpha": 0.95, "beta": 1.0, "gamma": 0.95},
        "O1": {"delta": 0.5, "theta": 0.7, "alpha": 1.7, "beta": 0.6, "gamma": 0.7},
        "O2": {"delta": 0.5, "theta": 0.7, "alpha": 1.7, "beta": 0.6, "gamma": 0.7},
        "T3": {"delta": 0.8, "theta": 0.9, "alpha": 0.8, "beta": 0.9, "gamma": 0.9},
        "T4": {"delta": 0.8, "theta": 0.9, "alpha": 0.8, "beta": 0.9, "gamma": 0.9},
    }

    leads: list[list[float]] = []
    for ch in names:
        g = gains_by_pos.get(ch, gains_by_pos["C3"])
        # 共享的 1/f 基底（全脑容积传导），各导联加独立噪声
        base = _pink(n, rng, beta=1.85)
        sig = [amp * 0.40 * b for b in base]
        for band, _lo, _hi, _ in BANDS:
            comp = _band_component(n, fs, centers[band] * (1 + 0.01 * (rng.random() - 0.5)), 1.0, rng)
            w = weights[band] * g[band] * amp * 0.30
            for i in range(n):
                sig[i] += w * comp[i]
        # 独立高频噪声 & 缓慢基线漂移
        for i in range(n):
            sig[i] += rng.gauss(0, amp * 0.035)
        drift = _band_component(n, fs, 0.16, amp * 0.12, rng, mod=0.1)
        sig = [a + b for a, b in zip(sig, drift)]
        # 眨眼伪迹（额区）
        if ch in ("Fp1", "Fp2"):
            k = max(1, int(seconds / 4))
            for _ in range(k):
                pos = rng.randrange(int(fs * 0.5), max(int(fs * 0.5) + 1, n - int(fs * 0.5)))
                width = int(fs * (0.16 + rng.random() * 0.08))
                height = amp * (1.8 + rng.random() * 0.9)
                for d in range(-width, width + 1):
                    idx = pos + d
                    if 0 <= idx < n:
                        sig[idx] += height * math.exp(-((d / (width / 2.2)) ** 2))
        leads.append([round(v, 3) for v in sig])
    return leads, names


def synthetic_csv(state: str = "meditation", fs: int = 128, seconds: float = 12.0, seed: int = 7) -> str:
    leads, names = synthesize_eeg(state, fs=fs, seconds=seconds, seed=seed)
    lines = [
        f"# EchoMind synthetic EEG | state={state} | fs={fs} | channels={len(names)} | seconds={seconds}",
        "# 合成数据，仅用于演示溯灵的分析流程，不是真实人类脑电记录",
        "time_s," + ",".join(names),
    ]
    n = len(leads[0])
    for i in range(n):
        row = [f"{i / fs:.4f}"] + [f"{leads[c][i]:.2f}" for c in range(len(names))]
        lines.append(",".join(row))
    return "\n".join(lines) + "\n"
