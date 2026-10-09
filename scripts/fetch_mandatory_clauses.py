#!/usr/bin/env python3
"""从官方公告页机械提取强条清单，并与仓库内文档做 diff。

为什么需要这个：GB 50015-2019 的强条清单在人工转抄过程中出现过
三个不同数字（29 / 30 / 31）。这是"数字看着有、但错了，且没有任何
检查会报"的典型失败模式——同一模式已出现三次（附录 G 数值错位、
5.2.38 静默丢维度、强条清单少 1 条）。

因此本脚本不做人工核对，只做 diff。

⚠️ 关于可信度（务必阅读）

本脚本的网络请求在部分环境下会被拦截（urllib 报 HTTPError，而
同一 URL 用 curl 可能返回 200）。此时会回退到本地副本
archive/GB50015-2019/announcement.html。

**关键：回退时的 diff 是"副本与文档"自比对，不证明与官方公告一致。**
这是同源自证——两端可能来自同一次手工整理。若脚本在回退时仍输出
"匹配公告原文"并返回 0，就是在校验机制里制造虚假的确信：
校验通过了，但它没有真的校验。

因此本脚本严格区分三种状态，退出码不可混用：

    0  已与官方公告原文比对，且一致
    1  不一致（公告有而文档缺，或文档有而公告无）
    2  未能与官方公告原文比对（网络不可用且回退到本地副本，
       或解析失败）——此结果仅证明本地副本与文档自洽，
       不证明与官方公告一致

退出码 2 不是失败，而是"未验证"。调用方必须区分对待。

用法：
    python scripts/fetch_mandatory_clauses.py                 # 只抓取并展示
    python scripts/fetch_mandatory_clauses.py --check         # 与文档比对

离线环境下想确认公告原文，只能人工下载后替换 announcement.html，
并同时更新其来源声明（见 archive/GB50015-2019/SOURCE.md）。
"""
from __future__ import annotations

import pathlib
import re
import sys
import urllib.request
from dataclasses import dataclass

ANNOUNCE_URL = "https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2019/art_17339_242990.html"
ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE_MD = ROOT / "archive" / "GB50015-2019" / "SOURCE.md"
LOCAL_HTML = ROOT / "archive" / "GB50015-2019" / "announcement.html"

# 退出码语义（严禁混用）
EXIT_OK = 0        # 已与官方公告比对且一致
EXIT_MISMATCH = 1  # 与公告原文不一致
EXIT_UNVERIFIED = 2  # 未与官方公告比对（回退/解析失败）


@dataclass
class FetchResult:
    """抓取结果。source 决定 diff 的可信度，不可省略。"""

    html: str
    source: str        # "network" | "local_fallback"
    detail: str = ""   # 人类可读的来源说明

    @property
    def verified_against_official(self) -> bool:
        """是否真的与官方公告原文比对过。只有 True 时才能声称「匹配公告原文」。"""
        return self.source == "network"


