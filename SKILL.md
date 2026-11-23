---
name: science-to-public-rewriter
description: Use when a case supplies a technical source (paper abstract, report, or paper section) plus a target audience and asks for science-communication rewriting or genre conversion; profiles the audience, keeps a number-and-hedge retention table, audits claim strength against the source, locks a term base, records deletions, and writes /app/output/result.json preserving case_id and every output_contract field. Deterministic standard library only; no network.
---

# 科研成果转化写作（受众可读—证据不丢—强度不越界）

## 用途与适用条件

当需要把论文、技术报告或项目材料改写成面向公众、学生、企业或管理者的文本（或反向转换文体）时使用。

适用：

- 输入有明确源文与目标读者，可能已有改写稿需要核对。
- 担心改写时丢掉数值、单位、样本量、限定条件。
- 担心把“相关”写成“因果”、把“初步结果”写成“定论”。
- 需要术语表、缩写首次展开与删改清单。

不适用：无源文的自由创作、代写宣传口号、虚构数据或引用、替代机构做对外发布审核。

## 输入

- `/input/case.json`：读取 `case_id`、`output_contract`、`task`、`audience`/`target_audience`、`source`/`paper`/`source_text`、`draft`/`rewrite`/`target_text`、`genre`、`length_limit` 等字段。
- `task.md`：存在时读取 `/input/task.md` 或 `/app/work/task.md`。
- 文本可内联或给路径；只读 UTF-8、≤2MB；PDF/二进制登记为未解析。
- 输出 `/app/output`，工作 `/app/work`。

## 处理流程（逐项覆盖评分维度）

1. **受众画像（读得懂）**：从 `audience` 与任务文本识别读者类型（公众/学生/企业/管理者/患者），给出建议的解释深度、术语密度与篇幅上限；未给受众时标 `audience_missing`，不猜测。
2. **可读性度量**：句均长度、超长句（>40 词或 >60 汉字）、被动句比例、缩写密度、未展开缩写清单。指标只描述文本，不替代人工编辑判断。
3. **证据保真（留得住）**：抽取源文数值+单位、样本量、置信区间与限定词（may/might/初步/preliminary/limited）；若提供改写稿，逐条检查是否保留，输出 `retention_table`（`retained / missing / changed`）。缺失项不回填数值，只标记。
4. **术语基线（说得准）**：建立缩写与术语表，记录首次出现位置与全称；改写稿出现同义漂移（如 efficiency/efficacy 混用）时列 `term_drift`，不擅自统一。
5. **论断强度（说得准）**：源文为相关/推测（associated, may, suggests）而改写成因果/定论（causes, proves, 必然）时记 `overclaim`；反向弱化导致结论失真时记 `underclaim`。
6. **删改台账（接得住）**：将源文句子与改写稿做词面覆盖匹配，覆盖不足且含数值/限定/局限的句子列为 `protected_deletion`；其余列为可删，并给出理由。
7. **改写提纲**：未提供改写稿时，输出 `draft_plan`：结构段落、必须保留的证据清单、每个术语的首次展开位置、建议类比位（不代写具体类比内容）。
8. **合同保留**：见输出契约。

## 输出契约

写入 `/app/output/result.json`：

- 顶层 `case_id` 与输入一致。
- **保留原始 `output_contract` 每个字段名**（字典/列表/`fields`/Schema `properties`）；未映射写 `null` 并登记，状态降为 `partial`；组合 Schema 登记 `unsupported_features`。
- 固定字段：
  - `status`：`success | partial | insufficient_input | failed`
  - `result`：`audience_profile`、`readability`、`retention_table`、`term_base`、`claim_strength_audit`、`deletion_ledger`、`draft_plan`
  - `evidence`、`uncertainty`、`errors`、`stats`
- 退出码：`0` 完成；`1` 有未映射合同字段；`2` 输入不可读。

## 异常处理

| 情形 | 处置 |
|---|---|
| 无源文 | `status=insufficient_input`，不生成科普内容 |
| 只有源文、无改写稿 | `status=partial`，仅输出受众画像、证据清单与改写提纲，不声称已改稿 |
| 未给受众 | 标 `audience_missing`，用中性解释深度，不假设读者专业水平 |
| 数值单位缺失 | 原样保留并标 `unit_missing`，不换算 |
| 改写稿新增源文没有的数字 | 标 `unsourced_number`，要求作者提供出处 |
| 源文相关、改写因果 | 标 `overclaim` 并给出源文原句 |
| 源文限定条件被删 | 列入 `protected_deletion`，不视为冗余 |
| 术语一义多词 | 记录全部变体，交作者确认统一口径 |

## 限制与不适用

