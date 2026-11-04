"""EEG 读取：CSV / TXT / TSV / JSON / EDF / EDF+ / NPZ。

所有格式最终归一化为 EEGData：
  channels: list[list[float]]  单位 μV（重采样为 128 Hz，等间隔抽为最多 40 秒）
  channel_names / fs / seconds / source / notes
"""

from __future__ import annotations

import io
import json
import math
import os
import re
import struct
import zipfile
from dataclasses import dataclass, field

from . import signal as sig

TARGET_FS = 128.0
MAX_SECONDS = 40.0
MIN_SECONDS = 2.0


class EEGError(ValueError):
    """输入文件无法被解释为脑电数据。"""


@dataclass
class EEGData:
    channels: list[list[float]]
    channel_names: list[str]
    fs: float
    seconds: float
    source: str = "upload"
    notes: list[str] = field(default_factory=list)
    raw_seconds: float = 0.0
    unit: str = "μV"

    @property
    def n_channels(self) -> int:
        return len(self.channels)

    @property
    def n_samples(self) -> int:
        return len(self.channels[0]) if self.channels else 0


# ---------------------------------------------------------------- 解析工具
def _clean_header(line: str) -> str:
    return re.sub(r"[\ufeff\"']", "", line).strip()


def _split_line(line: str) -> list[str]:
    line = _clean_header(line)
    if not line:
        return []
    for sep in ("\t", ";", "|"):
        if sep in line:
            return [c.strip() for c in line.split(sep)]
    return [c.strip() for c in re.split(r"[,\s]+", line) if c.strip() not in ("",)]


def _is_number(tok: str) -> bool:
    try:
        float(tok)
        return True
    except (TypeError, ValueError):
        return False


def _looks_like_meta(tok: str) -> bool:
    t = tok.strip().lower()
    return t in {"time", "time_s", "timestamp", "t", "秒", "时间", "index", "sample", "n", "#", "ch1"} or t.startswith(
        ("time", "index", "sample", "时间", "序号")
    )


def _numeric_columns(rows: list[list[str]], limit: int = 400) -> int:
    """估算每行中数值列的最小数量，用于判断分隔符是否合理。"""
    counts = []
    for r in rows[:limit]:
        counts.append(sum(1 for c in r if _is_number(c)))
    if not counts:
        return 0
    return min(counts)


def _rows_to_matrix(rows: list[list[str]], has_time: bool, header: list[str] | None) -> tuple[list[list[float]], list[str], int]:
    """返回 (通道×样本, 通道名, 时间列是否有效)。"""
    if not rows:
        raise EEGError("文件里没有可用的数据行。")
    ncol = max(len(r) for r in rows)
    use_time = has_time
    start = 1 if use_time else 0
    n_ch = ncol - start
    if n_ch < 1:
        raise EEGError("没有找到数据列。")
    channels: list[list[float]] = [[] for _ in range(n_ch)]
    for r in rows:
        padded = list(r) + [""] * (ncol - len(r))
        vals = []
        for c in range(start, ncol):
            tok = padded[c].replace("μ", "").strip()
            try:
                vals.append(float(tok))
            except ValueError:
                vals.append(float("nan"))
        if all(math.isnan(v) for v in vals):
            continue
        # 用该通道最近的中位数填补 NaN
        for c, v in enumerate(vals):
            channels[c].append(v)
    names = []
    for c in range(n_ch):
        if header and c + start < len(header):
            nm = header[c + start]
            names.append(nm if nm and not _is_number(nm) else f"CH{c + 1}")
        else:
            names.append(f"CH{c + 1}")
    return channels, names, start


def _fill_nan(channels: list[list[float]]) -> list[list[float]]:
    out = []
    for ch in channels:
        vals = [v for v in ch if not math.isnan(v)]
        fill = sig.median(vals) if vals else 0.0
        out.append([fill if math.isnan(v) else v for v in ch])
    return out