def fetch_announcement(retries: int = 3) -> FetchResult:
    """抓取公告页。失败时回退本地副本，并如实标注来源。

    沙箱环境下脚本进程的网络请求可能被拦截，因此需要本地副本兜底。
    但回退时必须标记 source="local_fallback"——调用方据此禁止
    声称「与官方公告一致」。
    """
    import time

    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                ANNOUNCE_URL, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            return FetchResult(
                html=html,
                source="network",
                detail=f"已抓取官方公告页（HTTP 200，{len(html)} 字符）",
            )
        except Exception as e:
            last = e
            if attempt < retries:
                print(f"  第 {attempt} 次抓取失败（{type(e).__name__}），重试…")
                time.sleep(1)

    if LOCAL_HTML.exists():
        html = LOCAL_HTML.read_text(encoding="utf-8", errors="ignore")
        return FetchResult(
            html=html,
            source="local_fallback",
            detail=(
                f"网络不可用（{type(last).__name__}），回退本地副本 "
                f"{LOCAL_HTML.name}（{len(html)} 字符）。"
                f"该副本来源未经本次验证，diff 结果不证明与官方公告一致。"
            ),
        )

    raise SystemExit(
        f"抓取公告失败：{type(last).__name__} {last}\n"
        f"且无本地副本可回退。请手工下载后存到 {LOCAL_HTML}\n"
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
    """提取 SOURCE.md 中已记录的强条清单。

    按显式标记定位，不用 split("```")[1] 的位置索引——文档里可能
    先出现其他代码块（如复核命令），位置索引会取错块且不报错。
    这正是本脚本要防的那类静默失败。
    """
    if not SOURCE_MD.exists():
        return None
    text = SOURCE_MD.read_text(encoding="utf-8")

    # 清单块必须紧跟在明确的标题行之后
    anchor = "## 强条清单"
    i = text.find(anchor)
    if i < 0:
        return None

    # 从该标题起，找第一个非 bash 的围栏代码块
    rest = text[i + len(anchor):]
    for m in re.finditer(r"```(\w*)\n(.*?)```", rest, re.S):
        if m.group(1).lower() in ("bash", "sh", "shell", ""):
            # 纯围栏或 shell 块：可能是命令示例，若内含条文号也接受
            body = m.group(2)
            if re.search(r"\d+\.\d+\.\d+", body):
                return set(re.findall(r"\d+\.\d+\.\d+", body))
            continue
        return set(re.findall(r"\d+\.\d+\.\d+", m.group(2)))
    return None


def audit_local_copy(html: str) -> list[str]:
    """审查本地副本是否像一份真实抓取的政务页面。

    真实的住建部政务页面必然包含导航栏、脚本样式、分享组件等结构，
    体积通常在数十 KB。若副本仅有极少段落且无任何 URL 与页面结构
    元素，它更可能是手工整理的最小复现，不应承担"公告原文"的角色。
    本函数只给出提示，不作为判定依据——结论须由人工给出。
    """
    warnings: list[str] = []
    size = len(html)
    para_count = len(re.findall(r"<p[ >]", html))
    has_url = bool(re.search(r"https?://", html))
    has_chrome = bool(
        re.search(r"nav|header|footer|script|style|share", html, re.I)
    )

    if size < 5000:
        warnings.append(f"副本仅 {size} 字符，明显小于真实政务页面（通常数十 KB）")
    if para_count < 10:
        warnings.append(f"仅 {para_count} 个段落，真实页面通常有数十个")
    if not has_url:
        warnings.append("不含任何 URL，无法回溯抓取来源")
    if not has_chrome:
        warnings.append("不含导航/脚本/样式等页面结构元素")
    return warnings


def main() -> int:
    check = "--check" in sys.argv

    try:
        result = fetch_announcement()
    except SystemExit:
        raise
    except Exception as e:
        print(f"抓取失败：{type(e).__name__} {e}")
        return EXIT_UNVERIFIED

    verified = result.verified_against_official

    print("=" * 60)
    print(f"来源：{result.detail}")
    print("=" * 60)

    if not verified:
        print()
        print("⚠️  未与官方公告页比对 —— 本次结论仅证明「本地副本与文档自洽」")
        print("⚠️  这不证明与官方公告一致。请在网络可用时重跑本脚本。")
        print()
        warnings = audit_local_copy(result.html)
        if warnings:
            print("本地副本形态审查：")
            for w in warnings:
                print(f"  · {w}")
            print()

    try:
        nums = parse_mandatory(result.html)
    except SystemExit as e:
        print(f"解析失败：{e}")
        return EXIT_UNVERIFIED
    except Exception as e:
        print(f"解析失败：{type(e).__name__} {e}")
        return EXIT_UNVERIFIED

    print(f"提取：{len(nums)} 条" + ("（已与官方公告比对）" if verified else "（来自本地副本）"))
    print("=" * 60)
    for i in range(0, len(nums), 10):
        print("  " + " ".join(nums[i : i + 10]))

    ch5 = [n for n in nums if n.startswith("5.")]
    print()
    if ch5:
        print(f"注意：第 5 章出现强条 {ch5}")
    else:
        print("第 5 章（雨水）无强条 → GB 50015-2019 第 5 章全部条文有效")
        if not verified:
            print("  （此判断同样基于本地副本，未经官方公告验证）")

    if not check:
        print()
        print("加 --check 可与 SOURCE.md 比对。")
        return EXIT_OK if verified else EXIT_UNVERIFIED

    doc = parse_source_md()
    if doc is None:
        print("\nSOURCE.md 未找到清单代码块，无法比对。")
        return EXIT_UNVERIFIED

    print()
    missing = [n for n in nums if n not in doc]
    extra = [n for n in doc if n not in nums]

    if not missing and not extra:
        if verified:
            print(f"一致：{len(doc)} 条全部匹配官方公告原文。")
            return EXIT_OK
        print(f"本地副本与 SOURCE.md 一致：{len(doc)} 条。")
        print()
        print("⚠️  退出码 2 = 未验证。以下三点必须明确：")
        print("   1. 结论成立，但未经官方公告比对，本地副本可能本身有误")
        print("   2. 不得据此声称「已与官方公告核对」")
        print("   3. 网络可用时重跑本脚本，或人工核对 SOURCE.md 的来源声明")
        return EXIT_UNVERIFIED

    print("不一致！")
    if missing:
        print(f"  原文有而文档缺（{len(missing)} 条）：{missing}")
    if extra:
        print(f"  文档有而原文无（{len(extra)} 条）：{extra}")
    print()
    print("处理：把 SOURCE.md 清单改为与公告原文一致，不要写推测的总数。")
    return EXIT_MISMATCH


if __name__ == "__main__":
    raise SystemExit(main())