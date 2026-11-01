# 建质函〔2016〕247 号 建筑工程设计文件编制深度规定（2016 年版） · 原文归档

> 本文件只记出处与获取方式，**不记本地是否已下载**——正文是否在手是每台机器
> 各自的运行时状态，写进版本库必然过期。本地有没有，跑 `audit_archive.py` 看。
> **官方附件是 Word（`.doc`），不是 PDF**：本目录没有 PDF，也没有 PDF 直链。

## 归档台账字段

（`scripts/audit_archive.py` 读取本表；下方「下载记录」是更细的流水，不参与解析。）

| 项 | 内容 |
|---|---|
| 来源页面 | https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2016/art_17339_229701.html |
| 正文附件直链 | https://www.mohurd.gov.cn/api-gateway/jpaas-web-server/front/document/download?fileUrl=YW5UzzlvCwcM%2FNHHX%2FtT6BJ6yM%2FAU1LVtmOVIvNjcuqxaLMLAlBp0EDqzYTeRbwV8%2FpHVW9vQZwVeUj7acXaYA1a8UpOukxMODRe3yE%2FKxEImsHJVa2Ppb2AB1n8j4Kc&fileName=%E3%80%8A%E5%BB%BA%E7%AD%91%E5%B7%A5%E7%A8%8B%E8%AE%BE%E8%AE%A1%E6%96%87%E4%BB%B6%E7%BC%96%E5%88%B6%E6%B7%B1%E5%BA%A6%E8%A7%84%E5%AE%9A%EF%BC%882016%E7%89%88%EF%BC%89%E3%80%8B+ |
| 下载方式 | 从通知页 HTML 的附件 `href` 取 `/api-gateway/…/document/download?…`，补域名后用 `curl -sSL` 跟随 302 取回官方 Word 附件（`application/msword`），**未转 PDF**（转制件不是官方件，会污染哈希口径） |
| 下载时间 | 2026-11-01 |
| 下载人 | 主理人（会话内由 AI 助手执行） |
| 来源类型 | 官方（正文原件为住建部门户网站 Word 附件） |
| 完整性 | 94 页（Word 文档属性 `Number of Pages`）；附件即通知所印发正文 |

## 文件

| 项 | 内容 |
|---|---|
| 文号 | 建质函〔2016〕247 号 |
| 名称 | 建筑工程设计文件编制深度规定（2016 年版） |
| 发布日期 | 2016-11-17 |
| 实施日期 | 2017-01-01 |
| 公告页 | https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2016/art_17339_229701.html |
| 文件 | `DEPTH-2016.doc`（官方 Word 附件，不是 PDF） |
| 大小 | 704,496 B |
| SHA-256 | `a055e81dbc6bb73dbf537a63df40d668dac49c7e3f75d5ae5ceea3f462095b7f` |

## 下载记录

| 日期 | 来源 | 文件 | 大小 | 校验 |
|---|---|---|---|---|
| 2026-11-01 | 通知页附件下载接口（302 → `/cms_files/filemanager/1150240553/attach/202411/W020210218021653.doc`） | DEPTH-2016.doc | 704,496 字节 | SHA-256 `a055e81d…`；Word 文档属性：94 页、14,130 字 |
| 2026-11-01 | 住建部通知页（官方） | announcement.html | 13,192 字节 | SHA-256 `2f95073b…`（见 `announcement.sha256`） |

## 公告副本

`announcement.html` 抓自住建部门户网站通知页（HTTP 200，**官方发布件**），用于核对文号、
发文日期、实施日期与附件形态：

- 文号：建质函〔2016〕247 号；索引号 000013338/2016-00318
- 发文日期 2016-11-17、实施日期 2017-01-01、「废止日期」为空（现行）
- 附件：「《建筑工程设计文件编制深度规定（2016版）》」，下载接口返回 `application/msword`

## 为什么没有 PDF

该文件的官方发布形态就是 **Word 文档**，门户网站没有提供 PDF 版。强行用本地工具把
`.doc` 转成 PDF 会产生一个「非官方、不可复现」的派生件，哈希也无法与官方原件对应，
所以本目录**不转、不写 PDF 直链**。需要 PDF 阅读时，自行把官方 `.doc` 转换即可；
`.doc` 原件按上表直链重新下载、用 SHA-256 `a055e81d…` 验明正身。

公式化的复现步骤：

```bash
# 1) 取通知页，从 HTML 取附件 href（/api-gateway/...document/download?fileUrl=...&fileName=...）
# 2) 补 https://www.mohurd.gov.cn 后下载，-L 跟随 302 到 .doc
curl -sSL '<正文附件直链>' -o DEPTH-2016.doc
shasum -a 256 DEPTH-2016.doc   # 应为 a055e81d...
```

## 用途边界

正文原件为住建部门户网站发布件（Word），可作为条文出处。
仍需注意：本文件只证明「拿到的是这一份」，**不证明条文数值已被核对**。
录入规则库时 `provenance.page` 必须逐条填真实页码，`verified_by` 必须有值。

## 权利说明

原文著作权归住房和城乡建设部所有。本项目只做结构化整理与引用，**不主张对原文的权利**，详见仓库根目录 `NOTICE.md`。
如本目录内容与官方版本不一致，以官方版本为准。
