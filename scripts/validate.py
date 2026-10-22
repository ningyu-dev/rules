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
    rule_id: str | None = None


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


def load_rules(include_samples: bool = False, drafts_only: bool = False) -> list[tuple[str, dict]]:
    """加载生产规则。

    排除 _ 前缀文件与 tests/ 目录：那里存放故意违规的测试样本，
    不是生产数据。早期版本用 rglob("*.json") 扫全目录，导致测试
    样本被当生产规则校验，还污染 known 集合使 W005 失效。

    include_samples=True 时纳入样本，仅用于验证检查项本身是否生效。
    drafts_only=True 时只读 _draft_*.json —— 草稿结构必须干净，
    而 fixture 本来就该报错，两者混在一起时退出码无法表达「草稿是否有问题」。
    """
    out: list[tuple[str, dict]] = []
    if not RULES_DIR.exists():
        return out

    for path in sorted(RULES_DIR.rglob("*.json")):
        rel = path.relative_to(RULES_DIR)
        if drafts_only:
            if not path.name.startswith("_draft_"):
                continue
        else:
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


def check_lookup_table(rule: dict, path: str, rep: Report) -> None:
    """查表的形态与维度一致性。

    三条断言，对应本项目真实踩过的坑：

    E016 三种形态（矩阵 / 分组 / 行键）至少一种非空。
         曾为塞进旧的 rows/columns/values 而伪造公共轴，把三种互不对齐的
         管材规格硬并成一根 columns，导致 De110 查表得 18.30（真实 12.80），
         高估 43% → 立管选小 → 溢流。

    E017 列轴长度必须等于每个数值行的长度。
         附录 G 那次错位的直接原因就是这一条无人校验：塑料管 13 档塞进
         7 列，后 6 档静默丢失。

    E018 行键表的 metrics 不得为空——空的 metrics 等于一行只有名字没有内容。
    """
    if rule.get("rule_type") != "lookup_table":
        return

    lt = rule.get("lookup_table")
    if not isinstance(lt, dict):
        rep.add(Issue("error", "E016", path,
                      "rule_type=lookup_table 但缺少 lookup_table 对象"))
        return

    forms = {
        "values": lt.get("values"),
        "groups": lt.get("groups"),
        "entries": lt.get("entries"),
    }
    nonempty = [k for k, v in forms.items() if isinstance(v, list) and v]
    if not nonempty:
        rep.add(Issue("error", "E016", path,
                      "lookup_table 未提供任何非空表体：values / groups / entries 三者至少要有一种"))

    # 矩阵形态的维度一致
    cols = lt.get("columns") or []
    rows = lt.get("rows") or []
    vals = lt.get("values") or []
    if isinstance(vals, list) and vals:
        if cols and any(isinstance(r, list) and len(r) != len(cols) for r in vals):
            widths = sorted({len(r) for r in vals if isinstance(r, list)})
            rep.add(Issue("error", "E017", path,
                          f"values 行宽 {widths} 与 columns 长度 {len(cols)} 不一致："
                          "列轴与数值会错位，查表结果不可用"))
        if rows and len(rows) != len(vals):
            rep.add(Issue("error", "E017", path,
                          f"rows 长度 {len(rows)} 与 values 行数 {len(vals)} 不一致"))

    # 分组形态：每组各自对齐，不得跨组共用列轴
    for group in lt.get("groups") or []:
        if not isinstance(group, dict):
            continue
        gkey = group.get("key", "?")
        gcols = group.get("columns") or []
        gvals = group.get("values") or []
        if gcols and gvals and any(isinstance(r, list) and len(r) != len(gcols) for r in gvals):
            widths = sorted({len(r) for r in gvals if isinstance(r, list)})
            rep.add(Issue("error", "E017", path,
                          f"分组 `{gkey}` 的 values 行宽 {widths} 与本组 columns 长度 "
                          f"{len(gcols)} 不一致：该组规格与数值会错位"))

    # 行键形态：metrics 不得为空
    for entry in lt.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        if not entry.get("metrics"):
            rep.add(Issue("error", "E018", path,
                          f"行键 `{entry.get('key', '?')}` 的 metrics 为空："
                          "只有类别名没有指标，该行不可计算"))


