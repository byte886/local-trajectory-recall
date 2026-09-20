#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
local-trajectory-recall · 本地对话轨迹检索（跨会话记忆回溯）

豆包桌面端把每次会话的逐字记录落盘在本地，每行一个 JSON：
  ~/Library/Application Support/Doubao/<Profile>/.doubao/agent_mode/workspace/.sessions/<sid>/agents/<aid>/system/trajectory.jsonl
  role = user / assistant / tool；content = 内容。
一个 sid 下可能有多个 agent：m_ 开头=主对话（用户可见），s_/o_ 开头=子 agent（工具调用，跳过）。

用法（系统 python3 即可，无第三方依赖）:
  python3 recall.py list                # 列出最近的主会话（时间倒序，看历史有哪些）
  python3 recall.py where               # 当前正在用的是哪条 trajectory
  python3 recall.py stats              # 当前会话统计（轮数/角色/字数）
  python3 recall.py stats --id 38442   # 指定某会话（用 sid 片段）
  python3 recall.py search 股息率       # 在【当前会话】搜 用户+助手 原话
  python3 recall.py search --all 决策  # 跨【全部主会话】搜（找回之前讨论过的东西）
  python3 recall.py search --id 38441 接口  # 只在指定会话里搜
  python3 recall.py export out.md      # 导出当前会话可读对话（跳过 tool）

隐私红线：trajectory 含系统提示/工具返回/token，只本机自用，绝不粘进 git/文档/对外。
"""
import sys, json, glob, os, time, re
from pathlib import Path


def _roots():
    home = str(Path.home())
    return glob.glob(os.path.join(
        home,
        "Library/Application Support/Doubao/*/.doubao/agent_mode/workspace/.sessions/*/agents/*/system/trajectory.jsonl"))


def _info(p):
    m = re.search(r"\.sessions/([^/]+)/agents/([^/]+)/system/trajectory", p)
    sid = m.group(1) if m else "?"
    aid = m.group(2) if m else "?"
    return sid, aid, aid.startswith("m_")


def all_trajectories(main_only=False):
    ps = _roots()
    if main_only:
        ps = [p for p in ps if _info(p)[2]]
    return sorted(ps, key=os.path.getmtime)


def latest(main_only=True):
    c = all_trajectories(main_only)
    return c[-1] if c else None


def pick(frag=None):
    """按 sid 片段选会话；不给则取最新主会话。"""
    if not frag:
        return latest()
    for p in reversed(all_trajectories(main_only=False)):
        if frag in p:
            return p
    return None


def load(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def first_user(rows, n=40):
    for r in rows:
        if r.get("role") == "user":
            return str(r.get("content", "")).replace("\n", " ")[:n]
    return "(无用户消息)"


def cmd_list(limit=20):
    ps = list(reversed(all_trajectories(main_only=True)))[:limit]
    if not ps:
        print("未找到任何主会话 trajectory")
        return
    print(f"最近 {len(ps)} 个主会话（时间倒序，最上=最新）：\n")
    for p in ps:
        sid, aid, _ = _info(p)
        mt = time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(p)))
        rows = load(p)
        users = sum(1 for r in rows if r.get("role") == "user")
        print(f"[{mt}] sid=…{sid[-6:]} | {users}轮用户 | {first_user(rows)}")


def cmd_where():
    p = latest()
    if not p:
        print("未找到 trajectory"); return
    sid, _, _ = _info(p)
    mt = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(p)))
    print(f"当前最新主会话：{p}\n  sid=…{sid[-6:]}  更新于 {mt}")


def cmd_stats(path):
    rows = load(path)
    import collections
    c = collections.Counter(r.get("role", "?") for r in rows)
    total = sum(len(str(r.get("content", ""))) for r in rows)
    print(f"共 {len(rows)} 条 | 用户 {c.get('user',0)} | 助手 {c.get('assistant',0)} | 工具 {c.get('tool',0)} | 约 {total/10000:.1f}万字")
    print("首条用户:", first_user(rows))
    print("末条用户:", first_user(list(reversed(rows))))


def cmd_search(paths, kw):
    hits = 0
    for p in paths:
        rows = load(p)
        sid = _info(p)[0][-6:]
        for r in rows:
            if r.get("role") not in ("user", "assistant"):
                continue
            txt = str(r.get("content", ""))
            if kw in txt:
                hits += 1
                i = txt.find(kw)
                snip = txt[max(0, i - 60):i + 100].replace("\n", " ")
                tag = "用户" if r.get("role") == "user" else "助手"
                print(f"[…{sid}] [{tag}] ...{snip}...")
                if hits >= 40:
                    print("...(更多省略，缩小关键词)"); print(f"共命中 {hits}+ 条"); return
    print(f"共命中 {hits} 条")


def cmd_export(path, out):
    rows = load(path)
    with open(out, "w") as f:
        for r in rows:
            if r.get("role") not in ("user", "assistant"):
                continue
            c = str(r.get("content", "")).strip()
            if not c:
                continue
            f.write(f"\n### {'用户' if r.get('role')=='user' else '助手'}\n\n{c}\n")
    print(f"已导出: {out}")


def _get(args, flag):
    return args[args.index(flag) + 1] if flag in args else None


if __name__ == "__main__":
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "list"
    body = [a for a in argv[1:] if a != "--all"]
    frag = _get(body, "--id")
    if cmd == "list":
        cmd_list()
    elif cmd == "where":
        cmd_where()
    elif cmd == "stats":
        p = pick(frag); cmd_stats(p); print("轨迹:", p)
    elif cmd == "search" and len(argv) >= 2:
        kw = argv[1]
        if "--all" in argv:
            paths = all_trajectories(main_only=True)
        else:
            paths = [pick(frag)]
        cmd_search(paths, kw)
    elif cmd == "export" and len(argv) >= 2:
        cmd_export(pick(frag), argv[1])
    else:
        print(__doc__)