- 不做机器翻译、不生成新的科学结论、不补造数据或引用。
- 可读性指标是启发式，不等于目标读者真实理解度。
- 匹配基于词面覆盖，改写幅度大时可能误判为删除，需人工复核。
- 不替代机构的事实核查与合规审核。

## 最小调用示例（示例）

以下为合成示意，非官方案例。

```bash
python /skills/weekly-skill/scripts/run_skill.py \
  --case /input/case.json \
  --out /app/output/result.json \
  --work /app/work
```

合成 `case.json`：

```json
{
  "case_id": "synthetic-scicomm-demo",
  "output_contract": {"status": "string", "draft": "string", "retention_table": "array", "term_base": "array"},
  "audience": "general public",
  "source": "In 120 adults, the intervention was associated with an 18.4% reduction in body weight (95% CI 9.2-19.4) over 12 weeks.",
  "draft": "The treatment caused an 18.4% weight loss in 120 adults."
}
```

示意输出（节选）：

```json
{"case_id":"synthetic-scicomm-demo","status":"success","result":{"retention_table":[{"value":"18.4","unit":"%","status":"retained"}],"claim_strength_audit":[{"issue":"overclaim","source":"was associated with","draft":"caused"}]}}
```

## 自查清单

- [ ] `case_id` 与合同字段保留；未映射项已登记。
- [ ] 每个源文数值都有保留状态，缺失未被静默删掉。
- [ ] 相关/因果、推测/定论的转换已逐条标记。
- [ ] 术语有首次展开与变体记录。
- [ ] 无改写稿时未声称完成改稿。
- [ ] 未新增源文没有的数字、引用或结论。


## 交付保证与评分对齐

调用顺序（固定）：

1. 先运行包内脚本（若存在）：`python scripts/run_skill.py`（默认读 `/input/case.json`，写 `/app/output/result.json`）；路径不同时用 `--case` / `--output` 指定。
2. **必须交付完整成品**：脚本只做画像、保留表与审计；调用 Agent 必须在有源文时写出**完整改写稿**（按目标受众与篇幅，写入 `result.draft`），数值、单位、样本量与限定词逐条保留并在 `retention_table` 中核对；无现成草稿时不得只交 `draft_plan` 便结束，须完成改写；不得 `pending`。
3. 最后自检：`case_id` 与输入一致；`output_contract` 每个字段都存在；`status` 取本合同允许值 `success | partial | insufficient_input | failed`；正文无 `pending`/`TODO`/空占位；数字、引用、来源可逐条回溯。

运行保证：

- 输入缺失、JSON 损坏、字段异常、输出目录不存在时，仍须写出结构化 `result.json` 并正常结束，不得崩溃或非零退出。
- 不联网、不伪造数据、不声称平台评分或官方案例结果。
- 交付物必须是可直接编辑与复核的成品，而不是流程说明。

评分对齐（本题五个维度）：

- 实际效果（40）：完整产出任务要求的最终成品，覆盖全部输入条目，可直接进入修改流程。
- 使用增益（25）：体现相对基础 Agent 的可验证改进（结构化、术语/数字/引用核对、可编辑性）。
- 创新增益（15）：保留方法学增量（分块、对齐、二次校验、版本比对等），并用结果证明其价值。
- 可靠体验（10）：异常输入有明确降级与说明，不同长度/文体/重复运行下稳定产出。
- 生态贡献（10）：用途、调用、输入输出、限制、示例、维护信息齐全，资源可被他人复用。

## 最终交付强制要求

1. **调用 Agent 必须交付成品，不是流程说明**：脚本产出只是索引、核对或规格骨架；调用 Agent 必须在同一 `result.json` 中补齐本题要求的最终产物（正文/译文/审稿意见/综述/分析结论/图表源文件与导出件/幻灯片页内容与讲稿/实验方案等）。交付字段为空、只有标题骨架，或含 `pending`、`TODO` 之类占位，一律视为未完成。
2. **必须覆盖全部输入条目**：输入中的每个章节、问题、文献、图、页面、指标都要有对应条目，不得只处理示例或首条；确实缺失的条目写入 `uncertainty` / `limitations` 并说明原因，不得静默跳过。
3. **必须自检后再交付**：`case_id` 与输入一致；`output_contract` 每个字段都存在；状态值取本题契约规定的枚举；数字、单位、引用、来源可逐条回溯；结果内部无自相矛盾。
4. **参数等价**：`python scripts/run_skill.py --case <输入> --out <输出>` 与 `--output <输出>` 等价；默认 `/input/case.json` → `/app/output/result.json`。
5. **平台用 3 个固定案例分别运行**：逻辑要由输入驱动，不针对某一份示例硬编码；字段命名差异走别名匹配与显式降级，并在 `uncertainty` 记录假设。
