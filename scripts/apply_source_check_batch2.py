#!/usr/bin/env python3
"""公告四查第二批：把 4 本的核对结果写回 sources/standards.json。

本批对象与依据（全部为官方公告或含公告原文影印的出版方页面）：

| 标准 | 公告 | 实施日期 | 关键结论 |
|---|---|---|---|
| CJJ 142-2014 | 公告第 349 号 | **2014-09-01**（原记录 2014-10-01 错） | 强条 3.1.2/3.1.9/3.4.5 已被 GB 55020 附件 2 废止 |
| CJJ 127-2009 | 公告第 279 号 | 2009-09-01 | 强条 4.2.5/6.1.1 **不在**废止清单，仍有效 |
| CJJ/T 29-2010 | 公告第 840 号 | 2011-10-01 | 推荐性行标，无强条；废止 CJJ/T 29-98 |
| DEPTH-2016 | 建质函〔2016〕247 号 | 2017-01-01 | 现行；2016 版废止 2008 版 |

**为什么不直接改 JSON**
日期与公告号是要被引用的判据，写错会让审查基准整体偏移（合同签在
2014-09 至 2014-10 之间的项目会被误判为「未适用新版」）。所以走脚本，
并在写入前断言：原值确实是待修正的值、废止清单确实含/不含对应条号。

用法：
    python scripts/apply_source_check_batch2.py            # 只报告
    python scripts/apply_source_check_batch2.py --apply    # 写入
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REG = ROOT / "sources" / "standards.json"
ABOLISHED = ROOT / "sources" / "abolished_strong_clauses.json"

TODAY = "2026-10-24"
BY = "沈澄 给排水工程师"

UPDATES = {
    "CJJ142-2014": {
        "announcement_no": "住房和城乡建设部公告 第 349 号",
        "implemented": "2014-09-01",
        "status": "current",
        "last_checked": TODAY,
        "checked_by": BY,
        "evidence": "https://www.ccsn.org.cn/News/ShowInfo.aspx"
                    "?Guid=f275b2ce-0bd6-4199-bccf-d5a053543e64",
        "notes": "GB 50015-2019 5.2.37 明确指向。强条 3.1.2、3.1.9、3.4.5 已自 "
                 "2022-04-01 由 GB 55020-2021 附件 2 第 8 项废止强条属性（官方清单已核，"
                 "标准本体现行、条文照引）。**换版预警**：住建部办公厅 2024-04-28 发布"
                 "局部修订征求意见稿，修订内容含 87 型与虹吸雨水斗最大排水流量、"
                 "天沟（集水槽）宽度与深度最小尺寸、雨水总径流雨量计算公式——"
                 "正是本子域最依赖的几处数值。征求意见稿不得作依据，但须盯发布。"
                 "库内 0 条，是当前最大缺口。",
    },
    "CJJ127-2009": {
        "announcement_no": "住房和城乡建设部公告 第 279 号",
        "implemented": "2009-09-01",
        "status": "current",
        "last_checked": TODAY,
        "checked_by": BY,
        "evidence": "https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2009/art_17339_189322.html",
        "notes": "雨水立管用金属管时的依据。强条 4.2.5、6.1.1（公告原文逐条列出），"
                 "**不在** GB 55020-2021 附件 2 的 9 项废止清单内，强条属性仍有效。",
    },
    "CJJT29-2010": {
        "announcement_no": "住房和城乡建设部公告 第 840 号",
        "implemented": "2011-10-01",
        "status": "current",
        "last_checked": TODAY,
        "checked_by": BY,
        "evidence": "https://ebook.chinabuilding.com.cn/zbooklib/bookpdf/probation"
                    "?SiteID=1&bookID=56260",
        "notes": "雨水立管用塑料管时的伸缩节与支架间距依据。推荐性行业标准（CJJ/T），"
                 "无强条，故不在 GB 55020 废止清单内属正常。发布时废止 CJJ/T 29-98。"
                 "evidence 为中国建筑工业出版社的原文影印页（转载，含公告原文）。",
    },
    "DEPTH-2016": {
        "last_checked": TODAY,
        "checked_by": BY,
        "evidence": "https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2016/art_17339_229701.html",
        "notes": "适用范围含工业厂房、仓库。屋面雨水属建筑给排水，适用本版；"
                 "市政公用工程另有 2025 年版（2013 年版已于 2025-10-01 废止），"
                 "两者不得混用。计算书深度要求在此。官方页「废止日期」为空，现行有效；"
                 "2016 版发布时废止 2008 年版。",
    },
}


def verify(data: dict) -> list[str]:
    """写入前的硬断言。"""
    problems: list[str] = []
    by_id = {s["id"]: s for s in data["standards"]}
    abl = json.loads(ABOLISHED.read_text(encoding="utf-8"))
    keys = {i["key"]: i for i in abl["abolished"]}

    for sid in UPDATES:
        if sid not in by_id:
            problems.append(f"登记表缺 {sid}")

    # 断言 1：CJJ 142 的实施日期原值确实是待修正的 2014-10-01
    old = by_id.get("CJJ142-2014", {}).get("implemented")
    if old != "2014-10-01":
        problems.append(
            f"CJJ142-2014 实施日期原值为 {old!r}，与脚本假设的 2014-10-01 不符。"
            "可能已被他人改动，先核对再跑。")

    # 断言 2：废止清单必须含 CJJ 142-2014 的 3 条
    it = keys.get("CJJ 142-2014")
    if not it:
        problems.append("废止清单缺 CJJ 142-2014 项")
    elif it["clauses"] != ["3.1.2", "3.1.9", "3.4.5"]:
        problems.append(f"CJJ 142-2014 废止条号应为 3.1.2/3.1.9/3.4.5，实际 {it['clauses']}")

    # 断言 3：CJJ 127-2009 不得出现在废止清单里
    if "CJJ 127-2009" in keys:
        problems.append("CJJ 127-2009 出现在废止清单，与「强条仍有效」的结论冲突")

    # 断言 4：CJJ/T 29-2010 不得出现在废止清单里
    if "CJJ/T 29-2010" in keys:
        problems.append("CJJ/T 29-2010 出现在废止清单，与其「无强条」的结论冲突")

    return problems


def main() -> int:
    apply_mode = "--apply" in sys.argv
    data = json.loads(REG.read_text(encoding="utf-8"))
    problems = verify(data)

    print("=" * 68)
    print("公告四查第二批 · 回写")
    print("=" * 68)
    by_id = {s["id"]: s for s in data["standards"]}
    for sid, patch in UPDATES.items():
        cur = by_id[sid]
        print(f"\n{sid}  {cur['name']}")
        for k, v in patch.items():
            old = cur.get(k)
            if k == "notes":
                print(f"  notes      更新（{len(str(old or ''))} → {len(v)} 字）")
            elif old != v:
                print(f"  {k:18s} {old!r} → {v!r}")
            else:
                print(f"  {k:18s} 不变")

    if problems:
        print("\n" + "-" * 68)
        print("断言未通过，拒绝写入：")
        for p in problems:
            print("  -", p)
        return 1

    print("\n" + "-" * 68)
    print("断言通过：")
    print("  - CJJ 142 实施日期原值确为 2014-10-01（待修正）")
    print("  - 废止清单含 CJJ 142-2014 的 3.1.2/3.1.9/3.4.5")
    print("  - 废止清单不含 CJJ 127-2009 与 CJJ/T 29-2010")

    if not apply_mode:
        print("\n以上为报告。加 --apply 写入。")
        return 0

    for sid, patch in UPDATES.items():
        by_id[sid].update(patch)
    REG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"\n已写入 {REG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
