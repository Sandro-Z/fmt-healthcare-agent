# 从 WGS-FMT-Agent 迁移

## 原则

旧项目 `/home/zhangrongpeng/Project/WGS-FMT-Agent` 不直接修改。v2 通过适配器读取旧数据，在验证结果一致后逐模块切换。

## 模块映射

| 旧模块 | v2 位置 | 处理方式 |
|---|---|---|
| `tools/pipeline_runner.py` | `metagenome/adapters/` | 底层命令与路径移入 Adapter |
| `tools/knowledge_tools.py` | `knowledge/adapters/` | 返回结构化 Claim，不再返回拼接文本 |
| `tools/domain_tools.py` | `workflows/` | 拆为用例服务，Agent Tool 只做薄包装 |
| `pipeline/report_data.py` | `contracts.FeatureSet` | 统一单位、实体 ID、来源版本 |
| `tools/report_maker.py` | `reporting/` | 保留模板，输入改成 EvidenceBundle |
| `web/app.py` | API 客户端 | Web 不直接执行工具和 Shell |

## 第一阶段验收

- 同一样本可生成稳定的 `AnalysisResult`。
- 每个观察值包含来源、单位和特征版本。
- 每个 Claim 包含实体 ID、证据来源、解析器版本和审核状态。
- 报告能够追溯数据库、知识图谱和模型版本。
- 外部接口不可用时返回明确降级状态，不伪造结果。

## 第二阶段验收

- 建立固定训练/验证/外部测试集。
- FMT 使用 Recall@K、NDCG@K 和 MRR。
- 疾病风险使用 AUROC、AUPRC 与校准误差。
- 报告评测数字忠实度、引用支持率和无依据结论率。

