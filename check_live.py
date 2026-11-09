#!/usr/bin/env python3
"""Hourly liveness checker for the live-source repo.

Re-tests every candidate in sources.json, rebuilds live.m3u / cctv.m3u /
weishi.m3u / difang.m3u keeping only currently-playable, carrier-clean lines
(max 2 per channel: official hosts first, then lowest latency), and writes
status.json + STATUS.md. Dead lines are dropped from the published lists but
stay in sources.json, so they are re-tested every hour and can come back.
"""
import json, os, sys, datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from test_urls import test_url
from build_repo import canon, host_of, official_score


def write_m3u(path, items):
    with open(path, "w", encoding="utf-8") as f:
        f.write('#EXTM3U x-tvg-url="https://epg.erw.cc/all.xml"\n')
        for it in items:
            logo = f'https://live.fanmingming.cn/tv/{it["name"].split()[0]}.png'
            f.write(f'#EXTINF:-1 tvg-name="{it["name"]}" tvg-logo="{logo}" '
                    f'group-title="{it["group"]}",{it["name"]}\n{it["url"]}\n')


def main():
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    ts = now.strftime("%Y-%m-%d %H:%M:%S")
    src_path = os.path.join(ROOT, "sources.json")
    prev = {}
    st_path = os.path.join(ROOT, "status.json")
    if os.path.exists(st_path):
        try:
            prev = {e["url"]: e for e in json.load(open(st_path, encoding="utf-8"))["entries"]}
        except Exception:
            prev = {}

    pool = json.load(open(src_path, encoding="utf-8"))
    print(f"[{ts}] testing {len(pool)} candidates")
    results = {}
    with ThreadPoolExecutor(max_workers=24) as ex:
        futs = {ex.submit(test_url, e["url"]): e for e in pool}
        for fut in as_completed(futs):
            results[futs[fut]["url"]] = fut.result()

    entries = []
    for e in pool:
        r = results[e["url"]]
        entries.append({**e, "status": r["status"], "latency_s": r["latency_s"],
                        "segments": r["segments"], "playable": r["playable"],
                        "checked_at": ts})

    by_channel = defaultdict(list)
    for e in entries:
        if e["playable"]:
            by_channel[(e["group"], e["name"])].append(e)

    chosen, groups = [], {"央视": [], "卫视": [], "地方台": []}
    for (grp, name), lines in sorted(by_channel.items()):
        lines.sort(key=lambda x: (official_score(x["url"]),
                                  x["latency_s"] if x["latency_s"] is not None else 99))
        seen, picked = set(), []
        for ln in lines:
            if ln["host"] in seen and len(picked) >= 1:
                continue
            picked.append(ln)
            seen.add(ln["host"])
            if len(picked) >= 2:
                break
        groups[grp].extend(picked)
        chosen.extend(picked)

    write_m3u(os.path.join(ROOT, "cctv.m3u"), groups["央视"])
    write_m3u(os.path.join(ROOT, "weishi.m3u"), groups["卫视"])
    write_m3u(os.path.join(ROOT, "difang.m3u"), groups["地方台"])
    write_m3u(os.path.join(ROOT, "live.m3u"),
              groups["央视"] + groups["卫视"] + groups["地方台"])

    dead = [e for e in entries if not e["playable"]]
    newly_dead = [e for e in dead if prev.get(e["url"], {}).get("playable")]
    revived = [e for e in entries if e["playable"] and prev.get(e["url"]) and not prev[e["url"]].get("playable")]

    status = {"checked_at": ts, "total": len(entries),
              "playable": len(by_channel) and sum(len(v) for v in groups.values()),
              "channels": len(by_channel), "dead": len(dead),
              "newly_dead": [f'{e["name"]} ({e["url"][:80]})' for e in newly_dead],
              "revived": [f'{e["name"]} ({e["url"][:80]})' for e in revived],
              "entries": entries}
    with open(st_path, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=1)

    with open(os.path.join(ROOT, "STATUS.md"), "w", encoding="utf-8") as f:
        f.write(f"# 测活状态\n\n最近检测：{ts}（北京时间，每小时自动检测）\n\n")
        f.write(f"- 候选源总数：{len(entries)}\n- 当前可用线路：{status['playable']}\n")
        f.write(f"- 覆盖频道：{len(by_channel)} 个（央视 {len(set(i['name'] for i in groups['央视']))} / "
                f"卫视 {len(set(i['name'] for i in groups['卫视']))} / "
                f"地方台 {len(set(i['name'] for i in groups['地方台']))}）\n")
        f.write(f"- 本次失效：{len(dead)} 条，其中新失效 {len(newly_dead)} 条\n")
        if newly_dead:
            f.write("\n## 本次新失效\n\n")
            for d in newly_dead:
                f.write(f"- {d}\n")
        if revived:
            f.write("\n## 本次恢复\n\n")
            for d in revived:
                f.write(f"- {d}\n")
        f.write("\n失效的源仍保留在 sources.json 中，每小时重测，恢复后自动回榜。\n")

    print(f"[{ts}] done: {len(by_channel)} channels, {status['playable']} lines, "
          f"{len(dead)} dead ({len(newly_dead)} newly dead, {len(revived)} revived)")


if __name__ == "__main__":
    main()
