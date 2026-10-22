# 校验脚本

检查规则库是否符合 schema，以及是否违反三条硬约束。

## 用法

```bash
python scripts/validate.py                   # 生产库
python scripts/validate.py --strict          # 未复核的条目视为错误
python scripts/validate.py --include-samples # 连草稿与 fixture 一起校验
python scripts/validate.py --drafts-only     # 只查 _draft_*.json（CI 用）

python scripts/verify_checklist.py           # 清单与草稿一一对应
python scripts/selftest_validate.py          # 证明 enum 校验真的在校验
python scripts/selftest_injection.py         # 证明清单校验真的在校验
python scripts/check_sources.py              # 信源登记与核对到期
python scripts/migrate_lookup_tables.py      # lookup_table 临时结构迁移（一次性）
python scripts/apply_source_check.py         # 公告四查结论回写（一次性）

python scripts/archive_announcements.py --apply          # 按登记表归档公告原文
python scripts/archive_pdf.py <id> <URL> --type 官方     # 归档正文 PDF（git 忽略）
python scripts/archive_pdf.py <id> --from-local <文件>   # 人工下载后归档
python scripts/archive_pdf.py <id> --stub                # 未取得正文时也写记录
python scripts/archive_pdf.py <id> --check               # 校验本地 PDF 与哈希一致
python scripts/audit_archive.py                          # 归档台账：正文从哪来、是否完整
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
| 未定义字段 | schema 未声明的顶层字段（E009）或嵌套字段（E013） | error |
| **枚举取值** | `mandatory_level` / `content_type` / `rule_type` / `category` 等取值不在枚举内（E011） | error |
| **类型** | 字段类型与 schema 不符（E012） | error |
| **嵌套必填** | 子对象缺必填字段（E014） | error |
| **镜像一致** | 顶层 `intended_level`/`normative_verb`/`blocks_production` 与 `mandatory_level_pending` 内不一致（E015） | error |
| **表体形态** | `lookup_table` 的 values / groups / entries 三者全空（E016） | error |
| **维度一致** | 列轴长度 ≠ 数值行长度（E017）——附录 G 错位 43% 就是这条没人查 | error |
| **结构约束** | `metrics` 为空、`minProperties` 不足、`anyOf` 全不满足（E018） | error |
| 临时字段 | `_` 前缀字段存在于正式结构内，投产前须清除（W008） | warn |

**最后五行是 2026-10-22 补的。** 在此之前脚本只做 `pattern` 与 `additionalProperties` 两类，不校验 `enum` —— 而 `mandatory_level` 唯一的机器可读约束就是 enum。结果是 `tag_blocking.py` 把字段名当哨兵值写进枚举字段，36 条规则变成非法取值，校验一路绿灯。见 `docs/DESIGN.md` D-011。

## 为什么校验脚本要独立于 core

规则库必须能在没有任何计算代码的情况下独立验证。如果校验逻辑依赖 core，就无法区分「规则错了」和「计算错了」。

详见 `docs/DESIGN.md` 的 D-001。

## 自检脚本为什么必需

`validate.py` 通过只说明"已知的坑没再踩"，不说明它覆盖了 schema。`selftest_validate.py` 向草稿注入一个非法枚举值，断言必须新增**恰好 1 条** E011、且指向被注入的 rule_id；注入前后比对文件指纹，还原后计数回到基线。这是 D-010 的直接应用——**注入没生效时，校验会因为"本来就没问题"而报通过**。

