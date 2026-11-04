"""EEG 分析：频带功率、复杂度、伪迹、质量评分，以及到 7 个维度的投影。"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import signal as sig
from .eeg import EEGData

TRAITS = ("curiosity", "empathy", "order", "alertness", "creativity", "stability", "sensory")
TRAIT_ZH = {
    "curiosity": "好奇",
    "empathy": "共情",
    "order": "秩序",
    "alertness": "警觉",
    "creativity": "创造",
    "stability": "定力",
    "sensory": "感受力",
}


def _logistic(x: float, center: float, slope: float) -> float:
    return 1.0 / (1.0 + math.exp(-(x - center) * slope))


def _norm(x: float, lo: float, hi: float) -> float:
    return sig.clip01((x - lo) / (hi - lo)) if hi > lo else 0.5


def _channel_pairs(names: list[str]) -> list[tuple[int, int, str]]:
    """找左右半球配对（C3/C4, O1/O2, Fp1/Fp2, T3/T4 …）。"""
    idx = {n.upper(): i for i, n in enumerate(names)}
    pairs = []
    for a, b, label in [("C3", "C4", "中央"), ("O1", "O2", "枕区"),
                        ("FP1", "FP2", "额区"), ("F3", "F4", "额区"),
                        ("T3", "T4", "颞区"), ("P3", "P4", "顶区")]:
        if a in idx and b in idx:
            pairs.append((idx[a], idx[b], label))
    if not pairs and len(names) >= 2:
        pairs.append((0, min(1, len(names) - 1), "前后"))
    return pairs


@dataclass
class EEGFeatures:
    fs: float
    seconds: float
    n_channels: int
    channel_names: list[str]
    bands: dict
    peak_hz: float
    centroid: float
    edge95: float
    entropy: float
    slope: float
    sampen: float
    hurst: float
    hjorth: tuple[float, float, float]
    asymmetry: float
    peak_stability: float
    quality: dict
    presence: list[float]
    dominant: str
    focus_channel: int


def analyze_eeg(eeg: EEGData) -> tuple[EEGFeatures, dict]:
    fs = eeg.fs
    names = list(eeg.channel_names)
    # 参考导联：全导联平均（更抗单导联伪迹）
    n = eeg.n_samples
    avg = [sum(ch[i] for ch in eeg.channels) / len(eeg.channels) for i in range(n)]
    avg = sig.detrend(avg)

    # 频带功率：逐导联 Welch，再取均值
    band_abs = {b[0]: 0.0 for b in sig.BANDS}
    specs = []
    for ch in eeg.channels:
        spec = sig.welch(sig.detrend(ch), fs, nfft=min(1024, 1 << max(6, (len(ch) - 1).bit_length())))
        specs.append(spec)
        for key, lo, hi, _ in sig.BANDS:
            band_abs[key] += spec.band_power(lo, hi)
    for key in band_abs:
        band_abs[key] /= max(1, len(eeg.channels))

    total = sum(band_abs.values()) or 1e-12
    rel = {k: round(v / total, 4) for k, v in band_abs.items()}
    abs_db = {k: round(10 * math.log10(max(v, 1e-12)), 2) for k, v in band_abs.items()}

    spec_avg = specs[0]
    if len(specs) > 1:
        nfft = len(specs[0].power)
        spec_avg = sig.Spectrum(
            list(specs[0].freqs),
            [sum(s.power[i] for s in specs) / len(specs) for i in range(nfft)],
            specs[0].resolution,
            specs[0].segments,
            specs[0].window_seconds,
        )

    peak_hz, _ = sig.peak_in_band(spec_avg, 7.5, 12.5)
    centroid = sig.spectral_centroid(spec_avg)
    edge95 = sig.spectral_edge(spec_avg, 0.95)
    entropy = sig.spectral_entropy(spec_avg)
    slope = sig.spectral_slope(spec_avg)
    sampen = sig.sample_entropy(avg, m=2, r_factor=0.2)
    hurst = sig.hurst_exponent(avg)
    hj = sig.hjorth(avg)

    # 半球不对称：alpha 功率的 (右-左)/(右+左)
    asym = 0.0
    for i, j, _label in _channel_pairs(names):
        a_i = sum(p for f, p in zip(specs[i].freqs, specs[i].power) if 8.0 <= f <= 13.0)
        a_j = sum(p for f, p in zip(specs[j].freqs, specs[j].power) if 8.0 <= f <= 13.0)
        if a_i + a_j > 1e-12:
            asym = (a_j - a_i) / (a_j + a_i)
            break

    # alpha 峰稳定性：跨窗口峰频的离散度
    win = max(1, int(fs * 2))
    peaks = []
    ch0 = avg
    for start in range(0, max(1, len(ch0) - win + 1), win):
        seg = ch0[start : start + win]
        if len(seg) < int(fs):
            continue
        sp = sig.welch(seg, fs, nfft=512 if len(seg) >= 512 else 256)
        f, _ = sig.peak_in_band(sp, 7.5, 12.5)
        peaks.append(f)
    if len(peaks) > 1:
        mu = sum(peaks) / len(peaks)
        sd = math.sqrt(sum((p - mu) ** 2 for p in peaks) / len(peaks))
        peak_stability = sig.clip01(1.0 - sd / 1.2)
    else:
        peak_stability = 0.5

    # 伪迹与质量
    noise = sig.noise_floor(avg, fs)
    blinks = sig.blink_events(eeg.channels[0], fs)
    dur_score = sig.clip01(eeg.seconds / 10.0)
    clip_pen = sig.clip01(1.0 - noise["clipped_ratio"] * 25)
    line_pen = sig.clip01(1.0 - noise["line_noise"] * 4)
    slope_score = _norm(slope, -3.2, -0.8)
    quality_score = sig.clip01(0.28 * dur_score + 0.24 * clip_pen + 0.18 * line_pen
                               + 0.15 * slope_score + 0.15 * _norm(entropy, 0.45, 0.95))

    # 意识强度曲线
    env = sig.envelope(avg, fs, 0.4)
    stride = max(1, len(env) // 120)
    presence = [round(sig.clip01(v / (sig.stdev(avg) * 2.2 + 1e-9)), 3) for v in env[::stride]][:120]
    presence = sig.moving_average(presence, 3)

    # 主频带
    dominant = max(rel, key=rel.get)
    focus_channel = max(range(len(eeg.channels)),
                        key=lambda i: sum(p for f, p in zip(specs[i].freqs, specs[i].power) if 8 <= f <= 13))

    spectrum = {
        "freqs": [round(f, 2) for f in spec_avg.freqs if 0.5 <= f <= 48.0],
        "power_db": [round(10 * math.log10(max(p, 1e-12)), 1) for f, p in
                     zip(spec_avg.freqs, spec_avg.power) if 0.5 <= f <= 48.0],
    }

    feats = EEGFeatures(
        fs=fs, seconds=eeg.seconds, n_channels=len(eeg.channels), channel_names=names,
        bands={k: {"abs": round(band_abs[k], 2), "rel": rel[k], "db": abs_db[k],
                   "label": sig.BAND_ZH[k], "color": sig.BAND_COLORS[k]} for k in band_abs},
        peak_hz=round(peak_hz, 2), centroid=round(centroid, 2), edge95=round(edge95, 2),
        entropy=round(entropy, 3), slope=round(slope, 3), sampen=round(sampen, 3),
        hurst=round(hurst, 3), hjorth=(round(hj[0], 2), round(hj[1], 3), round(hj[2], 3)),
        asymmetry=round(asym, 3), peak_stability=round(peak_stability, 3),
        quality={
            "score": round(quality_score, 3),
            "duration": round(eeg.seconds, 1),
            "blinks": len(blinks),
            "blink_times": blinks[:12],
            "clipped_ratio": noise["clipped_ratio"],
            "line_noise": noise["line_noise"],
            "drift_ratio": noise["drift_ratio"],
            "notes": eeg.notes,
        },
        presence=presence, dominant=dominant, focus_channel=focus_channel,
    )

    summary = {
        "bands": feats.bands,
        "spectrum": spectrum,
        "waveform": {
            "fs": fs,
            "seconds": round(eeg.seconds, 2),
            "names": names,
            "channels": [[round(v, 2) for v in ch] for ch in eeg.channels],
            "presence": presence,
        },
        "peak_hz": feats.peak_hz,
        "centroid": feats.centroid,
        "entropy": feats.entropy,
        "slope": feats.slope,
        "sampen": feats.sampen,
        "hurst": feats.hurst,
        "hjorth": {"activity": feats.hjorth[0], "mobility": feats.hjorth[1],
                   "complexity": feats.hjorth[2]},
        "asymmetry": feats.asymmetry,
        "peak_stability": feats.peak_stability,
        "dominant": feats.dominant,
        "quality": feats.quality,
        "seconds": feats.seconds,
        "n_channels": feats.n_channels,
    }
    return feats, summary


def eeg_traits(f: EEGFeatures) -> tuple[dict[str, float], dict[str, list[dict]]]:
    """把信号特征投影为 7 个维度（0~1），并给出每个维度的来源。"""
    rel = {k: v["rel"] for k, v in f.bands.items()}
    beta_alpha = (rel["beta"] + rel["gamma"] * 0.5) / max(1e-6, rel["alpha"] + 0.02)
    slow = rel["delta"] + rel["theta"]

    raw = {
        "curiosity": 0.42 * _logistic(rel["beta"], 0.15, 12.0) + 0.38 * _norm(f.sampen, 0.95, 2.4) + 0.20 * _norm(beta_alpha, 0.6, 3.4),
        "empathy": 0.50 * _logistic(rel["alpha"], 0.19, 12.0) + 0.25 * _norm(f.asymmetry, -0.35, 0.35) + 0.25 * _logistic(rel["theta"], 0.16, 11.0),
        "order": 0.40 * _logistic(f.peak_stability, 0.50, 7.0) + 0.24 * _logistic(rel["alpha"], 0.20, 10.0) + 0.20 * _logistic(rel["beta"], 0.25, 6.0) + 0.16 * (1 - _norm(f.sampen, 0.9, 2.6)),
        "alertness": 0.50 * _logistic(beta_alpha, 1.0, 1.7) + 0.28 * _norm(f.centroid, 7.5, 22.0) + 0.22 * (1 - _logistic(slow, 0.50, 9.0)),
        "creativity": 0.42 * _logistic(rel["gamma"], 0.045, 30.0) + 0.36 * _norm(f.sampen, 0.9, 2.5) + 0.22 * _norm(f.hurst, 0.45, 0.85),
        "stability": 0.40 * _logistic(slow, 0.42, 8.0) + 0.30 * _logistic(f.peak_stability, 0.40, 6.0) + 0.30 * (1 - _logistic(beta_alpha, 1.1, 1.8)),
        "sensory": 0.45 * _logistic(rel["theta"] + rel["gamma"], 0.16, 10.0) + 0.30 * _norm(f.asymmetry, -0.3, 0.3) + 0.25 * _logistic(f.sampen, 1.2, 2.2),
    }
    # 质量差的段做收缩，避免把噪声当人格
    shrink = 0.55 + 0.45 * f.quality["score"]
    mean_trait = sum(raw.values()) / len(raw)
    amplitude = {k: round(0.5 + (v - mean_trait) * 0.5 * shrink, 3) for k, v in raw.items()}
    traits = {k: round(0.5 + (v - 0.5) * shrink, 3) for k, v in raw.items()}

    def dom(*vals: tuple[str, float]) -> list[dict]:
        out = []
        for name, w in vals:
            out.append({"source": name, "weight": round(w, 2)})
        return out

    sources = {
        "curiosity": dom(("beta 相对功率", 0.45), ("样本熵", 0.35), ("beta/alpha 比", 0.20)),
        "empathy": dom(("alpha 相对功率", 0.50), ("半球不对称", 0.25), ("theta 相对功率", 0.25)),
        "order": dom(("alpha 峰稳定性", 0.50), ("alpha 相对功率", 0.30), ("低熵", 0.20)),
        "alertness": dom(("beta/alpha 比", 0.55), ("谱质心", 0.25), ("低慢波", 0.20)),
        "creativity": dom(("gamma 相对功率", 0.40), ("样本熵", 0.35), ("Hurst 指数", 0.25)),
        "stability": dom(("慢波占比", 0.45), ("α 峰稳定性", 0.30), ("Hjorth 复杂度", 0.25)),
        "sensory": dom(("theta+gamma", 0.45), ("半球不对称", 0.30), ("样本熵", 0.25)),
    }
    return traits, sources, amplitude


def eeg_confidence(f: EEGFeatures) -> float:
    """信号本身能支撑多少"解读"。质量低、时长短、通道少都会打折。"""
    q = f.quality["score"]
    ch = sig.clip01(f.n_channels / 4.0)
    dur = sig.clip01(f.seconds / 12.0)
    return round(sig.clip01(0.60 * q + 0.20 * ch + 0.20 * dur), 3)


def signal_summary(f: EEGFeatures) -> dict:
    rel = {k: v["rel"] for k, v in f.bands.items()}
    beta_alpha = (rel["beta"] + rel["gamma"] * 0.5) / max(1e-6, rel["alpha"] + 0.02)
    if rel["alpha"] > 0.30 and beta_alpha < 1.2:
        mood = "清明 · 向内"
    elif beta_alpha > 2.2:
        mood = "紧绷 · 向外"
    elif rel["delta"] + rel["theta"] > 0.55:
        mood = "昏沉 · 下沉"
    elif rel["theta"] + rel["gamma"] > 0.30:
        mood = "流动 · 联想"
    else:
        mood = "平稳 · 待机"
    return {
        "dominant": f.dominant,
        "dominant_label": sig.BAND_ZH[f.dominant],
        "mood": mood,
        "alpha": rel["alpha"],
        "beta_alpha": round(beta_alpha, 2),
        "slow": round(rel["delta"] + rel["theta"], 3),
        "peak_hz": f.peak_hz,
        "quality": f.quality["score"],
    }