def check_pending_consistency(rule: dict, path: str, rep: Report) -> None:
    """待定级信息的内部一致性。

    顶层 intended_level / normative_verb / blocks_production 是
    mandatory_level_pending 对象内同名字段的镜像。两者一旦漂移，
    检索与渲染就会看到两套结论——第 6 轮「同一数字三处不同」的同型。
    """
    pend = rule.get("mandatory_level_pending")
    mirror_keys = ("intended_level", "normative_verb", "blocks_production")

    if not isinstance(pend, dict):
        if any(k in rule for k in mirror_keys):
            rep.add(Issue("error", "E015", path,
                          "存在 intended_level/normative_verb/blocks_production 但缺少"
                          " mandatory_level_pending 对象：待定级信息不完整"))
        return

    for key in mirror_keys:
        if key in rule and rule[key] != pend.get(key):
            rep.add(Issue("error", "E015", path,
                          f"顶层 {key}=`{rule[key]}` 与 mandatory_level_pending.{key}="
                          f"`{pend.get(key)}` 不一致"))

    if pend.get("blocks_production") is not True:
        rep.add(Issue("warn", "W009", path,
                      "带待定级对象但 blocks_production 非 true："
                      "该条可能被当成可用规则"))

    if pend.get("safety_critical") is True and rule.get("safety_critical") is not True:
        rep.add(Issue("error", "E015", path,
                      "mandatory_level_pending.safety_critical 为 true，"
                      "但顶层未标 safety_critical"))


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
    """执行 schema 中本项目的全部约束：pattern / additionalProperties / enum / type / 嵌套 required。

    历史：本脚本最初只比对 required 字段列表，不执行 pattern 与
    additionalProperties，因此「31 条 rule_id 不合规」查不出来；
    补了这两类之后，又漏掉 enum —— 而 mandatory_level 唯一的机器可读
    约束就是 enum，于是 tag_blocking.py 把字段名当成哨兵值写进枚举字段，
    36 条规则（含 8 条安全关键）在内核里落入未定义分支，而校验一路绿灯。

    这说明「补了校验」不等于「校验覆盖了 schema」：校验器自己有没有覆盖
    全部约束，也需要被断言。见 D-011 与 scripts/selftest_validate.py。

    undefined_seen 收集未定义字段名，用于末尾汇总——大量条目重复
    报同一个缺失字段会淹没输出。
    """
    _check_node(rule, schema, rep, path, "$", undefined_seen, is_root=True)


_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "number": (int, float),
    "integer": int,
    "null": type(None),
}


def _type_ok(value, spec_type) -> bool:
    types = spec_type if isinstance(spec_type, list) else [spec_type]
    for t in types:
        py = _TYPE_MAP.get(t)
        if py is None:
            continue
        # bool 是 int 的子类，必须排除，否则 "value": true 会被当作合法数值
        if t in ("number", "integer") and isinstance(value, bool):
            continue
        if isinstance(value, py):
            return True
    return False


