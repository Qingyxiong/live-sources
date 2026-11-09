# 直播源仓库

央视 / 各省卫视 / 地方台直播源，只收 **IPv4**、三网（移动 / 联通 / 电信）通用源。
每小时自动测活一次，失效的源自动下架、恢复后自动回榜。

## 订阅地址（TVBox / 影视仓 → 设置 → 配置地址 / 直播源）

> 把下面任意一个地址粘贴到播放器的直播源订阅处即可，每小时测活后自动更新，地址不变。

- 全量：https://raw.githubusercontent.com/Qingyxiong/live-sources/main/live.m3u
- 央视：https://raw.githubusercontent.com/Qingyxiong/live-sources/main/cctv.m3u
- 卫视：https://raw.githubusercontent.com/Qingyxiong/live-sources/main/weishi.m3u
- 地方台：https://raw.githubusercontent.com/Qingyxiong/live-sources/main/difang.m3u
- 港台：https://raw.githubusercontent.com/Qingyxiong/live-sources/main/gangtai.m3u（TVB、TVBS、凤凰、中天、三立等，不在全量里）

国内加载慢可换 jsDelivr 镜像（同一文件）：把 `raw.githubusercontent.com/Qingyxiong/live-sources/main/` 换成 `cdn.jsdelivr.net/gh/Qingyxiong/live-sources@main/`。

| 文件 | 内容 | 频道数 |
|---|---|---|
| `live.m3u` | 全量：央视 + 卫视 + 地方台 | 见 STATUS.md |
| `cctv.m3u` | 央视 1–17、5+、8K、CGTN、央视数字付费频道 | 46 |
| `weishi.m3u` | 各省卫视 | 38 |
| `difang.m3u` | 中国各省内地方台（已剔除国外频道） | 412 |
| `gangtai.m3u` | 港台频道（不进全量） | 39 |

EPG：`https://epg.erw.cc/all.xml`（已写在 m3u 文件头）

## 测活规则

- 每个源每小时 GET 一次播放列表，要求 HTTP 200 且返回含 `#EXTM3U` 的有效列表，并且至少有一条 `#EXTINF` 分片或一条 `#EXT-X-STREAM-INF` 变体流，否则判失效（空列表/注广告的中继会被判失效）。
- 每个频道最多保留 2 条线路：官方台网 CDN 优先，其次按延迟从低到高。
- 失效源不删除，只下架：保留在 `sources.json` 中，每小时重测，恢复后自动回榜。
- 排除项（不进库）：IPv6 地址、移动咪咕 `cmvideo.cn`、联通 `CUCC`、带过期鉴权参数（`Authinfo` / `txSecret` / `key=txiptv`）的源、私网地址；国外频道（BBC、RT、ABC、NBC、Arirang 等）、春晚/轮播/歌曲等点播条目、纯音频广播流。
- 屏蔽名单（广告污染）：`74.91.26.218` 及其跳转目标 `192.187.115.106`、`69.197.146.178`——该中继 2026-11-09 被发现跳转到注广告的转流链，测活抓不到，已按主机名硬屏蔽。

## 当前状态

见 [STATUS.md](STATUS.md)（每小时更新）。

## 诚实说明

- 测活是从一台美国出口服务器发起的：能证明源是活的、列表是有效的，但**不能证明它在国内三网下同样流畅**。三网通用是靠“排除运营商专网/鉴权源 + 优先官方公开 CDN”来保证的，真正的三网播放效果需要在国内三网环境下实测。
- 央视官方 HLS（`liveop.cctv.cn`）带鉴权、从境外测基本 403；目前央视线主要来自 hebijunge/tvbox-config 的国内实测精选、iptv-org 社区中继和 CCTV+ 官方流。卫视官方流大多只在 App 内，公开 IPv4 源本来就少，卫视覆盖仍在补。
- CCTV-5 体育主台已有可用 IPv4 公开源；CCTV-4K 暂无境外可验证的公开 IPv4 源。卫视暂缺：天津、福建、辽宁、陕西、青海卫视。
- 很多小中继源不稳定：同一条源 18 分钟内可能在可用/失效之间翻转，所以每小时测活是必须的，失效源恢复后会自动回榜。纯音频广播流已剔除，只留电视台。
- 北邮 ivi（`ivi.bupt.edu.cn`）从境外测不到，未收录。

## 文件说明

| 文件 | 用途 |
|---|---|
| `live.m3u` / `cctv.m3u` / `weishi.m3u` / `difang.m3u` / `gangtai.m3u` | 发布用的订阅文件，每小时重建 |
| `sources.json` | 候选池：全部干净候选源及最近测活结果 |
| `check_live.py` | 每小时测活脚本（`python3 check_live.py`） |
| `build_repo.py` | 从上游测试结果初建仓库的脚本 |
| `status.json` / `STATUS.md` | 最近一次测活的机器/人类可读报告 |
| `_upstream/` | 上游原始清单（范明明、zhi35、iptv-org、YanG、hebijunge/tvbox-config 等）及测试记录 |
