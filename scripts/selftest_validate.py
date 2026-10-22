#!/usr/bin/env python3
"""validate.py 的反向注入自检（D-010）。

背景：validate.py 补了 pattern 与 additionalProperties 之后，仍然不校验
enum —— 而 mandatory_level 唯一的机器可读约束就是 enum。结果是
tag_blocking.py 把字段名当作哨兵值写进枚举字段，36 条规则（含 8 条
安全关键）变成非法取值，校验一路绿灯。

「补了校验」不等于「校验覆盖了 schema」。因此对每一类新增约束，都必须
证明它真的会报错，且证明方式不能依赖肉眼：

  1. 注入确实改变了目标文件（比较前后指纹）
  2. 污染后必须新增恰好 1 条对应错误码，且指向被注入的 rule_id
  3. 还原后指纹必须与注入前一致
  4. 还原后错误计数必须回到基线

第 4 项是针对「注入没生效」的防呆：如果注入写到了别处、或写成了
schema 本来就拒绝的值，第 2 项会假通过，第 4 项会兜住。

用法：
    python scripts/selftest_validate.py
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
DRAFTS = ROOT / "rules" / "building_rain"
VALIDATE = ROOT / "scripts" / "validate.py"

# 注入值：与真实 bug 同型——把字段名当哨兵值写进枚举字段。
# 不用随机字符串，因为要证明的正是这一类取值会被枚举拦住。
INJECT_LEVEL = "mandatory_level_pending"


class SelfTestFailure(Exception):
    pass


def fingerprint(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_validate() -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(VALIDATE), "--include-samples"],
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def count_code(text: str, code: str) -> int:
    return len(re.findall(rf"\[{code}\]", text))


def main() -> int:
    print("=" * 60)
    print("validate.py · 反向注入自检（enum 约束）")
    print("=" * 60)
    try:
        return _run()
    except SelfTestFailure as e:
        print(f"\n    [F] 自检失败：{e}")
        print("        自检失败不等于校验脚本无效——先查注入种子是否与数据结构匹配。")
        return 3
    except Exception as e:  # noqa: BLE001 兜底，避免裸 traceback 淹没原因
        print(f"\n    [F] 自检意外异常：{type(e).__name__} {e}")
        return 4


def _run() -> int:
    drafts = sorted(DRAFTS.glob("_draft_*.json"))
    if not drafts:
        raise SelfTestFailure("未找到草稿文件，无法注入")

    target = drafts[0]
    rules = json.loads(target.read_text(encoding="utf-8"))
    if not rules:
        raise SelfTestFailure(f"{target.name} 为空，无法注入")
    victim = rules[0]["rule_id"]

    rc0, out0 = run_validate()
    base_e011 = count_code(out0, "E011")
    print(f"目标文件：{target.name}")
    print(f"注入对象：{victim}")
    print(f"\n[1] 基线              退出码 {rc0}，E011 = {base_e011}")

    with tempfile.TemporaryDirectory() as td:
        backup = pathlib.Path(td) / target.name
        shutil.copy2(target, backup)
        before_fp = fingerprint(target)

        try:
            rules[0]["mandatory_level"] = INJECT_LEVEL
            target.write_text(
                json.dumps(rules, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            # 断言 1：注入必须真的改变文件
            if fingerprint(target) == before_fp:
                print("    [F] 注入未改变文件 —— 注入没发生，后面的「通过」不可采信。")
                return 3
            print("[2] 注入生效          文件指纹已变化")

            # 断言 2：必须新增恰好 1 条 E011，且指向被注入的 rule_id
            rc1, out1 = run_validate()
            inc = count_code(out1, "E011") - base_e011
            print(f"[3] 污染状态校验      退出码 {rc1}，E011 增量 = {inc}")
            if inc != 1:
                print(f"    [F] E011 增量应为 1，实际 {inc} —— 枚举校验未按预期生效。")
                print("        可能是 check_schema_patterns 未递归到该字段，或 enum 读取路径变了。")
                return 3
            if INJECT_LEVEL not in out1 or victim not in out1:
                print("    [F] 报错未指向被注入的值或 rule_id —— 可能是另一条规则误报。")
                return 3

        finally:
            shutil.copy2(backup, target)

        # 断言 3：还原后指纹必须一致
        if fingerprint(target) != before_fp:
            print("    [F] 还原后指纹不一致，文件未恢复原状。")
            return 3

        # 断言 4：还原后计数必须回到基线
        rc2, out2 = run_validate()
        back = count_code(out2, "E011")
        print(f"[4] 还原状态校验      退出码 {rc2}，E011 = {back}")
        if back != base_e011:
            print(f"    [F] 还原后 E011 计数未回到基线 {base_e011}，实际 {back}。")
            return 3

    print("-" * 60)
    print("通过：enum 约束的反向注入有效。")
    print("      （有效 ≠ 数据正确。枚举合法不代表取值正确。）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