def _check_node(value, spec, rep: Report, path: str, locator: str,
                undefined_seen: set[str], is_root: bool = False) -> None:
    """按 schema 递归校验一个节点。只实现 schema 实际用到的关键字。"""
    if not isinstance(spec, dict):
        return

    # 1. type
    spec_type = spec.get("type")
    if spec_type and not _type_ok(value, spec_type):
        rep.add(Issue("error", "E012", path,
                      f"{locator} 类型不符：期望 {spec_type}，实际 {type(value).__name__}"))
        return  # 类型错则不再深入，避免连带噪音

    # 2. enum
    enum = spec.get("enum")
    if enum is not None and value not in enum:
        rep.add(Issue("error", "E011", path,
                      f"{locator} 取值 `{value}` 不在枚举内：{enum}"))

    # 3. pattern（仅对字符串）
    if isinstance(value, str):
        pattern = spec.get("pattern")
        if pattern and not re.match(pattern, value):
            rep.add(Issue("error", "E010", path,
                          f"{locator} = `{value}` 不匹配 pattern: {pattern}"))

    # 4. object
    if isinstance(value, dict):
        props: dict = spec.get("properties", {})
        patterns: dict = spec.get("patternProperties", {})
        additional = spec.get("additionalProperties", True)

        min_props = spec.get("minProperties")
        if isinstance(min_props, int) and len(value) < min_props:
            rep.add(Issue("error", "E018", path,
                          f"{locator} 至少需要 {min_props} 个字段，实际 {len(value)} 个"))

        for req in spec.get("required", []):
            # 根节点的 required 由 check_required / missing_schema 负责，
            # 这里只查嵌套对象，避免同一缺失被三条码重复报。
            if is_root:
                continue
            if req not in value:
                rep.add(Issue("error", "E014", path,
                              f"{locator} 缺少 schema 要求的字段 `{req}`"))

        for key, sub in value.items():
            child_loc = f"{locator}.{key}"
            if key in props:
                _check_node(sub, props[key], rep, path, child_loc, undefined_seen)
                continue
            matched = next((p for p in patterns if re.match(p, key)), None)
            if matched is not None:
                if key.startswith("_"):
                    rep.add(Issue("warn", "W008", path,
                                  f"{child_loc} 为临时/占位字段：投产前必须清除（D-011）"))
                _check_node(sub, patterns[matched], rep, path, child_loc, undefined_seen)
                continue
            if additional is False:
                if is_root:
                    undefined_seen.add(key)
                    rep.add(Issue("error", "E009", path,
                                  f"出现 schema 未定义的字段 `{key}`"
                                  "（additionalProperties=false）"))
                else:
                    rep.add(Issue("error", "E013", path,
                                  f"{child_loc} 是 schema 未定义的嵌套字段"
                                  "（additionalProperties=false）"))
            elif isinstance(additional, dict):
                _check_node(sub, additional, rep, path, child_loc, undefined_seen)

    # 5. array
    elif isinstance(value, list):
        items = spec.get("items")
        if isinstance(items, dict):
            for i, item in enumerate(value):
                _check_node(item, items, rep, path, f"{locator}[{i}]", undefined_seen)

    # 6. anyOf —— 任一支路通过即可。用于 metrics 值「标量 或 维度映射」两种形态
    any_of = spec.get("anyOf")
    if any_of:
        passed = False
        for branch in any_of:
            probe = Report()
            _check_node(value, branch, probe, path, locator, set())
            if not probe.errors:
                passed = True
                break
        if not passed:
            rep.add(Issue("error", "E018", path,
                          f"{locator} 不满足 anyOf 的任一形态（共 {len(any_of)} 支）"))



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
    drafts_only = "--drafts-only" in sys.argv
    rep = Report()

    if not SCHEMA_PATH.exists():
        print(f"找不到 schema：{SCHEMA_PATH}")
        return 2


    schema = load_schema()
    required_props = set(schema.get("required", []))

    rules = load_rules(include_samples=include_samples, drafts_only=drafts_only)
    rep.files = len({p for p, _ in rules})
    rep.checked = len(rules)

    # 先扫一遍已收录的 rule_id，供 exceptions 引用校验用
    known = {r.get("rule_id") for _, r in rules if r.get("rule_id")}

    seen: dict[str, str] = {}
    undefined_seen: set[str] = set()
    for path, rule in rules:
        n_err, n_warn = len(rep.errors), len(rep.warnings)
        check_required(rule, path, rep)
        check_content_type(rule, path, rep)
        check_provenance(rule, path, rep, strict)
        check_version(rule, path, rep)
        check_numeric_value(rule, path, rep)
        check_duplicate(seen, rule, path, rep)
        check_exception_refs(rule, path, known, rep)
        check_mandatory_level_consistency(rule, path, rep)
        check_lookup_table(rule, path, rep)
        check_pending_consistency(rule, path, rep)
        check_requires_human_flag(rule, path, rep)
        check_blocking_marked(rule, path, rep)
        check_schema_patterns(rule, path, rep, schema, undefined_seen)

        missing_schema = required_props - set(rule.keys())
        if missing_schema:
            rep.add(Issue("error", "E001", path,
                          f"缺失 schema 要求字段：{sorted(missing_schema)}"))

        # 给本轮新增的条目补 rule_id：一个文件含数十条时，
        # 「哪一条错了」比「哪个文件错了」更需要先回答。
        rid = rule.get("rule_id")
        for issue in rep.errors[n_err:] + rep.warnings[n_warn:]:
            if issue.rule_id is None:
                issue.rule_id = rid

    print("=" * 60)
    mode = "strict" if strict else "normal"
    if include_samples:
        mode += " +samples"
    if drafts_only:
        mode = "drafts-only" + (" +strict" if strict else "")
    print(f"规则库校验  模式：{mode}")
    print(f"文件 {rep.files} 个，条目 {rep.checked} 条")
    print("=" * 60)

    for issue in rep.errors:
        where = f"{issue.path}" + (f"  [{issue.rule_id}]" if issue.rule_id else "")
        print(f"  ERROR  [{issue.code}] {where}\n         {issue.message}")
    for issue in rep.warnings:
        where = f"{issue.path}" + (f"  [{issue.rule_id}]" if issue.rule_id else "")
        print(f"  WARN   [{issue.code}] {where}\n         {issue.message}")

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
