# WGS.FMT 知识库系统

> 基于 SQLite 的结构化文献与多组学数据知识库，支持 PubMed 自动抓取、ICD-11 疾病分类、NCBI 物种中文名、益生菌名录和期刊影响因子。

## 目录结构

```
knowledge_base/
├── schema.sql            # 数据库 schema 定义
│
├── standards/            # 国际标准参考数据（原始文件）
│
├── documents/            # 原始 Markdown 文献（legacy）
│   ├── papers/           # 按疾病分类的文献 Markdown
│   └── README.md
│
├── scripts/              # 数据管理脚本
│   ├── init_db.py        # 初始化数据库
│   ├── fetch_standards.py # 下载/导入标准数据
│   ├── pubmed_pipeline.py # PubMed 自动抓取管道
│   └── backfill_existing.py # 回填现有文献
│
├── api/                  # 查询 API
│   └── kb_query.py       # 结构化查询接口
│
```

运行数据默认位于项目的 `var/knowledge/`：`kb.db` 为 SQLite 数据库，
`documents/` 为导入文献，`index/` 为索引预留位置。数据库、查询 API、导入脚本和
Agent 工具共享同一路径，可用 `WGS_WORKSPACE` 整体迁移，或用 `WGS_KB_SQLITE_PATH`
单独覆盖数据库地址。新环境所有业务表为空，不自动恢复旧文献。

## 快速开始

### 1. 初始化数据库

```bash
# 从项目根目录执行，先安装项目 Python 依赖

# 创建数据库表
python scripts/init_data.py

# 导入标准参考数据（ICD-11、NCBI taxonomy、益生菌、期刊 IF）
python knowledge_base/scripts/fetch_standards.py
```

### 2. 导入文献

**方式 A：从 PubMed 自动抓取新文献**
```bash
python knowledge_base/scripts/pubmed_pipeline.py 40659786 36058786 33542131
```

**方式 B：回填现有知识库文献**
```bash
python knowledge_base/scripts/backfill_existing.py --all
```

### 3. 结构化查询

```python
from knowledge_base.api.kb_query import KnowledgeBaseQuery

kb = KnowledgeBaseQuery()

# 查询 2020 年后关于 Akkermansia 的文献
papers = kb.search_papers(
    microbe="Akkermansia",
    year_from=2020,
    limit=10
)

# 查询糖尿病相关的高影响因子文献
papers = kb.search_papers(
    disease_keyword="diabetes",
    min_if=10,
    limit=20
)

# 查询 Feces 样本的 Shotgun 宏基因组文献
papers = kb.search_papers(
    sample_source="Feces",
    sequencing="Shotgun Metagenomics"
)

# 获取文献完整详情（含微生物、通路、代谢物、药物交互）
detail = kb.get_paper_detail("40659786")

# 获取知识库统计
stats = kb.get_stats()

# 获取 ICD-11 疾病列表
diseases = kb.get_icd11_codes(query="colorectal")

# 获取益生菌名录
probiotics = kb.get_probiotics()

# 搜索物种中文名
taxonomy = kb.get_taxonomy(name="Akkermansia")
```

## 数据库 Schema

### 核心表

| 表名 | 说明 | 记录数 |
|------|------|--------|
| `papers` | 文献主表（PMID、DOI、期刊、摘要、疾病、样本等） | 0 |
| `accessions` | 数据集编号（PRJNA/GSE/SRP 等） | - |
| `key_microbes` | 关键微生物（学名、中文名、丰度变化） | - |
| `functional_pathways` | 代谢通路（KEGG/MetaCyc） | - |
| `metabolites` | 代谢物（HMDB ID、变化方向） | - |
| `treatments` | 干预措施（药物/饮食/FMT） | - |
| `drug_microbe_interactions` | 药物-菌群交互 | - |

### 标准参考数据

| 表名 | 说明 | 记录数 |
|------|------|--------|
| `icd11_diseases` | ICD-11 疾病分类（含中文名） | 0 |
| `ncbi_taxonomy` | NCBI 物种分类（含中文名） | 0 |
| `probiotics` | ISAPP/FAO 益生菌名录 | 0 |
| `journal_impact_factors` | JCR 期刊影响因子 (2024) | 0 |

## 添加新知识条目

### 使用 PubMed 管道添加新文献

```bash
# 单篇文献
python knowledge_base/scripts/pubmed_pipeline.py <PMID>

# 批量
python knowledge_base/scripts/pubmed_pipeline.py PMID1 PMID2 PMID3 ...
```

### 标准数据更新

- **ICD-11**：修改 `scripts/fetch_standards.py` 中的 `fetch_icd11_builtin()`
- **NCBI taxonomy**：修改 `fetch_ncbi_taxonomy_builtin()`
- **益生菌名录**：修改 `fetch_probiotics_builtin()`
- **期刊 IF**：修改 `fetch_journal_if_builtin()` 后运行 `fetch_standards.py`

### 补充文献内容

文献的 Markdown 文件默认位于 `var/knowledge/documents/papers/[topic]/` 目录。
运行 `backfill_existing.py --markdown` 可将 Markdown 内容导入 SQLite 的 `study_context` 字段。

## 开发计划

- [ ] PubMed API Key 支持（提速 10 req/s）
- [ ] 期刊 IF 按 journal_name 模糊匹配（解决 ISSN 不一致）
- [ ] 物种名 NER（spaCy/BioBERT）自动提取
- [ ] PMC 全文下载和解析
- [ ] FAISS 向量索引 + RAG 集成
- [ ] Web UI：知识库浏览和编辑界面