def _parse_delimited(text: str, source: str) -> tuple[EEGData, dict]:
    """自动识别分隔符/表头/时间列，忽略 # 与 // 注释行。"""
    meta: dict = {}
    lines = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("#") or s.startswith("//"):
            for m in re.finditer(r"(\w+)\s*[=:]\s*([\w.+\-]+)", s):
                meta[m.group(1).lower()] = m.group(2)
            continue
        lines.append(s)
    if not lines:
        raise EEGError("文件为空，或只有注释行。")

    # 先检测表头
    header: list[str] | None = None
    body_start = 0
    first = _split_line(lines[0])
    if first and not _is_number(first[0]):
        header = first
        body_start = 1
    elif first and not _is_number(first[0].split(":")[0]):
        # 形如 "time=0.0,1,2" 的松散格式
        header = first
        body_start = 1

    body = [_split_line(l) for l in lines[body_start:]]
    body = [r for r in body if r and any(_is_number(c) for c in r)]
    if len(body) < 8:
        raise EEGError(f"有效数据行太少（{len(body)} 行），至少需要 8 行。")

    # 选列数最稳定的切法
    best = max(body, key=len)
    ncol = len(best)
    rows = []
    for r in body:
        if len(r) >= ncol - 1:
            rows.append(r[:ncol] + [""] * max(0, ncol - len(r)))
    if not rows:
        raise EEGError("无法对齐数据列。")

    has_time = False
    if header:
        has_time = _looks_like_meta(header[0]) or any(k in header[0].lower() for k in ("time", "时间", "index"))
    else:
        first_vals = [float(r[0]) for r in rows[:5] if _is_number(r[0])]
        if len(first_vals) >= 3:
            diffs = [first_vals[i + 1] - first_vals[i] for i in range(len(first_vals) - 1)]
            avg = sum(diffs) / len(diffs)
            # 单调递增且步长远小于 1 → 时间列（秒）
            has_time = all(d > 0 for d in diffs) and 0 < avg <= 0.1
            if has_time:
                meta.setdefault("fs", f"{1 / avg:.3f}")

    channels, names, time_used = _rows_to_matrix(rows, has_time, header)
    channels = _fill_nan(channels)

    fs = None
    for key in ("fs", "sampling_rate", "samplerate", "rate", "hz", "采样率"):
        if key in meta:
            try:
                fs = float(meta[key])
                break
            except ValueError:
                pass
    if fs is None and time_used:
        tcol = [float(r[0]) for r in rows if _is_number(r[0])]
        if len(tcol) > 2:
            diffs = [tcol[i + 1] - tcol[i] for i in range(len(tcol) - 1)]
            positive = [d for d in diffs if d > 0]
            if positive:
                avg = sorted(positive)[len(positive) // 2]
                fs = 1.0 / avg if avg > 0 else None
    if fs is None:
        fs = 256.0
        notes = ["未检测到采样率，按 256 Hz 处理。"]
    else:
        notes = [f"采样率 {fs:g} Hz（{'文件声明' if 'fs' in meta else '由时间列推算'}）。"]
    return EEGData(channels, names, float(fs), len(channels[0]) / float(fs), source=source, notes=notes), meta


# ---------------------------------------------------------------- EDF / EDF+
def _parse_edf(data: bytes, source: str) -> EEGData:
    if len(data) < 256:
        raise EEGError("EDF 文件头不完整。")
    head = data[:256]
    try:
        n_signals = int(head[252:256].decode("ascii").strip() or "0")
        n_records = int(head[236:244].decode("ascii").strip() or "-1")
    except ValueError as exc:
        raise EEGError("EDF 头字段损坏。") from exc
    if not (1 <= n_signals <= 512):
        raise EEGError(f"EDF 通道数异常：{n_signals}")

    def field(offset: int, width: int, idx: int) -> str:
        start = 256 + offset * n_signals + width * idx
        return data[start : start + width].decode("latin-1", errors="replace").strip()

    labels = [field(0, 16, i) for i in range(n_signals)]
    transducers = [field(16, 80, i) for i in range(n_signals)]
    units = [field(96, 8, i) for i in range(n_signals)]
    phys_min = [field(104, 8, i) for i in range(n_signals)]
    phys_max = [field(112, 8, i) for i in range(n_signals)]
    dig_min = [field(120, 8, i) for i in range(n_signals)]
    dig_max = [field(128, 8, i) for i in range(n_signals)]
    ns_per_rec = [field(216, 8, i) for i in range(n_signals)]

    try:
        pmin = [float(v) for v in phys_min]
        pmax = [float(v) for v in phys_max]
        dmin = [float(v) for v in dig_min]
        dmax = [float(v) for v in dig_max]
        samples = [int(float(v)) for v in ns_per_rec]
        rec_dur = float(head[244:252].decode("ascii").strip() or "1")
    except ValueError as exc:
        raise EEGError("EDF 校准字段损坏。") from exc

    offset = 256 + 256 * n_signals
    total_per_rec = sum(samples)
    if total_per_rec <= 0:
        raise EEGError("EDF 每记录采样点为 0。")
    frame_bytes = total_per_rec * 2
    recs = (len(data) - offset) // frame_bytes
    if n_records > 0:
        recs = min(recs, n_records)
    if recs <= 0:
        raise EEGError("EDF 没有可读的数据记录。")

    # 只读前 90 秒，避免超大文件拖慢分析
    max_recs = min(recs, int(90 / max(rec_dur, 1e-6)) or 1)
    parsed = [[] for _ in range(n_signals)]
    pos = offset
    for _ in range(max_recs):
        if pos + frame_bytes > len(data):
            break
        rec = data[pos : pos + frame_bytes]
        p = 0
        for s in range(n_signals):
            ns = samples[s]
            raw = struct.unpack("<" + "h" * ns, rec[p : p + ns * 2])
            p += ns * 2
            span = dmax[s] - dmin[s]
            scale = (pmax[s] - pmin[s]) / span if span else 1.0
            parsed[s].extend(pmin[s] + (v - dmin[s]) * scale for v in raw)
        pos += frame_bytes

    fs = samples[0] / rec_dur if rec_dur else 256.0
    units_clean = []
    for i, u in enumerate(units):
        u = u.strip()
        units_clean.append("μV" if u in {"uV", "µV", "μV", "\xb5V"} else (u or "μV"))

    fs = float(fs or 256.0)
    notes = [f"EDF+ 记录，{n_signals} 导联，{recs} 个数据记录（已读取前 {max_recs} 个）。"]
    return EEGData(
        [list(c) for c in parsed],
        labels,
        fs,
        (len(parsed[0]) / fs) if parsed and fs else 0.0,
        source=source,
        notes=notes,
    )


def _parse_edfplus_annotation(labels: list[str]) -> None:
    """保留占位：EDF+ 的 Annotation 通道在分析阶段会被剔除。"""
    return None


# ---------------------------------------------------------------- 其他格式
def _parse_json(text: str, source: str) -> EEGData:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EEGError(f"JSON 解析失败：{exc.msg}") from exc
    fs = 256.0
    names: list[str] | None = None
    if isinstance(obj, dict):
        fs = float(obj.get("fs") or obj.get("sampling_rate") or obj.get("samplerate") or 256.0)
        names = obj.get("channel_names") or obj.get("channels_names") or obj.get("labels")
        for key in ("channels", "data", "signals", "eeg"):
            v = obj.get(key)
            if isinstance(v, list) and v:
                obj = v
                break
        else:
            raise EEGError("JSON 中没有 channels/data/signals 字段。")
    if not isinstance(obj, list) or not obj:
        raise EEGError("JSON 数据为空。")
    if all(isinstance(x, (int, float)) for x in obj):
        obj = [obj]
    if not all(isinstance(x, list) for x in obj):
        if isinstance(obj[0], dict):
            keys = [k for k in obj[0].keys() if k.lower() not in ("time", "t", "timestamp", "index")]
            obj = [[float(row[k]) for row in obj] for k in keys]
            names = names or keys
        else:
            raise EEGError("JSON 数据不是二维数组。")
    channels = [[float(v) for v in ch] for ch in obj]
    names = names or [f"CH{i + 1}" for i in range(len(channels))]
    return EEGData(channels, list(names), fs, len(channels[0]) / fs, source=source, notes=[f"JSON 数据，采样率 {fs:g} Hz。"])


def _parse_npz(data: bytes, source: str) -> EEGData:
    try:
        import numpy as np  # 可选依赖
    except ImportError as exc:
        raise EEGError("读取 .npz 需要 numpy，请改用 CSV。") from exc
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        arrays = {n[:-4]: zf.read(n) for n in zf.namelist() if n.endswith(".npy")}
    if not arrays:
        raise EEGError(".npz 中没有数组。")
    import pickle  # noqa: S403 只是本地文件的数组头解析
    collected = []
    for name, blob in arrays.items():
        try:
            arr = np.load(io.BytesIO(blob), allow_pickle=False)
        except Exception:  # noqa: BLE001
            continue
        if arr.ndim == 2:
            collected.append((name, arr))
    if not collected:
        raise EEGError(".npz 中没有二维脑电数组。")
    name, arr = max(collected, key=lambda t: t[1].size)
    if arr.shape[0] > arr.shape[1]:
        arr = arr.T
    return EEGData(
        [[float(v) for v in ch] for ch in arr],
        [f"{name}_{i + 1}" for i in range(arr.shape[0])],
        256.0,
        arr.shape[1] / 256.0,
        source=source,
        notes=["从 .npz 读取数组，默认采样率 256 Hz。"],
    )


def _parse_wav(data: bytes, source: str) -> EEGData:
    import wave

    with wave.open(io.BytesIO(data), "rb") as wf:
        n_ch = wf.getnchannels()
        width = wf.getsampwidth()
        fs = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    if width not in (2, 4):
        raise EEGError("WAV 需为 16 或 32 位 PCM。")
    if width == 2:
        vals = struct.unpack("<" + "h" * (len(frames) // 2), frames)
        scale = 1.0
    else:
        vals = struct.unpack("<" + "i" * (len(frames) // 4), frames)
        scale = 1.0 / 65536.0
    chans = [[] for _ in range(n_ch)]
    for i, v in enumerate(vals):
        chans[i % n_ch].append(v * scale)
    return EEGData(chans, [f"CH{i + 1}" for i in range(n_ch)], float(fs), len(chans[0]) / fs, source=source, notes=["WAV PCM 音频作为脑电输入。"])


def _parse_docx(text: str, source: str) -> tuple[EEGData, dict]:
    raise EEGError("暂不支持 .docx。请导出为 CSV，或使用/生成示例脑波。")


# ---------------------------------------------------------------- 预处理与入口
def prepare(eeg: EEGData, notes: list[str] | None = None) -> EEGData:
    """去直流、剔除坏导、重采样到 128 Hz、最多 40 秒。"""
    notes = list(notes or [])
    # 剔除 EDF+ 注释通道与全零/全常数通道
    keep = []
    for i, ch in enumerate(eeg.channels):
        name = (eeg.channel_names[i] if i < len(eeg.channel_names) else "").lower()
        if "annotation" in name or name in ("status", "marker"):
            continue
        vals = [v for v in ch if not math.isnan(v)]
        if len(vals) < 8:
            continue
        if sig.stdev(vals) < 1e-9:
            notes.append(f"导联 {name or i + 1} 为常数，已剔除。")
            continue
        keep.append(i)
    if not keep:
        raise EEGError("所有导联都是常数或空白。")
    channels = []
    names = []
    for i in keep:
        ch = [v if not math.isnan(v) else 0.0 for v in eeg.channels[i]]
        mu = sig.mean(ch)
        ch = sig.detrend([v - mu for v in ch])
        channels.append(ch)
        names.append(eeg.channel_names[i] if i < len(eeg.channel_names) else f"CH{i + 1}")

    fs = eeg.fs
    if not (20.0 <= fs <= 4000.0):
        raise EEGError(f"采样率 {fs:g} Hz 不合理。")
    if fs != TARGET_FS:
        channels = [sig.resample_linear(ch, fs, TARGET_FS) for ch in channels]
        notes.append(f"重采样 {fs:g} Hz → {TARGET_FS:g} Hz。")
        fs = TARGET_FS

    n = len(channels[0])
    max_n = int(MAX_SECONDS * fs)
    if n > max_n:
        # 取中段 40 秒，避开开头结尾的接电极瞬态
        start = max(0, (n - max_n) // 2)
        channels = [ch[start : start + max_n] for ch in channels]
        notes.append(f"原长 {eeg.seconds:.1f}s，截取中段 {MAX_SECONDS:g}s 分析。")
        n = max_n
    if n < int(MIN_SECONDS * fs):
        raise EEGError(f"有效数据仅 {n / fs:.1f} 秒，至少需要 {MIN_SECONDS:.0f} 秒。")

    return EEGData(
        channels,
        names,
        fs,
        n / fs,
        source=eeg.source,
        notes=notes,
        raw_seconds=eeg.seconds or n / fs,
        unit=eeg.unit,
    )


def load_bytes(data: bytes, filename: str) -> EEEData:  # type: ignore[valid-type]
    raise EEGError("内部错误：请使用 parse_bytes。")


def parse_bytes(data: bytes, filename: str = "upload.csv") -> EEGData:
    if not data:
        raise EEGError("文件为空。")
    ext = os.path.splitext(filename.lower())[1]
    source = filename
    if ext in (".edf", ".bdf") or data[:8].lstrip(b"\xef\xbb\xbf").startswith(b"0       "):
        if ext == ".bdf":
            raise EEGError("暂不支持 BDF（24 位）格式，请转换为 EDF 或 CSV。")
        eeg = _parse_edf(data, source)
        return prepare(eeg)
    if ext == ".json":
        eeg = _parse_json(data.decode("utf-8-sig", errors="replace"), source)
        return prepare(eeg)
    if ext == ".npz":
        eeg = _parse_npz(data, source)
        return prepare(eeg)
    if ext == ".wav":
        eeg = _parse_wav(data, source)
        return prepare(eeg)
    if ext == ".docx":
        raise _parse_docx("", source)
    if ext in (".csv", ".tsv", ".txt", ".dat", ".asc", ".tsv".upper()):
        text = data.decode("utf-8-sig", errors="replace")
        eeg, meta = _parse_delimited(text, source)
        return prepare(eeg)
    # 未知扩展名：先按文本尝试
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise EEGError(f"无法识别的文件格式 {ext or '(无扩展名)'}。请上传 CSV/TSV/JSON/EDF。") from exc
    eeg, meta = _parse_delimited(text, source)
    return prepare(eeg)


def load_path(path: str) -> EEGData:
    with open(path, "rb") as f:
        return parse_bytes(f.read(), os.path.basename(path))


EEGDataAlias = EEGData
