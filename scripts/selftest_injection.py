#!/usr/bin/env python3
"""校验脚本的反向注入自检。

背景（第 7 轮失败）：做反向注入时，如果注入本身失效——
例如按错误的 marker 做字符串替换、匹配不上、什么都没插入——
校验脚本会因为「本来就没问题」而报「通过」。
表面结果是「脚本抓不出这个缺陷」，实际是「缺陷没被注入」。

这一步比前六轮更隐蔽：前六轮是校验手段失效，这一步是**校验手段
被正确地执行了，但被测对象没有被正确地污染**。两者都会产出
「通过」这个看起来正常的结果。

因此反向注入必须自带三项断言：
  1. 注入确实改变了目标文件（比较前后指纹）
  2. 校验脚本对污染后的文件返回非零
  3. 还原后校验脚本返回零

任一不满足即报错退出，不允许把「注入无效」误认为「校验有效」。

用法：
    python scripts/selftest_injection.py
"""
from __future__ import annotations

import hashlib
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
# 与 verify_checklist.py 使用同一套 glob，避免自检与被检定位到
# 不同文件而给出虚假结论（清单改名时两者必须同步变化）。
CHECKLIST_GLOB = "*核对*.md"
VERIFY = ROOT / "scripts" / "verify_checklist.py"

# 注入内容：复制一行清单数据行，使清单多出一行。
#
# 不硬编码具体条目或标题——本项目已两次因硬编码失效：一次 marker
# 写成 '### ## P3'（实际 '### P3'），一次精确等值匹配遇标题含
# 全角空格抛 ValueError。两次表面都是「校验通过」，实际是注入没发生。
#
# 仅靠「表格行 + 反引号」也不够：清单内还有说明性表格（证据等级
# 说明、优先级总览等），复制那些行不会触发任何断言。必须要求首列
# 是形如 GB50015-2019-xxx / EP-xxx 的 rule_id。
ROW_MARKER = re.compile(r"^\|\s*`((?:GB|CJJ|CJT|EP)-[^`]+)`\s*\|")


class SelfTestFailure(Exception):
    pass


def fingerprint(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_verify() -> int:
    return subprocess.run(
        [sys.executable, str(VERIFY)], capture_output=True, text=True
    ).returncode


def find_checklist() -> pathlib.Path:
    matches = list((ROOT / "docs").glob(CHECKLIST_GLOB))
    if len(matches) != 1:
        raise SelfTestFailure(f"清单文件定位失败：{matches}")
    return matches[0]


def main() -> int:
    print("=" * 60)
    print("校验脚本 · 反向注入自检")
    print("=" * 60)

    # 全程捕获 SelfTestFailure。
    # 为什么必须全局捕获：本脚本的目的是「证明校验脚本能抓出缺陷」。
    # 若自检本身失败却抛出裸 traceback，输出会被调用栈淹没——
    # 「为什么自检失败」这个信息被淹没，与第 4 轮「脚本没在校验却报通过」
    # 同型：表面是一个失败，实际原因不可见。故此处必须给出明确中文提示。
    try:
        return _run()
    except SelfTestFailure as e:
        print(f"\n    [F] 自检失败：{e}")
        print("        注意：本脚本用于验证校验脚本的有效性。")
        print("        自检失败不等于校验脚本无效——先查本脚本的注入种子是否与清单匹配。")
        return 3
    except Exception as e:  # noqa: BLE001 兜底，避免裸 traceback
        print(f"\n    [F] 自检意外异常：{type(e).__name__} {e}")
        return 4


def _run() -> int:
    checklist = find_checklist()

    print(f"目标清单：{checklist.name}")
    print(f"目标校验：{VERIFY.name}")

    # 前置：干净状态下校验必须通过
    rc0 = run_verify()
    print(f"\n[1] 干净状态校验      退出码 {rc0}")
    if rc0 != 0:
        print("    基线就不干净，无法进行反向测试。先修复基线。")
        return 2

    with tempfile.TemporaryDirectory() as td:
        backup = pathlib.Path(td) / checklist.name
        shutil.copy2(checklist, backup)
        before_fp = fingerprint(checklist)

        try:
            # 注入：复制一行真实存在的清单行
            lines = checklist.read_text(encoding="utf-8").splitlines(keepends=True)
            seed_lines = [l for l in lines if ROW_MARKER.match(l.strip())]
            if not seed_lines:
                raise SelfTestFailure(
                    "未找到可注入的清单数据行（形如 `| `GB50015-…` |`）。"
                    "请检查 ROW_MARKER 是否仍匹配清单结构。"
                )
            checklist.write_text(
                checklist.read_text(encoding="utf-8") + seed_lines[0],
                encoding="utf-8",
            )

            # 断言 1：注入必须真的改变文件
            if fingerprint(checklist) == before_fp:
                print("    [F] 注入未改变文件 —— 这是第 7 轮失败模式：")
                print("        表面看是「校验脚本抓不出缺陷」，实际是缺陷没注入。")
                return 3
            print("[2] 注入生效          文件指纹已变化")

            # 断言 2：校验必须报错
            rc1 = run_verify()
            print(f"[3] 污染状态校验      退出码 {rc1}")
            if rc1 == 0:
                print("    [F] 校验对污染返回 0 —— 断言确实抓不到该缺陷。")
                return 3

        finally:
            shutil.copy2(backup, checklist)

        # 断言 3：还原后必须通过
        if fingerprint(checklist) != before_fp:
            print("    [F] 还原后指纹不一致，文件未恢复原状。")
            return 3
        rc2 = run_verify()
        print(f"[4] 还原状态校验      退出码 {rc2}")
        if rc2 != 0:
            print("    [F] 还原后仍不通过 —— 可能污染了其他内容。")
            return 3

    print("-" * 60)
    print("通过：该校验脚本的反向注入有效。")
    print("      （有效 ≠ 数据正确。内容正确性靠逐条人工核对 + 留痕。）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
