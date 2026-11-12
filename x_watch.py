#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
x-direct-cn — 国内直连 / 免费 / 零 Key 的 X(推特) 关注动态第一时间提醒

数据源: https://api.fxtwitter.com/2/profile/{handle}/statuses   (国内直连实测 200)
        ?since=<unix秒> 无新推返回 204，有新推返回时间线 JSON
推送端: 飞书 / 钉钉 / Server酱 / Bark / 企业微信 / Windows 桌面气泡(零配置兜底)

用法:
    python x_watch.py                 # 常驻监控
    python x_watch.py --once          # 只跑一轮（测试用）
    python x_watch.py --test          # 发一条测试推送
    python x_watch.py --add sama      # 追加关注账号
    python x_watch.py --list          # 列出当前关注
    python x_watch.py --reset         # 清空状态，重新建立基线（不推历史）
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG_FILE = BASE / "config.json"
STATE_FILE = BASE / "state.json"
LOG_FILE = BASE / "watch.log"
API = "https://api.fxtwitter.com/2/profile/{}/statuses"

DEFAULT_CONFIG = {
    # 关注的账号，直接改这里，或用 --add 追加
    "watch": [
        "sama", "OpenAI", "OpenAIDevs", "ChatGPT", "gdb",
        "OfficialLoganK", "GeminiApp", "GoogleDeepMind",
        "demishassabis", "GoogleAIStudio", "GoogleAI"
    ],
    "interval": 60,          # 轮询秒数，60s 即"第一时间"
    "workers": 4,            # 并发数：实测 4 并发 + 5 次短重试 = 11/11 全成功，一轮约 33s
    "retries": 5,            # 短超时(5s)下的快速重试次数；链路丢包时靠重试补齐
    "replies": False,        # True = 连回复也提醒
    "retweets": True,        # False = 忽略纯转推
    "notify": {
        # 全部留空也能用：自动走 Windows 桌面气泡通知
        "feishu_webhook": "",        # https://open.feishu.cn/open-apis/bot/v2/hook/xxxx
        "dingtalk_webhook": "",      # https://oapi.dingtalk.com/robot/send?access_token=xxxx
        "dingtalk_secret": "",       # 可选，加签密钥 SECxxxx
        "serverchan_key": "",        # Server酱³ sctapi.ftqq.com 的 SendKey
        "bark_url": "",              # https://api.day.app/你的Key
        "wecom_webhook": "",         # https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx
        "desktop": True              # 无其他渠道时启用 Windows 气泡
    }
}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"


def log(msg: str):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("gbk", "replace").decode("gbk"), flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_json(path: Path, default):
    if not path.exists():
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        return json.loads(json.dumps(default))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log(f"读取 {path.name} 失败({e})，使用默认值")
        return json.loads(json.dumps(default))


