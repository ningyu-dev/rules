# 校验脚本

检查规则库是否符合 schema，以及是否违反三条硬约束。

## 用法

```bash
python scripts/validate.py
python scripts/validate.py --strict    # 未复核的条目视为错误
```

## 检查项

| 检查 | 说明 | 级别 |
|---|---|---|
| schema 校验 | 每条规则符合 `schema/rule.schema.json` | error |
| 强制等级缺失 | 强条未标 `mandatory_level` | error |
| 条文说明被误用 | `content_type=explanation` 却带了 `comparator`/`value` | error |
| 溯源缺失 | `provenance.page` 缺失或 `extracted_by` 为空 | error |
| AI 录入未复核 | `extracted_by=ai_assisted` 但无 `verified_by` | warn（strict 下为 error） |
| 版本缺失 | `standard_year` 缺失 | error |
| 阈值不合理 | 数值型阈值为 0 或负数 | warn |
| 重复 rule_id | 同一条文被录入多次 | error |
| 失效引用 | `exceptions.clause_ref` 指向不存在的规则 | warn |

## 为什么校验脚本要独立于 core

规则库必须能在没有任何计算代码的情况下独立验证。如果校验逻辑依赖 core，就无法区分「规则错了」和「计算错了」。

详见 `docs/DESIGN.md` 的 D-001。
