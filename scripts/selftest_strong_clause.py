#!/usr/bin/env python3
"""check_strong_clause.py 的反向注入自检（D-010）。

**为什么这个自检非做不可**
该检查器第一版就栽过一次：只归一化了规则一侧的标准号，清单键里还带空格，
于是 32 条一条没比，输出「库内落在清单覆盖范围内的标准：无」——
**看着是通过，实则空跑**。这类失败没有任何报错，只能靠注入来暴露。

三个错误码各注入一次，每次断言：
  1. 注入真的改变了文件（前后指纹不同）
  2. 污染后必须新增**恰好 1 条**对应错误码，且指向被注入的 rule_id
  3. 还原后指纹与注入前一致
  4. 还原后该错误码计数回到基线

用法：
    python scripts/selftest_strong_clause.py
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
CHECKER = ROOT / "scripts" / "check_strong_clause.py"

# 取自 GB 55020-2021 附件 2 第 1 项（GB 50015-2019 已废止强条），
# 与库内实际条号不重叠，因此注入不会与真实数据混淆。
ABOLISHED_CLAUSE = "3.1.2"
# 库内确有的、不在废止清单内的条号（第 5 章 0 条强条）
LIVE_CLAUSE = "5.2.11"


class SelfTestFailure(Exception):
    pass


def fingerprint(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_checker() -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(CHECKER)],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def count_code(text: str, code: str) -> int:
    return len(re.findall(rf"\[{code}\]", text))


def pick_victim() -> tuple[pathlib.Path, list[dict], int]:
    for path in sorted(DRAFTS.glob("_draft_*.json")):
        rules = json.loads(path.read_text(encoding="utf-8"))
        for i, r in enumerate(rules):
            std = str(r.get("standard", "")).replace(" ", "")
            if std == "GB50015" and r.get("standard_year") == 2019:
                return path, rules, i
    raise SelfTestFailure("库内找不到 GB 50015-2019 条目，无法注入")


def main() -> int:
    print("=" * 62)
    print("check_strong_clause.py · 反向注入自检")
    print("=" * 62)
    try:
        return _run()
    except SelfTestFailure as e:
        print(f"\n    [F] 自检失败：{e}")
        return 3
    except Exception as e:  # noqa: BLE001
        print(f"\n    [F] 自检意外异常：{type(e).__name__} {e}")
        return 4


def _run() -> int:
    target, rules, idx = pick_victim()
    victim = rules[idx]["rule_id"]

    rc0, out0 = run_checker()
    base = {c: count_code(out0, c) for c in ("E100", "E101", "E102")}
    print(f"目标文件：{target.name}")
    print(f"注入对象：{victim}（当前 clause={rules[idx].get('clause')}）")
    print(f"\n[1] 基线               退出码 {rc0}，"
          + " ".join(f"{k}={v}" for k, v in base.items()))
    if rc0 != 0:
        print("    [F] 基线不为通过，无法判断增量。先修基线。")
        return 3

    cases = [
        ("E100", "标为 strong_clause 且条号在废止清单内",
         {"mandatory_level": "strong_clause", "clause": ABOLISHED_CLAUSE}),
        ("E101", "pending 意图恢复为强条且条号在废止清单内",
         {"mandatory_level": "recommended", "clause": ABOLISHED_CLAUSE,
          "mandatory_level_pending": {"intended_level": "strong_clause",
                                      "reason": "自检注入"}}),
        ("E102", "标为 strong_clause 但条号不在该标准强条全集内",
         {"mandatory_level": "strong_clause", "clause": LIVE_CLAUSE}),
    ]

    with tempfile.TemporaryDirectory() as td:
        backup = pathlib.Path(td) / target.name
        shutil.copy2(target, backup)
        before_fp = fingerprint(target)

        try:
            for step, (code, desc, patch) in enumerate(cases, start=2):
                rules = json.loads(backup.read_text(encoding="utf-8"))
                for k, v in patch.items():
                    rules[idx][k] = v
                target.write_text(
                    json.dumps(rules, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")

                if fingerprint(target) == before_fp:
                    print(f"    [F] {code} 注入未改变文件，后续「通过」不可采信。")
                    return 3

                rc1, out1 = run_checker()
                inc = count_code(out1, code) - base[code]
                ok = (inc == 1 and rc1 == 1
                      and victim in out1)
                print(f"[{step}] 注入 {code}（{desc}）")
                print(f"       退出码 {rc1}，{code} 增量 = {inc}，"
                      f"指向被注入条目 = {victim in out1}")
                if not ok:
                    print(f"    [F] {code} 应新增恰好 1 条并指向 {victim}。"
                          f"检查器未按预期生效。")
                    return 3

                shutil.copy2(backup, target)
                if fingerprint(target) != before_fp:
                    print("    [F] 还原后指纹不一致。")
                    return 3

        finally:
            shutil.copy2(backup, target)

        rc2, out2 = run_checker()
        back = {c: count_code(out2, c) for c in base}
        print(f"\n[5] 还原状态校验       退出码 {rc2}，"
              + " ".join(f"{k}={v}" for k, v in back.items()))
        if back != base:
            print(f"    [F] 还原后计数未回到基线 {base}，实际 {back}。")
            return 3

    print("-" * 62)
    print("通过：三个错误码的反向注入均有效。")
    print("      （有效 ≠ 数据正确。只覆盖「公告已明确列号」的废止。）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