def save_json(path: Path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def http(url: str, data=None, timeout=15, headers=None):
    hd = {"User-Agent": UA, "Accept": "application/json,application/xml,*/*"}
    if headers:
        hd.update(headers)
    body = None
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        hd["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=hd)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def fetch_statuses(handle: str, since: int = 0):
    """返回 (是否有更新, 推文列表)。204 / 空体 = 无新推。"""
    url = API.format(urllib.parse.quote(handle, safe=""))
    if since:
        url += f"?since={since}"
    try:
        code, raw = http(url, timeout=5)
    except urllib.error.HTTPError as e:
        if e.code == 204:
            return False, []
        raise
    if code == 204 or not raw:
        return False, []
    payload = json.loads(raw.decode("utf-8", "replace"))
    # 注意：上游 results 并非严格按时间倒序，后续代码用 max 取最新时间戳
    items = [x for x in payload.get("results", []) if x.get("type") == "status"]
    return True, items


def fetch_profile(handle: str):
    """404 账号的降级哨兵：只取 statuses 计数，感知"有没有发新动态"。"""
    url = f"https://api.fxtwitter.com/{urllib.parse.quote(handle, safe='')}"
    code, raw = http(url, timeout=5)
    u = json.loads(raw.decode("utf-8", "replace")).get("user", {})
    return {"statuses": int(u.get("tweets") or u.get("statuses") or 0),
            "name": u.get("name", ""), "handle": u.get("screen_name", handle)}


def to_ts(item) -> int:
    v = item.get("created_timestamp")
    if isinstance(v, (int, float)) and v:
        return int(v / 1000) if v > 1e11 else int(v)
    s = item.get("created_at", "")
    try:
        return int(datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y").timestamp())
    except (ValueError, TypeError):
        return 0


def normalize(item) -> dict:
    author = item.get("author", {}) or {}
    return {
        "id": str(item.get("id", "")),
        "url": item.get("url") or f"https://x.com/{author.get('screen_name','')}/status/{item.get('id','')}",
        "handle": author.get("screen_name", ""),
        "name": author.get("name", ""),
        "text": (item.get("text") or "").strip(),
        "ts": to_ts(item),
        "replies": item.get("replies", 0),
        "reposts": item.get("reposts", 0),
        "likes": item.get("likes", 0),
        "replying_to": item.get("replying_to"),
        "reposted_by": item.get("reposted_by"),
    }


def should_notify(t: dict, cfg: dict, seen: set) -> bool:
    if not t["id"] or t["id"] in seen:
        return False
    if not cfg.get("replies") and (t["replying_to"] or t["text"].startswith("@")):
        return False
    if not cfg.get("retweets") and t["reposted_by"]:
        return False
    return True


# ---------------- 推送渠道 ----------------

def fmt(t: dict):
    when = (datetime.fromtimestamp(t["ts"], timezone.utc).astimezone().strftime("%m-%d %H:%M")
            if t["ts"] else "")
    title = f"@{t['handle']} 发了新动态"
    body = (f"{t['name']} (@{t['handle']})  {when}\n\n"
            f"{t['text']}\n\n"
            f"❤ {t['likes']}  🔁 {t['reposts']}  💬 {t['replies']}\n"
            f"{t['url']}")
    return title, body


def push_feishu(hook, t):
    title, body = fmt(t)
    http(hook, {"msg_type": "text", "content": {"text": f"{title}\n\n{body}"}}, timeout=12)


def push_dingtalk(hook, secret, t):
    import base64, hashlib, hmac
    url = hook
    if secret:
        ts = str(round(time.time() * 1000))
        sign = base64.b64encode(
            hmac.new(secret.encode(), f"{ts}\n{secret}".encode(), hashlib.sha256).digest()
        ).decode()
        url += f"&timestamp={ts}&sign={urllib.parse.quote(sign)}"
    title, body = fmt(t)
    http(url, {"msgtype": "text", "text": {"content": f"{title}\n\n{body}"}}, timeout=12)


def push_serverchan(key, t):
    title, body = fmt(t)
    data = urllib.parse.urlencode({"title": title, "desp": body}).encode()
    req = urllib.request.Request(f"https://sctapi.ftqq.com/{key}.send", data=data,
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=12) as r:
        r.read()


def push_bark(base, t):
    title, body = fmt(t)
    url = base.rstrip("/") + "/" + urllib.parse.quote(title, safe="") + "/" + urllib.parse.quote(body, safe="")
    http(url, timeout=12)


def push_wecom(hook, t):
    title, body = fmt(t)
    http(hook, {"msgtype": "text", "text": {"content": f"{title}\n\n{body}"}}, timeout=12)


def push_desktop(t):
    """Windows 气泡通知：非模态、10 秒自动消失、点击打开推文。零第三方依赖。"""
    if sys.platform != "win32":
        return
    import subprocess
    title, body = fmt(t)
    url = t["url"].replace("'", "''")
    ps = f'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$ni = New-Object System.Windows.Forms.NotifyIcon
$ni.Icon = [System.Drawing.SystemIcons]::Information
$ni.BalloonTipTitle = '{title.replace("'","''")}'
$ni.BalloonTipText = '{body[:240].replace("'","''").replace("`n"," ")}'
$ni.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info
$ni.Visible = $true
$ni.add_BalloonTipClicked({{ Start-Process '{url}' }})
$ni.ShowBalloonTip(10000)
Start-Sleep -Seconds 11
$ni.Dispose()
'''
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
    except OSError:
        pass


def notify_all(t: dict, n: dict):
    jobs = []
    if n.get("feishu_webhook"):
        jobs.append(("飞书", lambda: push_feishu(n["feishu_webhook"], t)))
    if n.get("dingtalk_webhook"):
        jobs.append(("钉钉", lambda: push_dingtalk(n["dingtalk_webhook"], n.get("dingtalk_secret", ""), t)))
    if n.get("serverchan_key"):
        jobs.append(("Server酱", lambda: push_serverchan(n["serverchan_key"], t)))
    if n.get("bark_url"):
        jobs.append(("Bark", lambda: push_bark(n["bark_url"], t)))
    if n.get("wecom_webhook"):
        jobs.append(("企业微信", lambda: push_wecom(n["wecom_webhook"], t)))
    if not jobs and n.get("desktop", True):
        jobs.append(("桌面气泡", lambda: push_desktop(t)))
    sent = []
    for name, fn in jobs:
        try:
            fn()
            sent.append(name)
        except Exception as e:
            log(f"  推送 {name} 失败: {e}")
    return sent


# ---------------- 主循环 ----------------

def run(cfg: dict, state: dict, once=False):
    watch = cfg.get("watch", [])
    interval = max(20, int(cfg.get("interval", 60)))
    workers = max(1, min(8, int(cfg.get("workers", 3))))
    retries = max(1, min(10, int(cfg.get("retries", 5))))
    log(f"开始监控 {len(watch)} 个账号 | 每 {interval}s 一轮 | {workers} 并发 / 重试 {retries} 次 | "
        f"数据源 api.fxtwitter.com（国内直连 / 免费 / 零 Key）")

    def probe(h):
        """单账号探测，失败重试；返回 (handle, kind, data, error)。
        关键不漏推保证：失败时不推进 since，下轮用旧值必然补回累积的新推。"""
        since = int(state.get(h, {}).get("since", 0))
        last = "unknown"
        for i in range(retries):
            try:
                changed, items = fetch_statuses(h, since)
                return h, "timeline", items if changed else [], None
            except urllib.error.HTTPError as e:
                if e.code == 204:
                    return h, "timeline", [], None
                if e.code == 404:
                    # 404 = 该账号时间线不可用，退化为推文计数哨兵
                    try:
                        return h, "sentinel", fetch_profile(h), None
                    except Exception as e2:
                        last = f"404 且哨兵失败: {e2}"
                else:
                    last = f"HTTP {e.code}"
            except Exception as e:
                last = str(e)
            if i + 1 < retries:
                time.sleep(0.3)
        return h, "error", None, last

    while True:
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(probe, watch))

        for h, kind, data, err in results:
            if kind == "error":
                log(f"@{h} 拉取失败: {err}（下轮重试）")
                continue

            st = state.setdefault(h, {"since": 0, "seen": [], "count": 0})
            seen = set(st.get("seen", []))

            if kind == "sentinel":
                # 时间线接口不给的账号（如 404），退化为"推文计数变化"哨兵
                cnt = int(data.get("statuses", 0))
                old = int(st.get("count", 0))
                if not st.get("baselined"):
                    st["baselined"] = True
                    st["count"] = cnt
                    log(f"@{h} 基线建立（哨兵模式，计数 {cnt}，时间线接口不可用）")
                elif cnt > old:
                    t = {"id": f"cnt-{cnt}-{int(time.time())}",
                         "url": f"https://x.com/{h}", "handle": h,
                         "name": data.get("name", h),
                         "text": f"该账号发了新动态（推文数 {old} → {cnt}）。"
                                 f"时间线接口暂不可用，点链接查看原文。",
                         "ts": int(time.time()), "replies": 0, "reposts": 0,
                         "likes": 0, "replying_to": None, "reposted_by": None}
                    channels = notify_all(t, cfg.get("notify", {}))
                    log(f"  ★ @{h} 新动态 [哨兵 {','.join(channels) or '未送达'}] 计数 {old}→{cnt}")
                    st["count"] = cnt
                continue

            # 正常时间线
            is_new = not st.get("baselined")
            fresh = [normalize(it) for it in data]
            fresh = [t for t in fresh if should_notify(t, cfg, seen)]
            fresh.sort(key=lambda x: x["ts"])

            if is_new:
                st["baselined"] = True
                log(f"@{h} 基线建立，{len(fresh)} 条历史推文记为已读（此后只推新增）")
            else:
                for t in fresh:
                    channels = notify_all(t, cfg.get("notify", {}))
                    preview = t["text"].replace("\n", " ")[:70]
                    log(f"  ★ @{h} 新动态 [{','.join(channels) or '未送达'}] {preview}")

            for t in fresh:
                seen.add(t["id"])
                if t["ts"] > int(st.get("since", 0)):
                    st["since"] = t["ts"]
            st["seen"] = list(seen)[-300:]
            state[h] = st

        save_json(STATE_FILE, state)
        cost = time.time() - t0
        fails = sum(1 for _, k, _, _ in results if k == "error")
        log(f"本轮完成，耗时 {cost:.1f}s，失败 {fails} 个（下轮自动补齐，不漏推）")
        if once:
            log("--once 结束")
            return
        time.sleep(max(5, interval - cost))


def main():
    ap = argparse.ArgumentParser(description="国内直连 / 免费 / X 关注动态实时提醒")
    ap.add_argument("--once", action="store_true", help="只跑一轮")
    ap.add_argument("--test", action="store_true", help="发一条测试推送")
    ap.add_argument("--add", metavar="HANDLE", help="追加关注账号")
    ap.add_argument("--list", action="store_true", help="列出关注账号")
    ap.add_argument("--reset", action="store_true", help="清空状态，重新建立基线")
    args = ap.parse_args()

    cfg = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    cfg.setdefault("notify", {})

    if args.add:
        h = args.add.lstrip("@")
        if h not in cfg["watch"]:
            cfg["watch"].append(h)
            save_json(CONFIG_FILE, cfg)
        log(f"已添加 @{h}｜共 {len(cfg['watch'])} 个：{', '.join(cfg['watch'])}")
        return
    if args.list:
        for h in cfg["watch"]:
            print(f"  @{h}")
        print(f"\n共 {len(cfg['watch'])} 个｜配置: {CONFIG_FILE}")
        return
    if args.reset:
        save_json(STATE_FILE, {})
        log("状态已清空，下次启动重新建立基线（不推历史）")
        return
    if args.test:
        t = {"id": "TEST", "url": "https://x.com/sama", "handle": "sama", "name": "Sam Altman",
             "text": "测试推送 ✅ 通道已打通", "ts": int(time.time()),
             "replies": 0, "reposts": 0, "likes": 0, "replying_to": None, "reposted_by": None}
        print("已发送 ->", notify_all(t, cfg["notify"]))
        return

    state = load_json(STATE_FILE, {})
    try:
        run(cfg, state, once=args.once)
    except KeyboardInterrupt:
        save_json(STATE_FILE, state)
        log("已停止，状态已保存。")


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass
    main()
