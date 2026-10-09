#!/usr/bin/env python3
"""规则库校验脚本。

独立于 core 运行：规则库必须能在没有任何计算代码的情况下独立验证。
详见 docs/DESIGN.md 的 D-001。

用法：
    python scripts/validate.py
    python scripts/validate.py --strict
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "rule.schema.json"
RULES_DIR = ROOT / "rules"

REQUIRED_FIELDS = [
    "rule_id",
    "standard",
    "standard_year",
    "clause",
    "category",
    "content_type",
    "rule_type",
    "statement",
    "provenance",
]

NUMERIC_RULE_TYPES = {"numeric_threshold"}


@dataclass
class Issue:
    level: str          # error | warn | info
    code: str
    path: str
    message: str


@dataclass
class Report:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    checked: int = 0
    files: int = 0

    def add(self, issue: Issue) -> None:
        if issue.level == "error":
            self.errors.append(issue)
        else:
            self.warnings.append(issue)


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_rules(include_samples: bool = False) -> list[tuple[str, dict]]:
    """加载生产规则。

    排除 _ 前缀文件与 tests/ 目录：那里存放故意违规的测试样本，
    不是生产数据。早期版本用 rglob("*.json") 扫全目录，导致测试
    样本被当生产规则校验，还污染 known 集合使 W005 失效。

    include_samples=True 时纳入样本，仅用于验证检查项本身是否生效。
    """
    out: list[tuple[str, dict]] = []
    if not RULES_DIR.exists():
        return out

    for path in sorted(RULES_DIR.rglob("*.json")):
        rel = path.relative_to(RULES_DIR)
        # 测试样本：文件名以 _ 开头，或位于 tests/ 下
        is_sample = path.name.startswith("_") or rel.parts[0] == "tests"
        if is_sample and not include_samples:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        str_path = str(path.relative_to(ROOT))
        items = data if isinstance(data, list) else [data]
        for item in items:
            out.append((str_path, item))
    return out


def check_required(rule: dict, path: str, rep: Report) -> None:
    for f in REQUIRED_FIELDS:
        if f not in rule or rule[f] in (None, ""):
            rep.add(Issue("error", "E001", path, f"缺少必填字段 {f}"))


def check_content_type(rule: dict, path: str, rep: Report) -> None:
    """条文说明禁止携带可计算字段。

    这是三条硬约束之一。条文说明是给编制人员看的解释，
    一旦被当成强制要求去卡工程师，系统立刻失去可信度。
    """
    if rule.get("content_type") != "explanation":
        return
    for f in ("comparator", "value", "lookup_table", "formula"):
        if f in rule and rule[f] not in (None, ""):
            rep.add(Issue(
                "error", "E002", path,
                f"content_type=explanation 不得携带 {f}："
                "条文说明不可参与校验（D-004）",
            ))


def check_provenance(rule: dict, path: str, rep: Report, strict: bool) -> None:
    prov = rule.get("provenance")
    if not isinstance(prov, dict):
        return

    if not prov.get("page"):
        rep.add(Issue("error", "E003", path, "provenance.page 缺失"))

    extracted = prov.get("extracted_by")
    if not extracted:
        rep.add(Issue("error", "E003", path, "provenance.extracted_by 缺失"))
    elif extracted == "ai_assisted" and not prov.get("verified_by"):
        level = "error" if strict else "warn"
        rep.add(Issue(level, "W001", path,
                      "AI 辅助录入但未人工复核"))

    if not prov.get("verified_by") and strict:
        rep.add(Issue("error", "W002", path, "严格模式下要求全部条目已复核"))


def check_version(rule: dict, path: str, rep: Report) -> None:
    year = rule.get("standard_year")
    if year is None:
        rep.add(Issue("error", "E004", path,
                      "standard_year 缺失：规范会局部换版，版本隔离不可省（D-003）"))
    elif not isinstance(year, int) or not (1990 <= year <= 2100):
        rep.add(Issue("warn", "W003", path, f"standard_year 异常：{year}"))


def check_numeric_value(rule: dict, path: str, rep: Report) -> None:
    if rule.get("rule_type") not in NUMERIC_RULE_TYPES:
        return
    if rule.get("comparator") is None:
        rep.add(Issue("error", "E005", path,
                      "numeric_threshold 缺少 comparator"))
    value = rule.get("value")
    if isinstance(value, (int, float)) and value <= 0:
        rep.add(Issue("warn", "W004", path,
                      f"阈值非正数：{value}，请确认是否录错"))


def check_duplicate(seen: dict[str, str], rule: dict, path: str, rep: Report) -> None:
    rid = rule.get("rule_id")
    if not rid:
        return
    if rid in seen:
        rep.add(Issue("error", "E006", path,
                      f"rule_id 重复：{rid}（已出现于 {seen[rid]}）"))
    else:
        seen[rid] = path


def check_exception_refs(rule: dict, path: str, known: set[str], rep: Report) -> None:
    for exc in rule.get("exceptions") or []:
        ref = exc.get("clause_ref")
        if ref and ref not in known:
            rep.add(Issue("warn", "W005", path,
                          f"exceptions 引用了未收录条文：{ref}"))


def main() -> int:
    strict = "--strict" in sys.argv
    include_samples = "--include-samples" in sys.argv
    rep = Report()

    if not SCHEMA_PATH.exists():
        print(f"找不到 schema：{SCHEMA_PATH}")
        return 2

    schema = load_schema()
    required_props = set(schema.get("required", []))

    rules = load_rules(include_samples=include_samples)
    rep.files = len({p for p, _ in rules})
    rep.checked = len(rules)

    # 先扫一遍已收录的 rule_id，供 exceptions 引用校验用
    known = {r.get("rule_id") for _, r in rules if r.get("rule_id")}

    seen: dict[str, str] = {}
    for path, rule in rules:
        check_required(rule, path, rep)
        check_content_type(rule, path, rep)
        check_provenance(rule, path, rep, strict)
        check_version(rule, path, rep)
        check_numeric_value(rule, path, rep)
        check_duplicate(seen, rule, path, rep)
        check_exception_refs(rule, path, known, rep)

        missing_schema = required_props - set(rule.keys())
        if missing_schema:
            rep.add(Issue("error", "E001", path,
                          f"缺失 schema 要求字段：{sorted(missing_schema)}"))

    print("=" * 60)
    mode = "strict" if strict else "normal"
    if include_samples:
        mode += " +samples"
    print(f"规则库校验  模式：{mode}")
    print(f"文件 {rep.files} 个，条目 {rep.checked} 条")
    print("=" * 60)

    for issue in rep.errors:
        print(f"  ERROR  [{issue.code}] {issue.path}\n         {issue.message}")
    for issue in rep.warnings:
        print(f"  WARN   [{issue.code}] {issue.path}\n         {issue.message}")

    print("-" * 60)
    if rep.errors:
        print(f"不通过：{len(rep.errors)} 个错误，{len(rep.warnings)} 个警告")
        return 1
    if rep.warnings:
        print(f"通过（有警告）：{len(rep.warnings)} 个警告")
        return 0
    print("通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
