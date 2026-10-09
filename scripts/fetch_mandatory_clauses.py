#!/usr/bin/env python3
"""从官方公告页机械提取强条清单，并与仓库内文档做 diff。

为什么需要这个：GB 50015-2019 的强条清单在人工转抄过程中出现过
三个不同数字（29 / 30 / 31）。这是"数字看着有、但错了，且没有任何
检查会报"的典型失败模式——同一模式已出现三次（附录 G 数值错位、
5.2.38 静默丢维度、强条清单少 1 条）。

因此本脚本不做人工核对，只做 diff。

用法：
    python scripts/fetch_mandatory_clauses.py                 # 只抓取并展示
    python scripts/fetch_mandatory_clauses.py --check         # 与文档比对，退出码非零表示不一致
"""
from __future__ import annotations

import io
import pathlib
import re
import sys
import urllib.request

ANNOUNCE_URL = "https://www.mohurd.gov.cn/gongkai/zc/wijk/art/2019/art_17339_242990.html"
ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE_MD = ROOT / "archive" / "GB50015-2019" / "SOURCE.md"
# 公告原文的本地归档。沙箱环境可能拦截脚本的网络请求，
# 此时回退到本地副本，仍能完成 diff —— 比对能力不应依赖网络。
LOCAL_HTML = ROOT / "archive" / "GB50015-2019" / "announcement.html"


def fetch_announcement(retries: int = 3) -> str:
    """抓取公告页，失败时回退本地归档。

    沙箱环境下脚本进程的网络请求可能被拦截（表现为 urllib 报
    404 而 curl 同 URL 返回 200），因此需要本地副本兜底，
    保证 diff 能力始终可用。
    """
    import time

    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                ANNOUNCE_URL, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            last = e
            if attempt < retries:
                print(f"  第 {attempt} 次抓取失败（{type(e).__name__}），重试…")
                time.sleep(1)

    if LOCAL_HTML.exists():
        print(f"  网络不可用，回退本地归档：{LOCAL_HTML.name}")
        print("  ⚠ 本地归档可能过期，改动公告后需重新抓取")
        return LOCAL_HTML.read_text(encoding="utf-8", errors="ignore")

    raise SystemExit(
        f"抓取公告失败：{type(last).__name__} {last}\n"
        f"且无本地归档可回退。请手工下载后存到 {LOCAL_HTML}\n"
        f"或核对：{ANNOUNCE_URL}"
    )


def parse_mandatory(html: str) -> list[str]:
    """提取强条条文号。

    只匹配公告固定句式「其中，第X条为强制性条文」，
    避免抓到页面其他位置的数字。
    """
    m = re.search(r"其中[，,]?\s*第(.*?)条为强制性条文", html, re.S)
    if not m:
        raise SystemExit("未匹配到强条句式，公告页结构可能已变化")
    return re.findall(r"\d+\.\d+\.\d+", m.group(1))


def parse_source_md() -> set[str] | None:
    """提取 SOURCE.md 中已记录的强条清单（代码块内第一段）。"""
    if not SOURCE_MD.exists():
        return None
    text = SOURCE_MD.read_text(encoding="utf-8")
    if "```" not in text:
        return None
    block = text.split("```")[1]
    return set(re.findall(r"\d+\.\d+\.\d+", block))


def main() -> int:
    check = "--check" in sys.argv

    try:
        nums = parse_mandatory(fetch_announcement())
    except SystemExit:
        raise
    except Exception as e:
        print(f"解析失败：{type(e).__name__} {e}")
        print(f"请手工核对：{ANNOUNCE_URL}")
        return 2

    print("=" * 60)
    print(f"公告原文提取：{len(nums)} 条（机械提取，非人工转抄）")
    print("=" * 60)
    for i in range(0, len(nums), 10):
        print("  " + " ".join(nums[i : i + 10]))

    # 关键断言：第 5 章（雨水）不应有强条
    ch5 = [n for n in nums if n.startswith("5.")]
    print()
    if ch5:
        print(f"注意：第 5 章出现强条 {ch5}")
    else:
        print("确认：第 5 章（雨水）无强条 → GB 50015-2019 第 5 章全部条文有效")

    if not check:
        print()
        print("加 --check 可与 SOURCE.md 比对。")
        return 0

    doc = parse_source_md()
    if doc is None:
        print("\nSOURCE.md 未找到清单代码块，无法比对。")
        return 2

    print()
    missing = [n for n in nums if n not in doc]
    extra = [n for n in doc if n not in nums]

    if not missing and not extra:
        print(f"一致：{len(doc)} 条全部匹配公告原文。")
        return 0

    print("不一致！")
    if missing:
        print(f"  公告有而文档缺（{len(missing)} 条）：{missing}")
    if extra:
        print(f"  文档有而公告无（{len(extra)} 条）：{extra}")
    print()
    print("处理：把 SOURCE.md 清单改为与公告原文一致，不要写推测的总数。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
