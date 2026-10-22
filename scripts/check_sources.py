#!/usr/bin/env python3
"""给排水标准全景登记表的完整性检查、分类汇总与核对到期提醒。

为什么需要这个脚本：规则库的可靠性最终取决于「标准是不是还现行」，
而这件事没有任何自动判据——公告必须人读。脚本能做三件：

  1. 结构检查：渠道引用、检索式、状态取值、名称是否已核
  2. 分类汇总：按门类 A~N 出「登记数 / 本产品范围内 / 已入库」三列
  3. 交叉核对：库里的每条规则，其标准是否都在登记表中；登记表中的
     「已入库」是否为 0 —— 两个方向都要看，只查一边会漏

它**不能**判断标准是否现行。任何声称「跑完脚本即完成现行性核对」的说法，
与「校验通过 = 数据正确」是同一个错误（见 docs/COLLABORATION.md）。

用法：
    python scripts/check_sources.py               # 本地检查 + 汇总
    python scripts/check_sources.py --online      # 额外探测渠道可达性
    python scripts/check_sources.py --days 60     # 自定义超期阈值
    python scripts/check_sources.py --unverified  # 只列名称/编号未核的条目
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "sources" / "standards.json"
DRAFTS = ROOT / "rules" / "building_rain"

VALID_STATUS = {"current", "presumed", "pending_verify", "abolished", "partial_abolished", "unknown"}
STALE_DAYS = 90


def load_registry() -> dict:
    if not REGISTRY.exists():
        raise SystemExit(f"找不到信源登记表：{REGISTRY}")
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def library_counts() -> Counter:
    """按 standard 字段统计库内条目数。以文件实际内容为准，不采信登记表自述。"""
    counts: Counter = Counter()
    if not DRAFTS.exists():
        return counts
    for path in sorted(DRAFTS.glob("_draft_*.json")):
        for rule in json.loads(path.read_text(encoding="utf-8")):
            counts[rule.get("standard")] += 1
    return counts


def check_structure(data: dict) -> list[str]:
    errors: list[str] = []
    channels = data.get("channels") or []
    standards = data.get("standards") or []
    taxonomy = {t.get("id") for t in (data.get("taxonomy") or [])}

    if not channels:
        errors.append("channels 为空：没有任何信源渠道")
    if not standards:
        errors.append("standards 为空：没有登记任何标准")

    channel_ids = [c.get("id") for c in channels]
    if len(channel_ids) != len(set(channel_ids)):
        errors.append("channels 的 id 有重复")
    known_ch = set(channel_ids)

    seen: set[str] = set()
    for s in standards:
        sid = s.get("id") or "<缺 id>"
        if sid in seen:
            errors.append(f"standards 的 id 重复：{sid}")
        seen.add(sid)

        if not s.get("standard"):
            errors.append(f"{sid} 缺 standard")
        if not s.get("name"):
            errors.append(f"{sid} 缺 name")
        if s.get("status") not in VALID_STATUS:
            errors.append(f"{sid} 的 status=`{s.get('status')}` 不在 {sorted(VALID_STATUS)}")
        if s.get("group") not in taxonomy:
            errors.append(f"{sid} 的 group=`{s.get('group')}` 不在 taxonomy 内")
        for ref in s.get("sources") or []:
            if ref not in known_ch:
                errors.append(f"{sid} 引用了不存在的渠道：{ref}")
        if not s.get("sources"):
            errors.append(f"{sid} 没有登记任何获取渠道，等于无从核对")
    return errors


def parse_date(value) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def main() -> int:
    online = "--online" in sys.argv
    only_unverified = "--unverified" in sys.argv
    structure_only = "--structure-only" in sys.argv
    days = STALE_DAYS
    if "--days" in sys.argv:
        try:
            days = int(sys.argv[sys.argv.index("--days") + 1])
        except (IndexError, ValueError):
            print("--days 需要一个整数参数")
            return 2

    data = load_registry()
    errors = check_structure(data)
    if errors:
        print("=" * 66)
        print("信源登记表 · 结构错误")
        print("=" * 66)
        for e in errors:
            print(f"  ERROR {e}")
        return 2

    channels = {c["id"]: c for c in data["channels"]}
    standards = data["standards"]
    taxonomy = data["taxonomy"]
    today = dt.date.today()
    lib = library_counts()

    if only_unverified:
        return report_unverified(standards, taxonomy)

    # ---- 分类汇总 ----
    # 计数口径：一个标准号可能在表里出现两次（现行 + 已废止），
    # 库内条目只能算给现行那一条，否则会重复计数。故先建
    # standard → group 的映射，且跳过 abolished。
    std_group: dict[str, str] = {}
    for s in standards:
        if s.get("status") == "abolished":
            continue
        std_group.setdefault(s["standard"], s.get("group"))

    lib_by_group: Counter = Counter()
    for std, n in lib.items():
        g = std_group.get(std)
        if g:
            lib_by_group[g] += n

    print("=" * 66)
    print("给排水标准全景 · 分类汇总")
    print("=" * 66)
    print(f"{'门类':4s} {'名称':34s} {'登记':>4s} {'范围内':>5s} {'已入库':>5s}")
    print("-" * 66)
    total = in_scope = in_lib = 0
    for t in taxonomy:
        items = [s for s in standards if s.get("group") == t["id"]]
        sc = sum(1 for s in items if s.get("in_scope"))
        lib_n = lib_by_group.get(t["id"], 0)
        total += len(items)
        in_scope += sc
        in_lib += lib_n
        print(f"{t['id']:4s} {t['name'][:32]:34s} {len(items):>4d} {sc:>5d} {lib_n:>5d}")
    print("-" * 66)
    print(f"{'合计':4s} {'':34s} {total:>4d} {in_scope:>5d} {in_lib:>5d}")
    print(f"\n口径：登记=按标准计（现行与已废止分别计一次）；范围内=in_scope 为 true 的标准数；"
          f"已入库=各标准在 _draft_*.json 中的条目数之和（{in_lib} 条），"
          "同一标准号只算给现行版本。")

    # ---- 两个方向的交叉核对 ----
    registered = {s["standard"] for s in standards}
    # 工程经验条目没有标准号，是已知的第五类，不属未登记
    known_no_standard = {"无规范出处"}
    unknown = {std: n for std, n in lib.items()
               if std and std not in registered and std not in known_no_standard}
    if unknown:
        print("-" * 66)
        print("库内有条目、但标准未在信源表登记（出处不可控，不得投产）：")
        for std, n in sorted(unknown.items(), key=lambda x: -x[1]):
            print(f"  {std:24s} {n:>3d} 条")
    no_std = sum(n for std, n in lib.items() if std in known_no_standard)
    if no_std:
        print(f"  另有工程经验条目 {no_std} 条无标准出处（EP-），按 reference + requires_human 处置，"
              "不参与信源登记。")

    # ---- 核对状态 ----
    print("-" * 66)
    never, stale, fresh = [], [], []
    for s in standards:
        last = parse_date(s.get("last_checked"))
        if last is None:
            never.append(s)
            continue
        age = (today - last).days
        (stale if age > days else fresh).append((s, age))

    print(f"核对状态：从未核对 {len(never)} 本 / 超期 {len(stale)} 本 / 在期内 {len(fresh)} 本"
          f"（阈值 {days} 天）")
    if stale:
        for s, age in stale:
            print(f"  超期 {s['standard']:20s} 距上次 {age} 天（{s.get('last_checked')}）")

    # ---- 名称未核 ----
    unverified = [s for s in standards if not s.get("name_verified")]
    if unverified:
        print("-" * 66)
        print(f"名称/编号未经官方确认：{len(unverified)} 本（此状态下不得引用其条文）")
        for s in unverified:
            print(f"  {s['standard']:20s} {s['name'][:34]:36s} {s['status']}")

    # ---- 状态分布 ----
    print("-" * 66)
    sc = Counter(s.get("status") for s in standards)
    print("状态分布：" + "  ".join(f"{k}={v}" for k, v in sorted(sc.items())))
    print("  current=已核现行   presumed=按常识判断现行但未核公告  "
          "pending_verify=状态待核  abolished=已废止")

    if online:
        print("-" * 66)
        print("渠道可达性探测（只报告，不写回登记表）：")
        for cid, c in channels.items():
            url = c.get("url")
            if not url:
                print(f"  {cid:16s} 无 URL（{c.get('type')}）")
                continue
            print(f"  {cid:16s} {probe(url):28s} {url}")

    print("-" * 66)
    print("注意：本脚本只查『该登记的都登记了没有、多久没查』，")
    print("      **不能**判断标准是否现行。现行性只能靠公告四查（docs/信源与更新机制.md §二）。")
    if structure_only:
        # CI 用：结构成立即可放行。核对到期是待办提示，不是缺陷，
        # 若让它阻断 CI，红色会变成没人看的背景色。
        return 0
    if never or stale:
        print(f"\n待办：{len(never) + len(stale)} 本需要走四查。")
        return 1
    return 0


def report_unverified(standards: list[dict], taxonomy: list[dict]) -> int:
    group_name = {t["id"]: t["name"] for t in taxonomy}
    rows = [s for s in standards if not s.get("name_verified")]
    print("=" * 66)
    print(f"名称/编号未核清单（{len(rows)} 本）")
    print("=" * 66)
    print("此状态下只能保留占位，不得录入条文。核清后把 name_verified 改 true。")
    for s in sorted(rows, key=lambda x: (x.get("group"), x["standard"])):
        print(f"  [{s.get('group')}] {group_name.get(s.get('group'),'?'):22s} "
              f"{s['standard']:22s} {s['name'][:30]}")
    return 0


def probe(url: str) -> str:
    req = urllib.request.Request(url, method="HEAD",
                                 headers={"User-Agent": "ningyu-rules-source-check/0.2"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}（可能禁 HEAD）"
    except Exception as e:  # noqa: BLE001 网络原因多样，统一报类型
        return f"不可达（{type(e).__name__}）"


if __name__ == "__main__":
    raise SystemExit(main())
