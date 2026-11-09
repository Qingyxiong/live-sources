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

BLOCKED_HOSTS = {"74.91.26.218", "192.187.115.106", "69.197.146.178"}
# 74.91.26.218 was ad-polluted 2026-11-09 (302 -> ad-relay chain); its
# redirect targets are blocked too. test_url() cannot catch this: the
# relay returns a small but well-formed playlist, so the host must be
# dropped by name here and in sources.json.

# English names that are genuinely Chinese stations (keep); any other
# name with no CJK characters is treated as foreign and dropped.
CN_EN_ALLOW = {"Baicheng TV", "Chaozhou Public Channel", "Chuxiong News Channel",
               "Guangzhou TV", "Harbin Movie Channel", "Harbin Comprehensive News Channel",
               "Hebi News Channel", "Hunan Economy Channel", "Kangba TV",
               "QTV-2", "QTV-5", "Siping TV", "Xinjiang TV 2", "Xinjiang TV 3",
               "Nei Monggol TV", "Anhui TV", "Hebei TV", "Guangdong Satellite TV",
               "Hunan TV", "Xizang TV", "Xizang TV Chinese", "Xizang TV Tibetan",
               "Jiangsu TV", "Dragon TV", "Beijing TV", "Shenzhen TV",
               "Tianjin TV", "Shandong TV", "Sichuan TV", "Henan TV",
               "Hubei TV", "Fujian TV", "Guizhou TV", "Yunnan TV",
               "Chongqing TV", "Liaoning TV", "Heilongjiang TV", "Jilin TV",
               "Shaanxi TV", "Shanxi TV", "Gansu TV", "Qinghai TV",
               "Ningxia TV", "Hainan TV", "Guangxi TV", "Jiangxi TV",
               "Zhejiang TV", "Shanghai TV", "Harbin TV", "Lanzhou TV",
               "Anshun TV", "Chifeng TV", "Jingmen TV"}

FOREIGN_CJK_DROP = ("阿里郎", "东京", "Red Bull", "Camp Spoopy", "半岛新闻",
                    "亚洲新闻", "光良", "叶倩文", "周华健", "周慧敏", "孟庭苇",
                    "吕方", "任齐贤", "心太软", "童话", "伤逝", "痴心换情深")

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
    if re.match(r"(CNR|CRI)\b", n):
        return None, None  # radio stations (CNR/CRI), not TV
    n = re.sub(r"\((720p|1080p|2160p|576i|960p|480p|600p|4K|8K|HD|SD)\)", "", n, flags=re.I).strip()
    n = re.sub(r"\[(Geo-blocked|Not 24/7)\]", "", n).strip()
    # foreign / VOD stragglers that carry CJK annotations or country tags
    if ("春晚" in n or "轮播" in n or "歌曲" in n or re.search(r"\bMV\b", n)
            or n.startswith("[") or n.startswith(("RT ", "RT-", "Channel News Asia", "韩国"))
            or n == "特种兵之火凤凰"):
        return None, None
    u = n.upper()
    if u.startswith("CCTV") or u.startswith("CGTN"):
        m = re.search(r"CCTV[- ]?(5\+|4K|8K|\d+)", n, re.I)
        if m:
            num = m.group(1).upper()
            rest = n[m.end():].strip(" -·")
            rest = re.sub(r"(高清|超清|HD|4K|8K|标清).*$", "", rest).strip()
            suffix = rest or CCTV_SUFFIX.get(num, "")
            disp = f"CCTV-{num}" + (f" {suffix}" if suffix else "")
            return disp, "央视"
        # CCTV+ / CCTV-数字付费 / CGTN variants: keep name, group 央视
        disp = re.sub(r"(高清|超清|HD|4K|8K|标清).*$", "", n).strip(" -")
        return disp, "央视"
    if re.search(r"香港|澳门|台湾|翡翠台|TVB|TVBS|港台|凤凰|三立|东森|中天|民视|华视|公视|台视|年代|壹电视", n):
        return n, "港台"
    if any(d in n for d in FOREIGN_CJK_DROP):
        return None, None  # foreign channel or song-MV entry
    if "「" in n or "」" in n:
        return None, None  # song-MV / bracketed foreign entries
    for en, cn in EN_WS.items():
        if n.lower().startswith(en.lower()):
            return cn, "卫视"
    if "卫视" in n:
        base = n.split("卫视")[0]
        base = re.sub(r"(高清|超清|4K|8K|HD|标清).*$", "", base).strip()
        return base + "卫视", "卫视"
    if not re.search(r"[\u4e00-\u9fff]", n):
        # no Chinese characters: foreign unless allowlisted Chinese station
        if n not in CN_EN_ALLOW:
            return None, None
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
        if f.endswith("test_master_recheck.json"):
            continue
        try:
            entries.extend(json.load(open(f, encoding="utf-8")))
        except Exception as e:
            print("skip", f, e)
    print(f"tested entries total: {len(entries)}")
    # master-playlist recheck: segs==0 playable entries re-fetched 2026-11-09;
    # MASTER = real variant playlist (keep), STUB = empty/dead (drop)
    recheck = {}
    rc_path = os.path.join(UP, "test_master_recheck.json")
    if os.path.exists(rc_path):
        recheck = json.load(open(rc_path, encoding="utf-8"))
        print(f"master recheck loaded: {len(recheck)} urls")

    pool = {}
    dropped_blocked = dropped_stub = dropped_foreign = 0
    for e in entries:
        if not e.get("playable") or e.get("carrier_flag"):
            continue
        u = e["url"]
        if host_of(u) in BLOCKED_HOSTS:
            dropped_blocked += 1
            continue
        segs = e.get("segments")
        if segs == 0 and recheck.get(u) == "STUB":
            dropped_stub += 1
            continue
        if u in pool:
            continue
        disp, grp = canon(e["name"])
        if not disp or len(disp) > 30:
            dropped_foreign += 1
            continue
        pool[u] = {"name": disp, "group": grp, "url": u,
                   "latency_s": e.get("latency_s", e.get("latency")), "host": host_of(u),
                   "source": e.get("source", "")}
    print(f"clean playable unique urls: {len(pool)} "
          f"(blocked host: {dropped_blocked}, stub: {dropped_stub}, "
          f"foreign/radio/mv: {dropped_foreign})")

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
              "地方台": [c for c in chosen if c["group"] == "地方台"],
              "港台": [c for c in chosen if c["group"] == "港台"]}
    for g, items in groups.items():
        print(f"{g}: {len(set(i['name'] for i in items))} channels, {len(items)} lines")
    write_m3u(os.path.join(ROOT, "cctv.m3u"), groups["央视"], "央视")
    write_m3u(os.path.join(ROOT, "weishi.m3u"), groups["卫视"], "卫视")
    write_m3u(os.path.join(ROOT, "difang.m3u"), groups["地方台"], "地方台")
    write_m3u(os.path.join(ROOT, "gangtai.m3u"), groups["港台"], "港台")
    write_m3u(os.path.join(ROOT, "live.m3u"),
              groups["央视"] + groups["卫视"] + groups["地方台"], "全量")

    with open(os.path.join(ROOT, "sources.json"), "w", encoding="utf-8") as f:
        json.dump(sorted(pool.values(), key=lambda x: (x["group"], x["name"])),
                  f, ensure_ascii=False, indent=1)
    print("wrote m3u files + sources.json")


if __name__ == "__main__":
    main()
