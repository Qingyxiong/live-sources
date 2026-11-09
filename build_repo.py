#!/usr/bin/env python3
"""Build the curated live-source repo from tested results.

Reads _upstream/test_*.json (playable + carrier-clean entries), canonicalises
channel names, picks up to 2 lines per channel (official hosts first, then
lowest latency), and writes live.m3u / cctv.m3u / weishi.m3u / difang.m3u,
sources.json (candidate pool for the hourly checker) and STATUS.md.
"""
import json, os, re, glob
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
UP = os.path.join(ROOT, "_upstream")

CCTV_SUFFIX = {"1": "综合", "2": "财经", "3": "综艺", "4": "中文国际", "5": "体育",
               "6": "电影", "7": "国防军事", "8": "电视剧", "9": "纪录", "10": "科教",
               "11": "戏曲", "12": "社会与法", "13": "新闻", "14": "少儿", "15": "音乐",
               "17": "农业农村", "4K": "超高清", "8K": "超高清", "5+": "体育赛事"}

EN_WS = {"Hunan TV": "湖南卫视", "Guangdong Satellite TV": "广东卫视",
         "Anhui TV": "安徽卫视", "Hebei TV": "河北卫视",
         "Nei Monggol TV": "内蒙古卫视", "Xizang TV Chinese": "西藏卫视",
         "Xizang TV Tibetan": "西藏卫视藏语", "Jiangsu TV": "江苏卫视",
         "Dragon TV": "东方卫视", "Beijing TV": "北京卫视",
         "Shenzhen TV": "深圳卫视", "Tianjin TV": "天津卫视",
         "Shandong TV": "山东卫视", "Sichuan TV": "四川卫视",
         "Henan TV": "河南卫视", "Hubei TV": "湖北卫视",
         "Fujian TV": "福建卫视", "Guizhou TV": "贵州卫视",
         "Yunnan TV": "云南卫视", "Chongqing TV": "重庆卫视",
         "Liaoning TV": "辽宁卫视", "Heilongjiang TV": "黑龙江卫视",
         "Jilin TV": "吉林卫视", "Shaanxi TV": "陕西卫视",
         "Shanxi TV": "山西卫视", "Gansu TV": "甘肃卫视",
         "Qinghai TV": "青海卫视", "Ningxia TV": "宁夏卫视",
         "Xinjiang TV": "新疆卫视", "Hainan TV": "海南卫视",
         "Guangxi TV": "广西卫视", "Jiangxi TV": "江西卫视",
         "Zhejiang TV": "浙江卫视", "Shanghai TV": "东方卫视"}

OFFICIAL = ["cctv.cn", "cntv.cn", "cctvplus.com", "mgtv.com", "cztv",
            "hebtv.com", "wcetv.com", "jlntv.cn", "hrbtv.net", "nmtv.cn",
            "qhbtv.com", "ningxiahuangheyun.com", "zjgonline.com.cn",
            "cnr.cn", "qingting.fm", "kankanlive.com", "pdtvhd.com",
            "bestvcdn.com.cn", "tvfix.org", "jlntv", "hebyun.com.cn"]


def canon(name):
    n = re.sub(r"\s+", " ", name.strip())
    if re.search(r"广播|电台|Radio|\bFM\d|\bAM\d", n, re.I):
        return None, None  # audio-only, not a TV channel
    n = re.sub(r"\((720p|1080p|2160p|576i|960p|480p|600p|4K|8K|HD|SD)\)", "", n, flags=re.I).strip()
    n = re.sub(r"\[(Geo-blocked|Not 24/7)\]", "", n).strip()
    m = re.search(r"CCTV[- ]?(5\+|4K|8K|\d+)", n, re.I)
    if m:
        num = m.group(1).upper().replace("+", "+")
        rest = n[m.end():].strip(" -·")
        rest = re.sub(r"(高清|超清|HD|4K|8K|标清).*$", "", rest).strip()
        suffix = rest or CCTV_SUFFIX.get(num, "")
        disp = f"CCTV-{num}" + (f" {suffix}" if suffix else "")
        return disp, "央视"
    for en, cn in EN_WS.items():
        if n.lower().startswith(en.lower()):
            return cn, "卫视"
    if "卫视" in n:
        base = n.split("卫视")[0]
        base = re.sub(r"(高清|超清|4K|8K|HD|标清).*$", "", base).strip()
        return base + "卫视", "卫视"
    return n, "地方台"


def host_of(url):
    m = re.search(r"://([^/:?]+)", url)
    return m.group(1) if m else ""


def official_score(url):
    h = host_of(url).lower()
    return 0 if any(o in h for o in OFFICIAL) else 1


def main():
    entries = []
    for f in sorted(glob.glob(os.path.join(UP, "test_*.json"))):
        try:
            entries.extend(json.load(open(f, encoding="utf-8")))
        except Exception as e:
            print("skip", f, e)
    print(f"tested entries total: {len(entries)}")

    pool = {}
    for e in entries:
        if not e.get("playable") or e.get("carrier_flag"):
            continue
        u = e["url"]
        if u in pool:
            continue
        disp, grp = canon(e["name"])
        if not disp or len(disp) > 30:
            continue
        pool[u] = {"name": disp, "group": grp, "url": u,
                   "latency_s": e.get("latency_s"), "host": host_of(u),
                   "source": e.get("source", "")}
    print(f"clean playable unique urls: {len(pool)}")

    by_channel = defaultdict(list)
    for e in pool.values():
        by_channel[(e["group"], e["name"])].append(e)
    print(f"channels: {len(by_channel)}")

    chosen = []
    for (grp, name), lines in sorted(by_channel.items()):
        lines.sort(key=lambda x: (official_score(x["url"]), x["latency_s"] if x["latency_s"] is not None else 99))
        seen_hosts, picked = set(), []
        for ln in lines:
            if ln["host"] in seen_hosts and len(picked) >= 1:
                continue
            picked.append(ln)
            seen_hosts.add(ln["host"])
            if len(picked) >= 2:
                break
        chosen.extend(picked)

    def write_m3u(path, items, title):
        with open(path, "w", encoding="utf-8") as f:
            f.write('#EXTM3U x-tvg-url="https://epg.erw.cc/all.xml"\n')
            for it in items:
                logo = f'https://live.fanmingming.cn/tv/{it["name"].split()[0]}.png'
                f.write(f'#EXTINF:-1 tvg-name="{it["name"]}" tvg-logo="{logo}" '
                        f'group-title="{it["group"]}",{it["name"]}\n{it["url"]}\n')

    groups = {"央视": [c for c in chosen if c["group"] == "央视"],
              "卫视": [c for c in chosen if c["group"] == "卫视"],
              "地方台": [c for c in chosen if c["group"] == "地方台"]}
    for g, items in groups.items():
        print(f"{g}: {len(set(i['name'] for i in items))} channels, {len(items)} lines")
    write_m3u(os.path.join(ROOT, "cctv.m3u"), groups["央视"], "央视")
    write_m3u(os.path.join(ROOT, "weishi.m3u"), groups["卫视"], "卫视")
    write_m3u(os.path.join(ROOT, "difang.m3u"), groups["地方台"], "地方台")
    write_m3u(os.path.join(ROOT, "live.m3u"),
              groups["央视"] + groups["卫视"] + groups["地方台"], "全量")

    with open(os.path.join(ROOT, "sources.json"), "w", encoding="utf-8") as f:
        json.dump(sorted(pool.values(), key=lambda x: (x["group"], x["name"])),
                  f, ensure_ascii=False, indent=1)
    print("wrote m3u files + sources.json")


if __name__ == "__main__":
    main()
