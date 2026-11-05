"""数字生命初级 本地服务器（纯标准库）。

启动：
  python -m suoling.server --port 8017
或：
  python app.py
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, admin, agency, archive, card, dialogue, eeg as eeg_mod, genome as genome_mod, life, llm, memory, pipeline, signal as sig, world

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, "web")
SAMPLE_DIR = os.path.join(ROOT, "samples")
MAX_UPLOAD = 32 * 1024 * 1024

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}

_cache: dict[str, dict] = {}
LIFE = life.LifeLoop()
_cache_lock = threading.Lock()


def _remember(profile: dict) -> None:
    with _cache_lock:
        _cache[profile["id"]] = profile
        if len(_cache) > 40:
            for k in list(_cache)[:-25]:
                _cache.pop(k, None)


def _get(mind_id: str) -> dict | None:
    with _cache_lock:
        if mind_id in _cache:
            return _cache[mind_id]
    try:
        p = pipeline.load(mind_id)
        _remember(p)
        return p
    except pipeline.PipelineError:
        return None


# ---------------------------------------------------------------- multipart
def parse_multipart(body: bytes, content_type: str) -> dict[str, list[dict]]:
    """极简 multipart/form-data 解析。返回 {field: [{filename, content}]}。"""
    if "boundary=" not in content_type:
        raise ValueError("缺少 boundary")
    boundary = content_type.split("boundary=", 1)[1].strip().strip('"')
    delim = b"--" + boundary.encode()
    parts = body.split(delim)
    out: dict[str, list[dict]] = {}
    for part in parts:
        if not part or part in (b"--\r\n", b"--"):
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        if b"\r\n\r\n" not in part:
            continue
        raw_head, content = part.split(b"\r\n\r\n", 1)
        if content.endswith(b"\r\n"):
            content = content[:-2]
        headers = {}
        for line in raw_head.decode("latin-1", "replace").split("\r\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        disp = headers.get("content-disposition", "")
        name_m = __import__("re").search(r'name="([^"]*)"', disp)
        file_m = __import__("re").search(r'filename="([^"]*)"', disp)
        name = name_m.group(1) if name_m else ""
        entry = {"filename": file_m.group(1) if file_m else "", "content": content}
        out.setdefault(name, []).append(entry)
    return out


def _first(fields: dict, name: str) -> tuple[str, bytes]:
    items = fields.get(name) or []
    if not items:
        return "", b""
    return items[0].get("filename", ""), items[0].get("content", b"")


# ---------------------------------------------------------------- handler
class Handler(BaseHTTPRequestHandler):
    server_version = "DigitalLife/" + __version__
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: A003
        if os.environ.get("ECHOMIND_QUIET"):
            return
        print("[%s] %s" % (time.strftime("%H:%M:%S"), fmt % args))

    # -------- helpers
    def _send_json(self, obj, status=HTTPStatus.OK):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, status, message, extra=None):
        body = {"ok": False, "error": message}
        if extra:
            body.update(extra)
        self._send_json(body, status)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            raise ValueError("文件太大（上限 32 MB）。")
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _sse_start(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _sse(self, event: str, data) -> None:
        payload = "event: %s\ndata: %s\n\n" % (event, json.dumps(data, ensure_ascii=False))
        self.wfile.write(payload.encode("utf-8"))
        self.wfile.flush()

    # -------- routes
    def do_OPTIONS(self):  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        try:
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/status":
                return self._send_json({
                    "ok": True, "version": __version__,
                    "samples": self._samples(),
                    "presets": [{"key": p.key, "name": p.name, "subtitle": p.subtitle, "desc": p.desc}
                                for p in sig.SYNTH_PRESETS],
                    "genome_presets": [
                        {"key": k, "label": v["label"], "desc": v["desc"]}
                        for k, v in genome_mod.DEMO_GENOME_PRESETS.items()
                    ],
                    "voices": [{"key": k, "label": v["label"], "desc": v["desc"]}
                               for k, v in __import__("suoling.persona", fromlist=["x"]).VOICE_STYLE.items()],
                    "archetypes": __import__("suoling.persona", fromlist=["x"]).archetype_table(),
                    "minds": pipeline.list_minds(),
                    "sim": LIFE.status(),
                    "capabilities": {
                        "eeg_formats": ["csv", "tsv", "txt", "json", "edf", "npz", "wav"],
                        "dna_formats": ["fasta", "23andme/raw", "vcf", "json", "pure-sequence"],
                        "max_upload_mb": 32,
                    },
                    "disclaimer": "本系统不实现真实的意识复制。它把脑电与基因数据投影为一个可对话的模拟人格。",
                })
            if path == "/api/sim":
                return self._send_json({"ok": True, **LIFE.status()})
            if path == "/api/world":
                mid = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id", [""])[0]
                profile = _get(mid)
                if not profile:
                    return self._send_error(HTTPStatus.NOT_FOUND, "没有找到这份档案。")
                return self._send_json({"ok": True, "world": world.evaluate(profile)})
            if path == "/api/admin":
                ids = [m["id"] for m in pipeline.list_minds()]
                profiles = [p for p in (_get(i) for i in ids) if p]
                out = admin.overview(profiles)
                out["sim"] = LIFE.status()
                return self._send_json(out)
            if path == "/api/minds":
                return self._send_json({"ok": True, "items": pipeline.list_minds()})
            if path.startswith("/api/minds/"):
                mid = path.rsplit("/", 1)[-1]
                p = _get(mid)
                if not p:
                    return self._send_error(HTTPStatus.NOT_FOUND, "没有找到这份档案。")
                return self._send_json({"ok": True, "profile": p})
            if path == "/api/samples":
                return self._send_json({"ok": True, "samples": self._samples()})
            if path.startswith("/api/sample/"):
                name = urllib.parse.unquote(path.rsplit("/", 1)[-1])
                return self._serve_file(os.path.join(SAMPLE_DIR, os.path.basename(name)), download=name)
            if path == "/api/brain":
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                mid = (qs.get("id") or [""])[0]
                prof = _get(mid) if mid else None
                if prof is None:
                    items = pipeline.list_minds()
                    prof = _get(items[0]["id"]) if items else None
                if prof is None:
                    return self._send_error(HTTPStatus.NOT_FOUND, "还没有档案。")
                from . import brain as brain_mod

                return self._send_json(brain_mod.snapshot(prof))
            return self._serve_static(path)
        except BrokenPipeError:
            return
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "服务器内部错误。")

    def do_POST(self):  # noqa: N802
        try:
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/scan":
                return self._scan(stream=False)
            if path == "/api/scan/stream":
                return self._scan(stream=True)
            if path == "/api/chat":
                return self._chat()
            if path == "/api/session":
                return self._session()
            if path == "/api/compare":
                body = json.loads(self._read_body() or b"{}")
                a = _get(str(body.get("a", "")))
                b = _get(str(body.get("b", "")))
                if not a or not b:
                    return self._send_error(HTTPStatus.NOT_FOUND, "对比需要两份已保存的档案。")
                return self._send_json({"ok": True, "result": pipeline.compare(a, b)})
            if path == "/api/save":
                body = json.loads(self._read_body() or b"{}")
                p = _get(str(body.get("id", "")))
                if not p:
                    return self._send_error(HTTPStatus.NOT_FOUND, "没有找到这份档案。")
                path_out = pipeline.save(p)
                return self._send_json({"ok": True, "path": path_out, "id": p["id"]})
            if path == "/api/export":
                body = json.loads(self._read_body() or b"{}")
                p = _get(str(body.get("id", "")))
                if not p:
                    return self._send_error(HTTPStatus.NOT_FOUND, "没有找到这份档案。")
                fmt = body.get("format", "md")
                if fmt == "md":
                    data = pipeline.export_markdown(p).encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/markdown; charset=utf-8")
                    fname = urllib.parse.quote((p["persona"]["name"] or "mind") + ".md")
                    self.send_header("Content-Disposition",
                                     "attachment; filename=\"mind.md\"; filename*=UTF-8''" + fname)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                return self._send_json({"ok": True, "profile": p})
            if path == "/api/inner":
                body = json.loads(self._read_body() or b"{}")
                profile = _get(str(body.get("id", "")))
                if not profile:
                    return self._send_error(HTTPStatus.NOT_FOUND, "没有找到这份档案。")
                agency.ensure(profile, {t["key"]: t["value"] for t in profile.get("traits", [])})
                agency.tick(profile)
                pipeline.save(profile)
                return self._send_json({"ok": True, "inner": agency.inner(profile)})
            if path == "/api/proactive":
                body = json.loads(self._read_body() or b"{}")
                profile = _get(str(body.get("id", "")))
                if not profile:
                    return self._send_error(HTTPStatus.NOT_FOUND, "没有找到这份档案。")
                agency.ensure(profile, {t["key"]: t["value"] for t in profile.get("traits", [])})
                agency.tick(profile)
                action = str(body.get("action", "check"))
                p = agency.pending(profile)
                if action == "deliver" and p:
                    agency.deliver(profile)
                pipeline.save(profile)
                return self._send_json({"ok": True, "pending": p, "inner": agency.inner(profile)})
            if path == "/api/world/budget":
                body = json.loads(self._read_body() or b"{}")
                profile = _get(str(body.get("id", "")))
                if not profile:
                    return self._send_error(HTTPStatus.NOT_FOUND, "没有找到这份档案。")
                w = world.set_budget(profile, float(body.get("budget", 6)))
                pipeline.save(profile)
                return self._send_json({"ok": True, "world": w})
            if path == "/api/autonomy":
                body = json.loads(self._read_body() or b"{}")
                profile = _get(str(body.get("id", "")))
                if not profile:
                    return self._send_error(HTTPStatus.NOT_FOUND, "没有找到这份档案。")
                res = agency.set_autonomy(profile, str(body.get("level", "balanced")))
                pipeline.save(profile)
                return self._send_json({"ok": True, "autonomy": res})
            if path == "/api/card":
                body = json.loads(self._read_body() or b"{}")
                profile = _get(str(body.get("id", "")))
                if not profile:
                    return self._send_error(HTTPStatus.NOT_FOUND, "没有找到这份档案。")
                data = card.build(profile).encode("utf-8")
                name = urllib.parse.quote(((profile.get("persona") or {}).get("code") or "DL") + "-card.html")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Disposition", "attachment; filename=\"card.html\"; filename*=UTF-8''" + name)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if path == "/api/archive":
                body = json.loads(self._read_body() or b"{}")
                profile = _get(str(body.get("id", "")))
                if not profile:
                    return self._send_error(HTTPStatus.NOT_FOUND, "没有找到这份档案。")
                data = archive.build(profile).encode("utf-8")
                name = urllib.parse.quote((profile["persona"]["name"] or "memory") + "-记忆档案.html")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Disposition", "attachment; filename=\"memory.html\"; filename*=UTF-8''" + name)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if path == "/api/reinforce":
                body = json.loads(self._read_body() or b"{}")
                mid = str(body.get("id", ""))
                memory_id = str(body.get("memory_id", ""))
                profile = _get(mid)
                if not profile:
                    return self._send_error(HTTPStatus.NOT_FOUND, "没有找到这份档案。")
                memory.reinforce(profile, [memory_id])
                pipeline.save(profile)
                mem = next((m for m in (profile.get("mind") or {}).get("memories", [])
                            if m.get("id") == memory_id), None)
                if not mem:
                    return self._send_error(HTTPStatus.NOT_FOUND, "没有找到这条记忆。")
                return self._send_json({"ok": True, "memory": mem})
            if path == "/api/delete":
                body = json.loads(self._read_body() or b"{}")
                mid = str(body.get("id", ""))
                with _cache_lock:
                    _cache.pop(mid, None)
                fp = os.path.join(pipeline.mind_dir(), mid + ".mind")
                if os.path.exists(fp):
                    os.remove(fp)
                return self._send_json({"ok": True})
            return self._send_error(HTTPStatus.NOT_FOUND, "未知接口。")
        except BrokenPipeError:
            return
        except (eeg_mod.EEGError, genome_mod.DNAError, pipeline.PipelineError) as exc:
            return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
        except ValueError as exc:
            return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "处理失败，请查看服务器日志。")

    # -------- implementations
    def _scan(self, stream: bool):
        ctype = self.headers.get("Content-Type", "")
        body = self._read_body()
        fields = parse_multipart(body, ctype)
        eeg_name, eeg_bytes = _first(fields, "eeg")
        dna_name, dna_bytes = _first(fields, "dna")
        subject = _first(fields, "subject")[1].decode("utf-8", "replace")[:24]
        voice = _first(fields, "voice")[1].decode("utf-8", "replace") or "calm"
        voice_sample = None
        voice_raw = _first(fields, "voice")[1]
        if voice_raw:
            try:
                voice_sample = json.loads(voice_raw.decode("utf-8", "replace"))
            except (ValueError, UnicodeDecodeError):
                voice_sample = None
            if voice_sample is not None:
                clip = str(voice_sample.get("clip") or "")
                if clip and (not clip.startswith("data:audio/") or len(clip) > 2_600_000):
                    return self._send_error(HTTPStatus.BAD_REQUEST, "声音样本格式不正确或过大。")

        avatar = None
        avatar_raw = _first(fields, "avatar")[1]
        if avatar_raw:
            try:
                avatar = json.loads(avatar_raw.decode("utf-8", "replace"))
            except (ValueError, UnicodeDecodeError):
                avatar = None
            if avatar is not None:
                views = avatar.get("views") or []
                sprite = str(avatar.get("sprite") or "")
                if sprite and (not sprite.startswith("data:image/") or len(sprite) > 4_000_000):
                    return self._send_error(HTTPStatus.BAD_REQUEST, "立绘格式不正确或过大。")
                if (not isinstance(views, list) or len(views) > 6) and not sprite:
                    return self._send_error(HTTPStatus.BAD_REQUEST, "面孔数据格式不正确（最多 6 个视角）。")
                total = sum(len(str(v.get("photo", ""))) for v in views if isinstance(v, dict))
                if total > 4_000_000:
                    return self._send_error(HTTPStatus.BAD_REQUEST, "面孔图片太大，请降低分辨率。")
                for v in (views if isinstance(views, list) else []):
                    if not isinstance(v, dict) or not str(v.get("photo", "")).startswith("data:image/"):
                        return self._send_error(HTTPStatus.BAD_REQUEST, "面孔图片必须是 data:image/... 格式。")

        if not eeg_bytes:
            return self._send_error(HTTPStatus.BAD_REQUEST, "缺少脑电文件。")
        if not dna_bytes:
            return self._send_error(HTTPStatus.BAD_REQUEST, "缺少基因文件。")
        if len(eeg_bytes) > MAX_UPLOAD or len(dna_bytes) > MAX_UPLOAD:
            return self._send_error(HTTPStatus.BAD_REQUEST, "文件过大（单文件上限 32 MB）。")

        if stream:
            self._sse_start()
            self._sse("meta", {"stage": "start", "message": "开始双通道录入"})
        events: list[tuple[str, dict]] = []

        def progress(stage, pct, message, track):
            ev = (stage, {"stage": stage, "pct": pct, "message": message, "track": track})
            if stream:
                try:
                    self._sse(*ev)
                except BrokenPipeError:
                    pass
            events.append(ev)

        try:
            eeg = eeg_mod.parse_bytes(eeg_bytes, eeg_name or "upload.csv")
            dna = genome_mod.parse_bytes(dna_bytes, dna_name or "upload.fasta")
            profile = pipeline.build(eeg, dna, subject=subject, voice=voice, progress=progress,
                                     avatar=avatar, voice_sample=voice_sample)
            pipeline.save(profile)
            _remember(profile)
        except (eeg_mod.EEGError, genome_mod.DNAError, pipeline.PipelineError, ValueError) as exc:
            if stream:
                self._sse("failed", {"stage": "error", "message": str(exc)})
                self.close_connection = True
                return
            return self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

        if stream:
            self._sse("done", {"stage": "done", "pct": 100, "profile": profile})
            self.close_connection = True
            return
        self._send_json({"ok": True, "profile": profile})

    def _session(self):
        body = json.loads(self._read_body() or b"{}")
        mid = str(body.get("id", ""))
        profile = _get(mid) if mid else None
        if not profile:
            return self._send_error(HTTPStatus.NOT_FOUND, "没有找到这份档案。")
        memory.ensure(profile, {t["key"]: t["value"] for t in profile.get("traits", [])})
        memory.ensure(profile, {t["key"]: t["value"] for t in profile.get("traits", [])})
        agency.ensure(profile, {t["key"]: t["value"] for t in profile.get("traits", [])})
        agency.tick(profile)
        info = memory.start_session(profile)
        per = profile.get("persona", {})
        days = info.get("since_last") or 0
        mo = info.get("mood") or {}
        opening = per.get("greeting") or "我在。"
        if days >= 1:
            opening = "我们有 %.0f 天没说话了。%s" % (days, opening)
        elif info.get("sessions", 0) > 1:
            opening = "又见面了。" + opening

        profile.setdefault("mind", {})["mood"]["updated"] = profile["mind"]["mood"].get("updated")
        pipeline.save(profile)
        self._send_json({
            "ok": True,
            "opening": opening,
            "session": info,
            "mood": mo,
            "memory": memory.summary(profile),
            "inner": agency.inner(profile),
            "world": world.evaluate(profile),
            "pending": agency.pending(profile),
            "since_last": days,
        })

    def _chat(self):
        try:
            body = json.loads(self._read_body() or b"{}")
        except json.JSONDecodeError:
            return self._send_error(HTTPStatus.BAD_REQUEST, "请求不是合法 JSON。")
        mid = str(body.get("id", ""))
        profile = _get(mid) if mid else None
        posted = body.get("profile")
        if not profile and isinstance(posted, dict) and "persona" in posted:
            profile = posted
        if not profile:
            return self._send_error(HTTPStatus.BAD_REQUEST, "缺少人格档案。")
        message = str(body.get("message", ""))[:600]
        history = body.get("history") or []
        if not isinstance(history, list):
            history = []
        memory.ensure(profile, {t["key"]: t["value"] for t in profile.get("traits", [])})
        memory.decay(profile)
        ctx = memory.recall_context(profile, message)
        world_state = world.evaluate(profile)
        try:
            from . import brain as brain_mod
            thought = brain_mod.pulse(profile, message, recall=bool(ctx.get("recalled")))
        except Exception:
            thought = ""
        result = None
        if world_state.get("state") != "protective" and llm.enabled():
            text = llm.reply(profile, message, ctx.get("recalled", []), ctx.get("mood", {}), world_state)
            if text:
                result = {
                    "text": text, "intent": "llm", "intent_zh": "本地模型",
                    "emotion": {"arousal": (ctx.get("mood") or {}).get("arousal", 0.5),
                                "valence": (ctx.get("mood") or {}).get("valence", 0.5),
                                "label": (ctx.get("mood") or {}).get("label", "")},
                    "followup": "", "voice": (profile.get("persona") or {}).get("voice", "calm"),
                    "memory": None, "world": world_state,
                    "disclaimer": "本地模型生成，仍是模拟。",
                }
        if result is None:
            result = dialogue.reply(profile, message, history[-12:], mem_ctx=ctx)
        obs = memory.observe(profile, message, result.get("text", ""), result.get("intent", ""))
        agency.ensure(profile, {t["key"]: t["value"] for t in profile.get("traits", [])})
        agency.satisfy(profile, result.get("intent", ""), message)
        if ctx.get("recalled"):
            memory.reinforce(profile, [m["id"] for m in ctx["recalled"]])
        stats = (profile.get("mind") or {}).get("stats", {})
        n = int(stats.get("messages", 0))
        level = 0 if n < 4 else 1 if n < 8 else 2 if n < 14 else 3
        labels = ["初次接通", "逐渐同步", "稳定共鸣", "深度绑定"]
        rel = {"level": level, "label": labels[level], "messages": n}
        profile["relationship"] = rel
        result["relationship"] = rel
        result["recalled"] = ctx.get("recalled", [])
        result["learned"] = obs.get("learned", [])
        result["mood"] = obs.get("mood") or ctx.get("mood")
        result["memory_stats"] = memory.summary(profile)
        result["inner"] = agency.inner(profile)
        result["world"] = world.evaluate(profile)
        if mid:
            profile["id"] = mid
            pipeline.save(profile)
        self._send_json({"ok": True, **result})

    def _samples(self) -> list[dict]:
        out = []
        if not os.path.isdir(SAMPLE_DIR):
            return out
        desc = {
            "eeg_meditation": "闭眼静息 · α 波主导的合成脑电",
            "eeg_focus": "深度专注 · β 波主导的合成脑电",
            "eeg_flow": "心流创作 · θ/γ 混合的合成脑电",
            "eeg_fatigue": "疲惫深夜 · 慢波抬头的合成脑电",
            "dna_sensitive": "高敏型 · COMT 慢清除的演示面板",
            "dna_explorer": "探索型 · 高多巴胺的演示面板",
            "dna_steady": "稳态型 · 慢节奏的演示面板",
            "dna_balanced": "均衡型 · 全参考纯合面板",
        }
        order = {
            "eeg_meditation": 0, "eeg_focus": 1, "eeg_flow": 2, "eeg_fatigue": 3,
            "dna_sensitive": 10, "dna_explorer": 11, "dna_steady": 12, "dna_balanced": 13,
        }
        names = [n for n in sorted(os.listdir(SAMPLE_DIR))
                 if n.lower().endswith((".csv", ".fasta", ".fa", ".txt", ".vcf"))]
        names.sort(key=lambda n: order.get(os.path.splitext(n)[0], 99))
        for name in names:
            key = os.path.splitext(name)[0]
            out.append({
                "name": name,
                "key": key,
                "label": desc.get(key, name),
                "kind": "eeg" if name.startswith("eeg") else "dna",
                "size_kb": round(os.path.getsize(os.path.join(SAMPLE_DIR, name)) / 1024, 1),
            })
        return out

    def _serve_static(self, path: str):
        if path in ("/", ""):
            path = "/index.html"
        rel = os.path.normpath(path.lstrip("/"))
        if rel.startswith("..") or os.path.isabs(rel):
            return self._send_error(HTTPStatus.FORBIDDEN, "禁止访问。")
        fp = os.path.join(WEB_DIR, rel)
        if not os.path.isfile(fp):
            fp = os.path.join(WEB_DIR, "index.html")
            if not os.path.isfile(fp):
                return self._send_error(HTTPStatus.NOT_FOUND, "前端尚未构建。")
        return self._serve_file(fp, download=None)

    def _serve_file(self, fp: str, download: str | None):
        if not os.path.isfile(fp):
            return self._send_error(HTTPStatus.NOT_FOUND, "文件不存在。")
        ext = os.path.splitext(fp)[1].lower()
        ctype = STATIC_TYPES.get(ext) or mimetypes.guess_type(fp)[0] or "application/octet-stream"
        with open(fp, "rb") as f:
            data = f.read()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache" if ext in (".html", ".js", ".css") else "max-age=3600")
        if download:
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(download))
        self.end_headers()
        self.wfile.write(data)


def serve(host: str = "127.0.0.1", port: int = 8017, open_browser: bool = True) -> None:
    os.makedirs(pipeline.mind_dir(), exist_ok=True)
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = "http://%s:%d" % (host, port)
    print("")
    print("  数字生命初级  ·  数字生命录入系统")
    print("  " + "-" * 44)
    print("  地址：%s" % url)
    print("  档案目录：%s" % pipeline.mind_dir())
    print("  Ctrl+C 停止")
    print("")
    LIFE.start()
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()


def main() -> None:
    ap = argparse.ArgumentParser(description="数字生命初级 本地服务器")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("ECHOMIND_PORT", "8017")))
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    serve(args.host, args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
