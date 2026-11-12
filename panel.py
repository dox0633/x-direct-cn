#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
x-direct-cn 控制面板 —— 本地桌面 GUI（浏览器壳，纯本地，不访问任何外网页面）

双击桌面「X 关注动态直连助手」打开：
  - 看到所有关注账号发过的动态正文（本地存档，历史也在）
  - 正确的作者头像（自动下载到本地，断网也能显示）
  - 推文配图（可一键关闭显示）
  - 开启 / 暂停监控、立即刷新、输入 X 账号即可加关注、移除关注
  - 退出程序
所有内容都从本地 http://127.0.0.1:8899 读取，界面里没有任何外部链接。
"""

import hashlib
import html
import json
import mimetypes
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG_FILE = BASE / "config.json"
STATE_FILE = BASE / "state.json"
ITEMS_FILE = BASE / "items.json"
TRANS_FILE = BASE / "translations.json"   # 译文缓存，避免重复消耗免费额度
PANEL_FILE = BASE / "panel.html"
LOG_FILE = BASE / "panel.log"
MEDIA_DIR = BASE / "media"
AVATAR_DIR = MEDIA_DIR / "avatars"
IMAGE_DIR = MEDIA_DIR / "images"
HTML_FILE = BASE / "panel.html"

API = "https://api.fxtwitter.com/2/profile/{}/statuses"
PROFILE_API = "https://api.fxtwitter.com/{}"
PROXY = "https://images.weserv.nl/?url={}&w={}&output=jpg&q=78"
PORT = 8899
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

DEFAULT_CONFIG = {
    "watch": [
        "sama", "OpenAI", "OpenAIDevs", "ChatGPT", "gdb",
        "OfficialLoganK", "GeminiApp", "GoogleDeepMind",
        "demishassabis", "GoogleAIStudio", "GoogleAI"
    ],
    "interval": 30,           # 固定轮询周期（秒），已扣除抓取耗时
    "workers": 4,
    "retries": 5,
    "replies": False,
    "retweets": True,
    "show_images": True,       # 面板是否显示推文配图（头像始终显示）
    "translate": False,        # 英译汉开关：开启后动态自动显示中文
    "theme": "light",          # light 白天 / dark 黑夜
    "desktop_notify": True,    # 兼容旧配置
    "popup_notify": True,      # 弹窗提醒开关（新动态时是否弹 Windows 气泡）
    "notify": {},
}

# ---------------- 全局状态 ----------------
LOCK = threading.RLock()
CFG = {}
STATE = {}
ITEMS = []
TRANS = {}                  # 原文 hash -> 中文译文
RUNNING = True              # 监控是否运行
STOP_EVENT = threading.Event()
LAST_ROUND = {"at": 0, "cost": 0.0, "ok": 0, "fail": 0, "new": 0}
IMG_POOL = ThreadPoolExecutor(max_workers=6, thread_name_prefix="img")
TR_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="tr")
SERVER = None


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_json(path, default):
    if not path.exists():
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        return json.loads(json.dumps(default))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(default))


def save_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def http_get(url, timeout=8, binary=False, tries=3):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return (json.loads(raw.decode("utf-8", "replace")) if not binary else raw)
        except urllib.error.HTTPError as e:
            if e.code == 204:
                return None
            last = e
        except Exception as e:
            last = e
        time.sleep(0.2)
    raise last


# ---------------- 图片本地化 ----------------

def safe_name(s):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(s))[:120]


def proxy_url(src, width=800):
    if not src:
        return None
    if "weserv.nl" in src:
        return src
    return PROXY.format(urllib.parse.quote(src, safe=""), width)


def download_image(src, dest: Path, width=800):
    """把外网图片经国内可直连的代理下载到本地；失败静默，下次重试。"""
    if dest.exists() and dest.stat().st_size > 200:
        return True
    u = proxy_url(src, width)
    if not u:
        return False
    try:
        raw = http_get(u, timeout=10, binary=True, tries=2)
        if raw and len(raw) > 200:
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            tmp.write_bytes(raw)
            tmp.replace(dest)
            return True
    except Exception:
        pass
    return False


def local_rel(p: Path):
    return "/media/" + p.relative_to(MEDIA_DIR).as_posix()


def ensure_avatar(handle, avatar_url):
    dest = AVATAR_DIR / (safe_name(handle) + ".jpg")
    if download_image(avatar_url, dest, 96):
        return local_rel(dest)
    return ""


# ---------------- 英译汉（唯一方向，不做中译英） ----------------

TR_API = "https://api.mymemory.translated.net/get?q={}&langpair=en%7Czh-CN"
TR_COOLDOWN = {"until": 0}      # 429 限流冷却截止时间戳


def has_latin(s):
    return bool(re.search(r"[A-Za-z]", s or ""))


def split_text(text, limit=420):
    """按 URL 编码后的字节长度切段（MyMemory 单次上限约 500B），优先句尾/空格断开。"""
    def blen(s):
        return len(urllib.parse.quote(s, safe="").encode("ascii"))

    out, buf = [], ""
    for seg in re.split(r"(?<=[.!?。！？])\s+|\n+", text):
        seg = seg.strip()
        if not seg:
            continue
        if blen(seg) > limit:
            # 逐字符累加，避免多字节字符被截断
            cur = ""
            for ch in seg:
                if blen(cur + ch) > limit and cur:
                    sp = cur.rfind(" ")
                    if sp > len(cur) // 2:
                        out.append((cur[:sp]).strip())
                        cur = cur[sp + 1:] + ch
                    else:
                        out.append(cur.strip())
                        cur = ch
                else:
                    cur += ch
            seg = cur.strip()
        if blen(buf + " " + seg) > limit and buf:
            out.append(buf.strip())
            buf = seg
        else:
            buf = (buf + " " + seg).strip()
    if buf:
        out.append(buf)
    return [x for x in out if x.strip()]


TR_YOUDAO = "https://aidemo.youdao.com/trans?q={}&from=auto&to=zh-CHS"
BATCH_SIZE = 5           # 每批最多合并几段（有道 errorCode 103 = 文本过长）
BATCH_CHARS = 600        # 单批最大字符数，超过就拆半
TR_BUSY = {"until": 0}   # 有道 411 限流冷却


def tr_key(seg):
    return hashlib.md5(seg.encode("utf-8")).hexdigest()


def tr_cache_get(seg):
    with LOCK:
        return TRANS.get(tr_key(seg))


def tr_cache_put(pairs):
    """批量写缓存，只落一次磁盘。"""
    if not pairs:
        return
    with LOCK:
        changed = False
        for seg, txt in pairs:
            k = tr_key(seg)
            if txt and k not in TRANS:
                TRANS[k] = txt
                changed = True
        if changed:
            save_json(TRANS_FILE, TRANS)


def youdao_batch(segs, tries=2, depth=0):
    """有道 aidemo：换行拼接多条，一次请求翻一批（固定英译汉）。"""
    if not segs:
        return []
    marker = " ⏎ "
    clean = [s.replace("\r", " ").replace("\n", marker) for s in segs]
    payload = "\n".join(clean)
    out = [None] * len(segs)
    for attempt in range(tries):
        if time.time() < TR_BUSY["until"]:
            time.sleep(min(1.0, TR_BUSY["until"] - time.time()))
        try:
            u = TR_YOUDAO.format(urllib.parse.quote(payload, safe=""))
            j = http_get(u, timeout=8, tries=1)
            code = str((j or {}).get("errorCode"))
            if code in ("411", "103", "402"):   # 限流 / 过长
                if code == "411":
                    TR_BUSY["until"] = time.time() + 1.5
                raise ValueError("errorCode=" + code)
            if not j or code != "0":
                raise ValueError("errorCode=" + code)
            blocks = j.get("translation") or []
            txt = "\n".join(blocks) if isinstance(blocks, list) else str(blocks)
            parts = [p.strip() for p in txt.split("\n")]
            if len(parts) == len(segs):
                return [p.replace(marker, "\n") or None for p in parts]
        except Exception:
            pass
        if attempt + 1 < tries:
            time.sleep(0.15)
    # 失败：拆半递归（避免长文本被 103 拒绝）
    if len(segs) > 1 and depth < 3:
        mid = len(segs) // 2
        return youdao_batch(segs[:mid], tries=1, depth=depth + 1) + \
               youdao_batch(segs[mid:], tries=1, depth=depth + 1)
    return out


def mymemory_fallback(seg):
    """MyMemory 兜底（有配额限制，仅在有道失败且未冷却时用）。"""
    if time.time() < TR_COOLDOWN["until"]:
        return None
    bad = ("INVALID EMAIL", "QUERY LENGTH LIMIT", "MYMEMORY WARNING",
           "PLEASE SELECT TWO DISTINCT", "YOU USED ALL AVAILABLE", "TOO MANY REQUESTS")
    try:
        u = TR_API.format(urllib.parse.quote(seg, safe=""))
        j = http_get(u, timeout=8, tries=1)
        if (j or {}).get("responseStatus") == 429 or str((j or {}).get("quotaFinished")).lower() == "true":
            TR_COOLDOWN["until"] = time.time() + 120
            return None
        txt = html.unescape((((j or {}).get("responseData") or {}).get("translatedText") or "")).strip()
        if txt and not any(b in txt.upper() for b in bad):
            return txt
    except urllib.error.HTTPError as e:
        if e.code == 429:
            TR_COOLDOWN["until"] = time.time() + 120
    except Exception:
        pass
    return None


def translate_segments(segs):
    """把任意数量的段按批翻译：缓存 → 并发有道批量 → 只对少量漏网段兜底。"""
    results = [None] * len(segs)
    pending = []
    with LOCK:
        for i, s in enumerate(segs):
            c = TRANS.get(tr_key(s))
            if c:
                results[i] = c
            else:
                pending.append((i, s))
    if not pending:
        return results

    # 按字符数切批，避免 URL 过长 / errorCode 103
    batches, cur, size = [], [], 0
    for idx, s in pending:
        if cur and (len(cur) >= BATCH_SIZE or size + len(s) > BATCH_CHARS):
            batches.append(cur)
            cur, size = [], 0
        cur.append((idx, s))
        size += len(s)
    if cur:
        batches.append(cur)

    all_pairs = []

    def run_batch(b):
        got = youdao_batch([s for _, s in b], tries=1)
        pairs = []
        for (idx, s), zh in zip(b, got):
            if zh:
                results[idx] = zh
                pairs.append((s, zh))
        return b, got, pairs

    # 批次之间轻量并发（2 路）：再高会有道返回 411 限流，反而更慢
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(run_batch, b) for b in batches]
        leftovers = []
        for f in as_completed(futs):
            try:
                b, got, pairs = f.result()
                all_pairs.extend(pairs)
                for (idx, s), zh in zip(b, got):
                    if not zh:
                        leftovers.append((idx, s))
            except Exception:
                pass

    # 只对失败段走 MyMemory（通常为零，不会拖慢主路径）
    for idx, s in leftovers[:20]:
        zh = mymemory_fallback(s)
        if zh:
            results[idx] = zh
            all_pairs.append((s, zh))

    tr_cache_put(all_pairs)
    return results


def translate_text(text):
    """英译汉。返回译文字符串，失败返回 None。"""
    if not text or not has_latin(text):
        return None
    segs = split_text(text)
    if not segs:
        return None
    results = translate_segments(segs)
    if not any(results):
        return None
    return "\n".join((r if r else s) for r, s in zip(results, segs)).strip()


TR_INFLIGHT = set()


def translate_item(rec, force=False):
    """英译汉，结果写进 rec['zh']。force=True 手动点译不受开关限制。"""
    if rec.get("zh") or (not force and not CFG.get("translate")):
        return
    rid = rec.get("id", "")
    with LOCK:
        if rid in TR_INFLIGHT:
            return
        TR_INFLIGHT.add(rid)
    try:
        zh = translate_text(rec.get("text", ""))
        if zh:
            with LOCK:
                rec["zh"] = zh
                save_json(ITEMS_FILE, ITEMS)
            log(f"已翻译 @{rec['handle']}: {rid[:12]}")
    finally:
        with LOCK:
            TR_INFLIGHT.discard(rid)


def translate_batch_items(records):
    """把多条动态的所有文本段汇总成少量批次，一次批量请求翻完，再写回各条记录。"""
    rec_segs = []          # (rec, [段...])
    seen = set()
    flat = []              # 去重后的全部段，避免同一句重复请求
    for rec in records:
        segs = split_text(rec.get("text", ""))
        if segs:
            rec_segs.append((rec, segs))
            for s in segs:
                k = tr_key(s)
                if k not in seen:
                    seen.add(k)
                    flat.append(s)
    if not flat:
        return 0
    # 全量走缓存 + 并发批量翻译
    t0 = time.time()
    rmap = dict(zip(flat, translate_segments(flat)))
    results = None
    # 用映射回填，避免顺序依赖
    done = 0
    with LOCK:
        for rec, segs in rec_segs:
            if rec.get("zh"):
                continue
            parts = [rmap.get(s) for s in segs]
            if any(parts):
                rec["zh"] = "\n".join((r if r else s) for r, s in zip(parts, segs)).strip()
                done += 1
        if done:
            save_json(ITEMS_FILE, ITEMS)
    log(f"批量翻译 {len(rec_segs)} 条 → 本次新增 {done} 条，耗时 {time.time()-t0:.2f}s")
    return done


def auto_translate_latest():
    """英译汉开启时只自动翻「最新一条」；历史动态不自动翻，由用户点卡片按钮手动翻。
    返回是否有新增译文。"""
    if not CFG.get("translate"):
        return False
    with LOCK:
        ordered = sorted(ITEMS, key=lambda x: x.get("ts", 0), reverse=True)
        target = next((x for x in ordered if has_latin(x.get("text", ""))), None)
        if not target or target.get("zh"):
            return False
        rid, before = target.get("id"), target.get("zh")
    translate_item(target)
    with LOCK:
        return bool(target.get("zh")) and target.get("zh") != before


def translate_pending(loop=False):
    """常驻轻量线程：只负责「最新一条」自动翻译 + 手动任务的队列，不做历史全量补译。
    这样开启英译汉时几乎瞬时完成，不会卡在免费接口限流上。"""
    while not STOP_EVENT.is_set():
        if CFG.get("translate"):
            try:
                # 有新推到达时，最新一条自动翻；每 10s 检查一次即可
                auto_translate_latest()
            except Exception as e:
                log(f"自动翻译异常: {e}")
        if not loop:
            return
        STOP_EVENT.wait(10)


# ---------------- 抓取与解析 ----------------

def fetch_statuses(handle, since=0):
    url = API.format(urllib.parse.quote(handle, safe=""))
    if since:
        url += f"?since={since}"
    j = http_get(url, timeout=5, tries=1)
    if not j:
        return []
    return [x for x in j.get("results", []) if x.get("type") == "status"]


def to_ts(item):
    v = item.get("created_timestamp")
    if isinstance(v, (int, float)) and v:
        return int(v / 1000) if v > 1e11 else int(v)
    try:
        return int(datetime.strptime(item.get("created_at", ""),
                                     "%a %b %d %H:%M:%S %z %Y").timestamp())
    except (ValueError, TypeError):
        return 0


def parse(item, handle):
    a = item.get("author", {}) or {}
    media = item.get("media", {}) or {}
    pics = []
    for m in (media.get("all") or media.get("photos") or []):
        src = m.get("url") or m.get("thumbnail_url")
        if src:
            pics.append(src)
        if len(pics) >= 4:
            break
    ts = to_ts(item)
    try:
        when = datetime.fromtimestamp(ts, timezone.utc).astimezone().strftime("%m-%d %H:%M") if ts else ""
    except (ValueError, OSError, OverflowError):
        when = ""
    return {
        "id": str(item.get("id", "")),
        "handle": a.get("screen_name") or handle,
        "name": a.get("name") or handle,
        "avatar_url": a.get("avatar_url") or "",
        "avatar": "",
        "text": (item.get("text") or "").strip(),
        "ts": ts,
        "when": when,
        "likes": item.get("likes", 0) or 0,
        "reposts": item.get("reposts", 0) or 0,
        "replies": item.get("replies", 0) or 0,
        "views": item.get("views", 0) or 0,
        "images_src": pics,
        "images": [],
        "replying_to": item.get("replying_to"),
        "reposted_by": item.get("reposted_by"),
        "source": f"x.com/{a.get('screen_name') or handle}",   # 纯文本，不做链接
        "via": handle,                                         # 从哪个关注账号的时间线来的
        "zh": "",                                              # 中文译文（英译汉）
    }


def probe(h, full=False):
    """单账号探测：短超时 + 快速重试。失败返回 error，不推进 since（下轮补齐，不漏）。
    full=True 时不带 since，拉全量时间线用于填充看板历史。"""
    since = 0 if full else int(STATE.get(h, {}).get("since", 0))
    last = "unknown"
    for i in range(max(1, int(CFG.get("retries", 5)))):
        try:
            return h, "timeline", fetch_statuses(h, since), None
        except urllib.error.HTTPError as e:
            if e.code == 204:
                return h, "timeline", [], None
            if e.code == 404:
                try:
                    j = http_get(PROFILE_API.format(urllib.parse.quote(h, safe="")), timeout=5, tries=1)
                    u = (j or {}).get("user", {})
                    return h, "sentinel", {"count": int(u.get("tweets") or 0),
                                          "name": u.get("name", h),
                                          "avatar": u.get("avatar_url", "")}, None
                except Exception as e2:
                    last = f"404 且哨兵失败: {e2}"
            else:
                last = f"HTTP {e.code}"
        except Exception as e:
            last = str(e)
        if i + 1 < int(CFG.get("retries", 5)):
            time.sleep(0.3)
    return h, "error", None, last


def desktop_notify(t):
    # popup_notify 为显式开关；老配置里只有 desktop_notify 时以它为准
    enabled = CFG.get("popup_notify", CFG.get("desktop_notify", True))
    if not enabled or sys.platform != "win32":
        return
    import subprocess
    title = f"@{t['handle']} 发了新动态"
    # 开启英译汉时，提醒内容也用中文
    body = (t.get("zh") or t["text"])[:200].replace("'", "''").replace("\n", " ")
    tt = title.replace("'", "''")
    ps = f'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$ni = New-Object System.Windows.Forms.NotifyIcon
$ni.Icon = [System.Drawing.SystemIcons]::Information
$ni.BalloonTipTitle = '{tt}'
$ni.BalloonTipText = '{body}'
$ni.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info
$ni.Visible = $true
$ni.ShowBalloonTip(8000)
Start-Sleep -Seconds 9
$ni.Dispose()
'''
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                          "-Command", ps], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=0x08000000)
    except OSError:
        pass


def attach_media(rec, notify=False):
    """异步补齐头像 + 配图 + 译文。notify=True 时翻译完再弹中文提醒。"""
    try:
        if rec["avatar_url"] and not rec["avatar"]:
            rec["avatar"] = ensure_avatar(rec["handle"], rec["avatar_url"])
        if CFG.get("show_images") and rec["images_src"] and not rec["images"]:
            out = []
            for i, src in enumerate(rec["images_src"]):
                dest = IMAGE_DIR / (safe_name(rec["id"]) + f"_{i}.jpg")
                if download_image(src, dest, 800):
                    out.append(local_rel(dest))
            rec["images"] = out
        if CFG.get("translate") and not rec.get("zh"):
            translate_item(rec)
        if notify:
            desktop_notify(rec)
    except Exception:
        pass


def do_round(full=False):
    global ITEMS, STATE
    t0 = time.time()
    watch = list(CFG.get("watch", []))
    if not watch:
        return
    workers = max(1, min(8, int(CFG.get("workers", 4))))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda h: probe(h, full), watch))

    added, fails, jobs = 0, 0, []
    quiet = full   # 全量填充轮只记录，不弹通知
    with LOCK:
        known = {x["id"] for x in ITEMS}
        for h, kind, data, err in results:
            if kind == "error":
                fails += 1
                log(f"@{h} 拉取失败: {err}（下轮补齐）")
                continue
            st = STATE.setdefault(h, {"since": 0, "seen": [], "count": 0, "baselined": False})
            seen = set(st.get("seen", []))

            if kind == "sentinel":
                # 时间线接口暂不可用：只更新计数基线，不往时间线里塞占位假动态
                # （真实正文会在下轮时间线恢复后由 since 自动补齐，不会漏）
                cnt = int(data.get("count", 0))
                st["count"] = cnt
                st["baselined"] = True
                if data.get("avatar") and not (AVATAR_DIR / (safe_name(h) + ".jpg")).exists():
                    IMG_POOL.submit(ensure_avatar, h, data["avatar"])
                continue

            parsed = [parse(it, h) for it in data]
            first = not st.get("baselined")
            for rec in parsed:
                if not rec["id"] or rec["id"] in seen or rec["id"] in known:
                    continue
                if not CFG.get("replies") and (rec["replying_to"] or rec["text"].startswith("@")):
                    continue
                if not CFG.get("retweets") and rec["reposted_by"]:
                    continue
                seen.add(rec["id"])
                known.add(rec["id"])
                ITEMS.append(rec)
                added += 1
                jobs.append((rec, (not first) and (not quiet)))
                if rec["ts"] > int(st.get("since", 0)):
                    st["since"] = rec["ts"]
            st["seen"] = list(seen)[-300:]
            st["baselined"] = True
            STATE[h] = st

        ITEMS.sort(key=lambda x: x["ts"], reverse=True)
        ITEMS[:] = ITEMS[:600]
        save_json(ITEMS_FILE, ITEMS)
        save_json(STATE_FILE, STATE)

    for rec, notify in jobs:
        IMG_POOL.submit(attach_media, rec, notify)

    LAST_ROUND.update(at=int(time.time()), cost=round(time.time() - t0, 1),
                      ok=len(watch) - fails, fail=fails, new=added)
    log(f"本轮 {LAST_ROUND['ok']}/{len(watch)} 成功，新增 {added} 条，耗时 {LAST_ROUND['cost']}s")


def monitor_loop():
    # 存档为空时先全量拉一次，让面板一打开就有历史动态可看
    if not ITEMS:
        try:
            log("首次启动：全量填充历史动态")
            do_round(full=True)
        except Exception as e:
            log(f"全量填充异常: {e}")
    while not STOP_EVENT.is_set():
        started = time.time()
        if RUNNING:
            try:
                do_round()
            except Exception as e:
                log(f"监控轮异常: {e}")
        # 固定周期对齐：扣除本轮耗时，避免「抓取耗时 + interval」造成叠加延迟
        interval = max(20, int(CFG.get("interval", 30)))
        wait = max(2, interval - (time.time() - started))
        STOP_EVENT.wait(wait)


def backfill_images():
    """开启配图后，为已有但没图的动态补图。"""
    with LOCK:
        todo = [x for x in ITEMS[:120] if x.get("images_src") and not x.get("images")]
    for rec in todo:
        IMG_POOL.submit(attach_media, rec)


# ---------------- HTTP 服务 ----------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            try:
                self._send(200, HTML_FILE.read_bytes(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, "panel.html 缺失")
            return
        if path == "/api/data":
            with LOCK:
                data = {
                    "items": ITEMS[:300] if CFG.get("show_images") else
                             [{**x, "images": []} for x in ITEMS[:300]],
                    "accounts": list(CFG.get("watch", [])),
                    "running": RUNNING,
                    "show_images": bool(CFG.get("show_images")),
                    "translate": bool(CFG.get("translate")),
                    "popup_notify": bool(CFG.get("popup_notify", CFG.get("desktop_notify", True))),
                    "theme": CFG.get("theme", "light"),
                    "translated": sum(1 for x in ITEMS[:300] if x.get("zh")),
                    "round": dict(LAST_ROUND),
                    "total": len(ITEMS),
                }
            self._send(200, json.dumps(data, ensure_ascii=False))
            return
        if path.startswith("/media/"):
            rel = path[len("/media/"):]
            if ".." in rel:
                self._send(403, "forbidden")
                return
            f = MEDIA_DIR / rel
            if not f.is_file():
                self._send(404, "")
                return
            ct = mimetypes.guess_type(f.name)[0] or "image/jpeg"
            self._send(200, f.read_bytes(), ct)
            return
        self._send(404, "not found")

    def do_POST(self):
        global RUNNING, CFG
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            req = json.loads(self.rfile.read(length).decode("utf-8", "replace") or "{}")
        except json.JSONDecodeError:
            req = {}
        action = req.get("action", "")
        value = str(req.get("value", "")).strip().lstrip("@")

        if action == "start":
            RUNNING = True
            log("面板：开启监控")
        elif action == "stop":
            RUNNING = False
            log("面板：暂停监控")
        elif action == "toggle_images":
            CFG["show_images"] = not bool(CFG.get("show_images"))
            save_json(CONFIG_FILE, CFG)
            if CFG["show_images"]:
                backfill_images()
            log(f"面板：显示配图 = {CFG['show_images']}")
        elif action == "toggle_translate":
            CFG["translate"] = not bool(CFG.get("translate"))
            save_json(CONFIG_FILE, CFG)
            log(f"面板：英译汉 = {CFG['translate']}")
            if CFG["translate"]:
                threading.Thread(target=auto_translate_latest, daemon=True).start()
        elif action == "translate_one":
            # 手动英译汉指定一条（点卡片上的「译」按钮）
            with LOCK:
                rec = next((x for x in ITEMS if x.get("id") == value), None)
            if not rec:
                self._send(200, json.dumps({"ok": False, "msg": "该条不存在"}))
                return
            if rec.get("zh"):
                self._send(200, json.dumps({"ok": False, "msg": "该条已译过"}))
                return
            threading.Thread(target=translate_item, args=(rec, True), daemon=True).start()
            log(f"面板：手动翻译 {value[:14]}")
        elif action == "toggle_theme":
            CFG["theme"] = "dark" if CFG.get("theme", "light") == "light" else "light"
            save_json(CONFIG_FILE, CFG)
            log(f"面板：配色 = {CFG['theme']}")
        elif action == "toggle_popup":
            cur = bool(CFG.get("popup_notify", CFG.get("desktop_notify", True)))
            CFG["popup_notify"] = not cur
            CFG["desktop_notify"] = CFG["popup_notify"]   # 兼容纯推送版读取
            save_json(CONFIG_FILE, CFG)
            log(f"面板：弹窗提醒 = {CFG['popup_notify']}")
        elif action == "refresh":
            threading.Thread(target=lambda: RUNNING and do_round(), daemon=True).start()
        elif action == "add":
            if value and re.fullmatch(r"[A-Za-z0-9_]{1,15}", value):
                if value not in CFG["watch"]:
                    CFG["watch"].append(value)
                    save_json(CONFIG_FILE, CFG)
                    log(f"面板：新增关注 @{value}")
                    threading.Thread(target=lambda: probe_and_add(value), daemon=True).start()
            else:
                self._send(200, json.dumps({"ok": False, "msg": "账号格式不对（1-15 位字母数字下划线）"}))
                return
        elif action == "remove":
            if value in CFG["watch"]:
                CFG["watch"].remove(value)
                save_json(CONFIG_FILE, CFG)
                log(f"面板：移除关注 @{value}")
        elif action == "mark_read":
            pass
        elif action == "quit":
            log("面板：退出程序")
            self._send(200, json.dumps({"ok": True}))
            STOP_EVENT.set()
            threading.Thread(target=shutdown_server, daemon=True).start()
            return
        self._send(200, json.dumps({"ok": True}))


def probe_and_add(h):
    """新增账号后立即抓一轮，让面板马上出现内容。"""
    try:
        kind, data, err = probe(h, full=True)[1:]
        if kind != "timeline":
            return
        with LOCK:
            known = {x["id"] for x in ITEMS}
            st = STATE.setdefault(h, {"since": 0, "seen": [], "count": 0, "baselined": False})
            seen = set(st.get("seen", []))
            for it in data:
                rec = parse(it, h)
                if not rec["id"] or rec["id"] in known or rec["id"] in seen:
                    continue
                seen.add(rec["id"])
                ITEMS.append(rec)
                IMG_POOL.submit(attach_media, rec)
                if rec["ts"] > int(st.get("since", 0)):
                    st["since"] = rec["ts"]
            st["seen"] = list(seen)[-300:]
            st["baselined"] = True
            STATE[h] = st
            ITEMS.sort(key=lambda x: x["ts"], reverse=True)
            ITEMS[:] = ITEMS[:600]
            save_json(ITEMS_FILE, ITEMS)
            save_json(STATE_FILE, STATE)
        log(f"@{h} 首轮抓取完成")
    except Exception as e:
        log(f"@{h} 首轮抓取异常: {e}")


def shutdown_server():
    time.sleep(0.4)
    if SERVER:
        try:
            SERVER.shutdown()
            SERVER.server_close()
        except Exception:
            pass
    IMG_POOL.shutdown(wait=False)
    os._exit(0)


def already_running():
    try:
        http_get(f"http://127.0.0.1:{PORT}/api/data", timeout=1, tries=1)
        return True
    except Exception:
        return False


def main():
    global CFG, STATE, ITEMS, TRANS, SERVER
    for d in (MEDIA_DIR, AVATAR_DIR, IMAGE_DIR):
        d.mkdir(parents=True, exist_ok=True)

    if already_running():
        webbrowser.open(f"http://127.0.0.1:{PORT}")
        return

    CFG = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    for k, v in DEFAULT_CONFIG.items():
        CFG.setdefault(k, v)
    # 固定周期：老配置里的 60 会叠加抓取耗时导致延迟过大，统一收敛到 20~60
    CFG["interval"] = max(20, min(60, int(CFG.get("interval", 30))))
    STATE = load_json(STATE_FILE, {})
    TRANS = load_json(TRANS_FILE, {})
    if not isinstance(TRANS, dict):
        TRANS = {}
    ITEMS = load_json(ITEMS_FILE, [])
    if not isinstance(ITEMS, list):
        ITEMS = []
    # 清掉旧版哨兵占位假动态（正文会在时间线恢复后自动补齐）
    before = len(ITEMS)
    ITEMS[:] = [x for x in ITEMS
                if not str(x.get("id", "")).startswith("cnt-")
                and "时间线接口暂不可用" not in (x.get("text") or "")]
    dropped = before - len(ITEMS)
    for rec in ITEMS:
        rec.setdefault("zh", "")
        rec.setdefault("via", "")
        rec.pop("zh_dir", None)   # 清掉旧版双向字段
    if dropped:
        save_json(ITEMS_FILE, ITEMS)
        log(f"清理哨兵占位记录 {dropped} 条")
    save_json(CONFIG_FILE, CFG)
    log(f"控制面板启动｜英译汉 {'开' if CFG.get('translate') else '关'}｜译文缓存 {len(TRANS)} 条")

    # 常驻补译线程：开关开启后自动续译历史，配额恢复后继续
    threading.Thread(target=lambda: translate_pending(loop=True), daemon=True).start()

    # 已有存档补齐头像（异步，不阻塞启动）
    for rec in ITEMS[:120]:
        if rec.get("avatar_url") and not rec.get("avatar"):
            IMG_POOL.submit(attach_media, rec)

    threading.Thread(target=monitor_loop, daemon=True).start()

    SERVER = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    try:
        SERVER.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        STOP_EVENT.set()


if __name__ == "__main__":
    main()
