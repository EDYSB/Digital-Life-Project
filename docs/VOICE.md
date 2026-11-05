# 语音链路：留给有 GPU 的那一侧

前端的通话页不关心后端是什么。它只说三件事：**我录了一段话**、**给我回复**、**把声音/画面给我**。
下面这条缝，就是为 VoxEMW / LiveTalking / Linly-Talker-Stream 这类后端留的。

## 现状（无后端，纯前端）

| 环节 | 现在是谁在做 | 说明 |
| --- | --- | --- |
| 听 | `SpeechRecognition`（浏览器） | 有网可用；无网就退回打字 |
| 想 | `config.json` 的 DeepSeek key | 空 → 本地规则引擎 |
| 说 | `speechSynthesis` | 零成本，音色一般 |
| 嘴 | canvas 包络 | 音量驱动开合，不是音素级 |

## 接后端时改两行

`config.json`：

```json
{
 "voice_backend": "http://127.0.0.1:8765",
 "voice_ws": "ws://127.0.0.1:8765/stream"
}
```

约定：

1. `POST {voice_backend}/turn`，body `{"id": "...", "text": "..."}` → `{"text": "...", "audio_url": "...", "video_url": "..."}`
2. `{voice_ws}` 推 WebRTC/Opus 轨，或直接推 `video/mp4` 分片
3. 前端拿到 `video_url` 就把 canvas 换成 `<video>`，拿到 `audio_url` 就把 `speechSynthesis` 换掉

## 六块积木的对应关系

| # | VoxEMW | 接到哪 | 备注 |
| --- | --- | --- | --- |
| ① VAD | Silero VAD | 浏览器的录音停止条件，或后端 `/turn` 里做 | 有后端就交给后端，前端只负责收音 |
| ② STT | Qwen3-ASR | `/turn` 内部 | 前端不再发文本，改发音频 |
| ③ LLM | DeepSeek | 已经在用 | 关掉思考模式以压延迟 |
| ④ TTS | VoxCPM2 | `/turn` 返回 `audio_url` | 首包 0.2s 是关键 |
| ⑤ 渲染 | SoulX-FlashHead | `/turn` 返回 `video_url` | 24GB 显存档 |
| ⑥ 推流 | WebRTC | `voice_ws` | 局域网优先 |

## 硬件

- 目标机：单卡 24GB（4090 / 4090D / A6000 级别）
- 本仓的开发机探测结果是 CPU-only（`torch.cuda.is_available() == False`），那只是**当前会话的沙箱环境**，不代表目标机
- 因此本仓代码不写死任何"无 GPU 降级"逻辑：前端始终按"有后端"的形状写，后端空着就退回浏览器能力

## 不做什么

- 不在前端做音素级口型（那需要 viseme 模型）
- 不做 WebRTC 信令（那是后端的事）
- 不把模型权重放进仓库
