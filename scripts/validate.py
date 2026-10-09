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
import re
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

    page = prov.get("page")
    if page is None or page == "":
        rep.add(Issue("error", "E003", path, "provenance.page 缺失"))
    elif page == 0:
        # 0 表示待补，是合法状态（草稿阶段常态），仅告警不阻断。
        # 绝不能编造页码；复核时必须填真实页码。
        rep.add(Issue("warn", "W006", path,
                      "provenance.page 为 0（待补），复核时须填真实页码"))

    extracted = prov.get("extracted_by")
    if not extracted:
        rep.add(Issue("error", "E003", path, "provenance.extracted_by 缺失"))
    elif extracted == "ai_assisted" and not prov.get("verified_by"):
        level = "error" if strict else "warn"
        rep.add(Issue(level, "W001", path,
                      "AI 辅助录入但未人工复核"))

    if not prov.get("verified_by") and strict:
        rep.add(Issue("error", "W002", path, "严格模式下要求全部条目已复核"))


def check_mandatory_level_consistency(rule: dict, path: str, rep: Report) -> None:
    """强制性等级与措辞的一致性检查。

    规范用词直接决定等级，不可凭印象填写：
      「必须/严禁/不应/不得」  -> strong_clause 或 mandatory_general_code
      「宜/不宜」             -> recommended
    把推荐级标成强条会让用户误以为必须遵守，是最危险的一类错误：
    新人照抄示例会把软约束做成硬约束。
    """
    if rule.get("content_type") != "clause":
        return

    stmt = rule.get("statement") or ""
    level = rule.get("mandatory_level")

    # 措辞含「宜」但标为强条 → 拔高
    if level in ("strong_clause", "mandatory_general_code"):
        if any(w in stmt for w in ("宜为", "宜按", "宜取", "宜在", "不宜")):
            rep.add(Issue("error", "E007", path,
                          f"statement 用「宜」但 mandatory_level={level}："
                          "推荐级被拔高为强条，会误导用户"))


def check_blocking_marked(rule: dict, path: str, rep: Report) -> None:
    """阻断标记的规则不得留在生产目录。

    mandatory_level_pending 表示该规则的真实强制性等级待定
    （schema 缺 clause 档导致无法准确表达）。这类规则在 schema
    改造完成前禁止投产，若混入生产目录会被当作可用的软约束。

    历史上出现过成员声称已加阻断标记但实际未写入的情况，
    因此这里以文件实际内容为准，不采信任何自述。
    """
    if rule.get("mandatory_level") != "mandatory_level_pending":
        return

    is_production = not (
        path.replace("\\", "/").split("/")[-1].startswith("_")
        or "/tests/" in path.replace("\\", "/")
    )
    if is_production:
        rep.add(Issue("error", "E008", path,
                      "阻断标记规则（mandatory_level_pending）"
                      "不得置于生产目录："
                      f"{rule.get('rule_id')}"))


def check_requires_human_flag(rule: dict, path: str, rep: Report) -> None:
    """软判断规则必须显式标 requires_human。

    规范无条文依据、依赖工程经验的规则，若未标记则会被当作
    可自动校验的硬约束，绕过用户确认。
    """
    level = rule.get("mandatory_level")
    if level in ("engineering_practice", "reference"):
        if "requires_human" not in rule:
            rep.add(Issue("warn", "W007", path,
                          f"mandatory_level={level} 但未标 requires_human："
                          "该类规则须显式标注是否需人工确认"))


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


def check_schema_patterns(rule: dict, path: str, rep: Report, schema: dict,
                          undefined_seen: set[str]) -> None:
    """执行 schema 中的 pattern 与 additionalProperties 约束。

    此前本脚本只比对 required 字段列表，不执行 pattern 与
    additionalProperties，因此「31 条 rule_id 不合规」这类问题
    查不出来——草稿看起来完全合规。这是 D-009/D-010 同源的盲区：
    校验层自己少查了东西，却报「通过」。

    不引外部依赖（jsonschema），只手写这两类约束——它们是本项目
    实际用到的全部。schema 若日后引入 draft-07 其他关键字，需相应
    扩展本函数。

    undefined_seen 收集未定义字段名，用于末尾汇总——大量条目重复
    报同一个缺失字段会淹没输出。
    """
    props: dict = schema.get("properties", {})
    additional_allowed = schema.get("additionalProperties", True)

    # 1. additionalProperties: false —— 拒绝 schema 未定义的字段
    if additional_allowed is False:
        for key in rule:
            if key not in props and not key.startswith("_"):
                undefined_seen.add(key)
                rep.add(Issue("error", "E009", path,
                              f"出现 schema 未定义的字段 `{key}`"
                              "（additionalProperties=false）"))

    # 2. pattern —— 正则约束（如 rule_id 格式）
    for key, spec in props.items():
        pattern = spec.get("pattern") if isinstance(spec, dict) else None
        value = rule.get(key)
        if pattern and isinstance(value, str) and not re.match(pattern, value):
            rep.add(Issue("error", "E010", path,
                          f"`{key}` = `{value}` 不匹配 pattern: {pattern}"))


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
    undefined_seen: set[str] = set()
    for path, rule in rules:
        check_required(rule, path, rep)
        check_content_type(rule, path, rep)
        check_provenance(rule, path, rep, strict)
        check_version(rule, path, rep)
        check_numeric_value(rule, path, rep)
        check_duplicate(seen, rule, path, rep)
        check_exception_refs(rule, path, known, rep)
        check_mandatory_level_consistency(rule, path, rep)
        check_requires_human_flag(rule, path, rep)
        check_blocking_marked(rule, path, rep)
        check_schema_patterns(rule, path, rep, schema, undefined_seen)

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

    if undefined_seen:
        print("-" * 60)
        print(f"schema 缺失定义：{len(undefined_seen)} 个字段被使用但未定义")
        for f in sorted(undefined_seen):
            print(f"  · {f}")
        print("  → 需扩展 schema（对应 S-1/S-3/S-4），否则 additionalProperties=false 会拒绝这些条目")

    print("-" * 60)
    if rep.checked == 0:
        # 0 条不能报「通过」。必须区分两种成因：
        #   a) 规则库确实为空
        #   b) 条目存在但被过滤条件全部排除
        # 后者是假阳性来源，会让人误以为草稿已通过校验。
        if include_samples:
            print("未找到任何条目（含样本模式）。请检查 rules/ 目录。")
        else:
            print("规则库为空 —— 本次未校验任何条目。")
            print("注意：以下情况也会导致此结果，请勿误认为校验通过：")
            print("  · 条目文件均以下划线 _ 开头（被当作测试样本排除）")
            print("  · 条目文件位于 tests/ 目录（被排除）")
            print("  · rules/ 目录下没有 .json 文件")
            print("草稿请用 --include-samples 校验。")
        return 3

    if rep.errors:
        print(f"不通过：{len(rep.errors)} 个错误，{len(rep.warnings)} 个警告")
        return 1
    if rep.warnings:
        print(f"通过（有警告）：{len(rep.warnings)} 个警告")
        return 0
    print(f"通过：{rep.checked} 条全部合规")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
