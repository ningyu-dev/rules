# GB 55020 建筑给水排水与节水通用规范 · 原文归档

> 本目录的 PDF **不进 git**（见仓库根 `.gitignore`）。
> 任何人按下列 URL 下载、用 `SHA256.txt` 比对，即可确认拿到的是同一份。
> **下载来源必须记全**：只有直链而不知从哪个页面下的，等于无法复核。

## 下载记录

| 项 | 内容 |
|---|---|
| 下载时间 | 2026-10-10 |
| 下载人 | 未记录（dl.ps1 批量下载，操作人未留痕） |
| 下载方式 | dl.ps1 按台账 §1.1 直链批量下载（2026-10-10） |
| **来源页面** | https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2021/art_17339_762458.html |
| PDF 直链 | https://www.mohurd.gov.cn/api-gateway/jpaas-web-server/front/document/download?fileUrl=YW5UzzlvCwcM%2FNHHX%2FtT6BJ6yM%2FAU1LVtmOVIvNjcuqxaLMLAlBp0EDqzYTeRbwVN3fPCN5o2RyBkY47dg6rAzaCLAIbPWIvTDj72QvEaooUhci45Od3s91MVFev0l%2BP0f7ImFn0WAIZjaeEzqWJqw%3D%3D&fileName=%E5%BB%BA%E7%AD%91%E7%BB%99%E6%B0%B4%E6%8E%92%E6%B0%B4%E4%B8%8E%E8%8A%82%E6%B0%B4%E9%80%9A%E7%94%A8%E8%A7%84%E8%8C%83 |

## 文件

| 项 | 内容 |
|---|---|
| 标准号 | GB 55020 |
| 名称 | 建筑给水排水与节水通用规范 |
| 公告号 | 2021 年第 171 号 |
| 实施日期 | 2022-04-01 |
| 公告页 | https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2021/art_17339_762458.html |
| **来源类型** | **官方**（住房和城乡建设部） |
| 文件 | `GB55020-2021.pdf` |
| 大小 | 3,978,385 B |
| SHA-256 | `d84b943144c51db7bbc8029493a39fe6a98358e81f19d5480da9f2459cea0112` |

## 用途边界

官方发布件或正式出版文本。可作为条文出处。

仍需注意：本文件只证明「拿到的是这一份」，**不证明条文数值已被核对**。
录入规则库时 `provenance.page` 必须逐条填真实页码，`verified_by` 必须有值。

## 废止强条清单（公告附件 2）

| 项 | 内容 |
|---|---|
| 清单文件 | `废止强条清单.docx`（原件）／`废止强条清单.txt`（抽取文本，供 grep 与 diff） |
| 清单大小 | 18,828 B |
| 清单 SHA-256 | `c2e9c4eb5d63d7a78abc2207438c5d9325b2ec537b7bafee2b0c366ba0edc6a2` |
| **清单直链** | https://www.mohurd.gov.cn/file/2021/20211012/cdd16de8eb9bf3a83a5d01f55acaa101.docx |
| 清单来源类型 | **官方**（住房和城乡建设部公告页附件） |
| 清单下载时间 | 2026-10-24 |
| 清单下载方式 | 直链直接取得（该附件为 .docx 静态直链，与正文 PDF 不同，不走 JS 动态加载） |
| 用途 | 机械比对已废止强条条号；生成 `sources/abolished_strong_clauses.json`，**不用于条文数值** |

**为什么必须单独存这一份**：公告正文只写「现行工程建设标准相关强制性条文
同时废止」，**不列条号**。条号全在附件 2。只看正文，只能得出「全部废止了」
这个无法执行的结论——库里的规则是按条号标记强制等级的，判据必须落到条号一级。
这也是「公告四查」之外的第二类盲区：公告查到了、措辞也读对了，**但判据在附件里，附件没取**。

抽取文本 `废止强条清单.txt` 由 `word/document.xml` 去标签生成，只保留段落文本；
如需逐字核对，以 `.docx` 原件为准。


## 文件性质（粗检）

| 项 | 值 |
|---|---|
| `/Font` | 9 |
| `/Image` | 210 |
| 判定 | 有字体资源，可能可抽取 → 须解析器确认文字层 |

口径：原始字节 ASCII 正则粗计数，仅供分流参考，**不等于解析器实测值**。
精确页数与文字层需 PDF 解析器确认（当前环境未安装）。
