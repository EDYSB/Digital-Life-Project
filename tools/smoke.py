"""最终冒烟：静态资源、状态、错误处理、扫描、对话、对比、删除保护。"""

import json
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:8017"


def multipart(fields):
    b = "----smoke" + uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        if isinstance(v, tuple):
            name, data = v
            out.append(("--%s\r\n" % b).encode())
            out.append(('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (k, name)).encode())
            out.append(b"Content-Type: application/octet-stream\r\n\r\n" + data + b"\r\n")
        else:
            out.append(("--%s\r\n" % b).encode())
            out.append(('Content-Disposition: form-data; name="%s"\r\n\r\n' % k).encode() + str(v).encode() + b"\r\n")
    out.append(("--%s--\r\n" % b).encode())
    return b"".join(out), "multipart/form-data; boundary=" + b


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return r.status, r.read()


def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read())


ok = True


def check(name, cond, detail=""):
    global ok
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else " :: " + str(detail)))
    if not cond:
        ok = False


st, body = get("/api/status")
j = json.loads(body)
check("status 200", st == 200)
check("3 份示例档案", len(j["minds"]) == 3, len(j["minds"]))
check("8 份样本", len(j["samples"]) == 8, len(j["samples"]))
check("4 种声音", len(j["voices"]) == 4)
check("12 个原型", len(j["archetypes"]) == 12)

for path in ("/", "/style.css", "/app.js"):
    st, body = get(path)
    check("static %s" % path, st == 200 and len(body) > 1000, "%s %s" % (st, len(body)))

st, body = get("/api/minds/mind_cbbf2c764732")
p = json.loads(body)["profile"]
check("读取档案", st == 200 and p["persona"]["name"])
check("档案含 7 维", len(p["traits"]) == 7)

# 错误处理：空文件
body, ct = multipart({"eeg": ("bad.csv", b"a,b\n1,2\n"), "dna": ("bad.fasta", b"ACGT")})
req = urllib.request.Request(BASE + "/api/scan", data=body, headers={"Content-Type": ct})
try:
    urllib.request.urlopen(req, timeout=30)
    check("坏文件应报错", False, "没有报错")
except urllib.error.HTTPError as e:
    msg = json.loads(e.read()).get("error", "")
    check("坏文件返回 400", e.code == 400 and bool(msg), "%s %s" % (e.code, msg))

# 扫描
with open("samples/eeg_meditation.csv", "rb") as f:
    eeg = f.read()
with open("samples/dna_balanced.txt", "rb") as f:
    dna = f.read()
body, ct = multipart({"eeg": ("eeg_meditation.csv", eeg), "dna": ("dna_balanced.txt", dna),
                      "subject": "冒烟", "voice": "neutral"})
req = urllib.request.Request(BASE + "/api/scan", data=body, headers={"Content-Type": ct})
with urllib.request.urlopen(req, timeout=120) as r:
    prof = json.loads(r.read())["profile"]
check("扫描成功", prof["id"].startswith("mind_"))
check("声音为素面", prof["persona"]["voice_label"] == "素面", prof["persona"]["voice_label"])

# 对话
st, c1 = post("/api/chat", {"id": prof["id"], "profile": prof, "message": "你是谁？", "history": []})
check("对话 1", st == 200 and c1["intent"] == "identity")
st, c2 = post("/api/chat", {"id": prof["id"], "profile": prof, "message": "我睡不着", "history": []})
check("对话 2（睡眠）", c2["intent"] == "sleep", c2["intent"])
st, c3 = post("/api/chat", {"id": prof["id"], "profile": prof, "message": "你觉得自由是什么？", "history": []})
check("对话 3（开放问题有回应）", len(c3["text"]) > 8)

# 对比
items = json.loads(get("/api/minds")[1])["items"]
st, cmp = post("/api/compare", {"a": items[0]["id"], "b": items[1]["id"]})
check("对比", st == 200 and 0 <= cmp["result"]["resonance"] <= 100)

# 删除不存在的档案
st, d = post("/api/delete", {"id": "mind_deadbeef0000"})
check("删除不存在档案不报错", st == 200 and d["ok"])

print("\nSMOKE", "PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
