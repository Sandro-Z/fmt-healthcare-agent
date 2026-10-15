# WGS Pipeline 8 步详细说明

## 概述

WGS.FMT 宏基因组分析流水线将原始 FASTQ 测序数据逐步处理为物种丰度、代谢通路、代谢物和药物交互矩阵。

基本输出路径: `/storage1/zhangrongpeng/fmt-data/wgs_out`

---

## 步骤 1: 准备输入 FASTQ 文件

**目录**: `samples/{sample_id}/`

**脚本**: 无（文件系统操作）

**输入**:
- SRA Accession ID 或 .tar.gz / .fastq.gz 文件

**输出**:
- `{sample_id}_1.fastq.gz`
- `{sample_id}_2.fastq.gz` (双端)

**检测方法**: 检查 `samples/{sample_id}/` 目录下是否有 `_1.fastq.gz` 文件

---

## 步骤 2: QC + 去宿主 (KneadData)

**脚本**: `Project/WGS.FMT/pipeline/bin/02_qc_preprocess.sh`

**Conda 环境**: `fmt-tax`

**输入**:
- Step 1 输出的 FASTQ 文件

**输出目录**: `01_knead/`
- `{sample_id}_paired_1.fastq`
- `{sample_id}_paired_2.fastq`
- `{sample_id}.kneaddata.log`

**关键参数**:
- 数据库: `/storage1/zhangrongpeng/database/kneaddata/hg_39`
- 线程数: 16

**检测方法**: 检查 `01_knead/{sample_id}_paired_1.fastq` 是否存在

**运行示例**:
```bash
bash bin/02_qc_preprocess.sh \
    -i samples/{sample_id} \
    -o 01_knead \
    -d /storage1/zhangrongpeng/database/kneaddata/hg_39 \
    -t 16 -p 1 -s <(echo {sample_id})
```

---

## 步骤 3: MetaPhlAn4 物种注释

**脚本**: `Project/WGS.FMT/pipeline/bin/03_metaphlan.sh`

**Conda 环境**: `fmt-tax`

**输入**:
- Step 2 输出的 clean FASTQ

**输出目录**: `02_classify/`
- `{sample_id}_profile.tsv`  — MetaPhlAn 物种丰度表

**关键参数**:
- 数据库: `/storage1/zhangrongpeng/database/metaphlan4`
- 索引: `mpa_vJan25_CHOCOPhlAnSGB_202503`

**检测方法**: 检查 `02_classify/{sample_id}_profile.tsv` 是否存在

**运行示例**:
```bash
bash bin/03_metaphlan.sh \
    -i 01_knead \
    -o 02_classify \
    -d /storage1/zhangrongpeng/database/metaphlan4 \
    -x mpa_vJan25_CHOCOPhlAnSGB_202503 \
    -t 16 -p 1 --save-bowtie2 -s <(echo {sample_id})
```

---

## 步骤 4: HUMAnN3 功能注释

**脚本**: `Project/WGS.FMT/pipeline/bin/04_humann.sh`

**Conda 环境**: `fmt-func`

**输入**:
- Step 2 输出的 clean FASTQ

**输出目录**: `02_classify/humann/`
- `{sample_id}_pathabundance.tsv` — 通路丰度
- `{sample_id}_genefamilies.tsv` — 基因家族丰度

**关键参数**:
- 蛋白库: `/storage1/zhangrongpeng/database/humann3`
- MetaPhlAn 数据库: `/storage1/zhangrongpeng/database/metaphlan4`
- 线程数: 16

**检测方法**: 检查 `02_classify/humann/{sample_id}_pathabundance.tsv` 是否存在

**运行示例**:
```bash
bash bin/04_humann.sh \
    -i 01_knead \
    -o 02_classify/humann \
    -m /storage1/zhangrongpeng/database/metaphlan4 \
    -P /storage1/zhangrongpeng/database/humann3 \
    -t 16 -p 1 -s <(echo {sample_id})
```

---

## 步骤 5: 通路映射

**脚本**: `Project/WGS.FMT/pipeline/bin/05_pathway_mapping.py` (内置 Python)

**Conda 环境**: `fmt-func`

**输入**:
- Step 3/4 的 HUMAnN 输出 (所有现有样本)

**输出目录**: `04_pathway/`
- `pathway_abundance_known.tsv` — 已知通路丰度矩阵
- `gene_families_uniref.tsv` — 蛋白质 UniRef 矩阵
- `pathway_species_contribution.tsv` — 通路-物种贡献矩阵

**检测方法**: 检查 `04_pathway/pathway_abundance_known.tsv` 是否**包含新样本列**

**运行示例**:
```bash
# 运行 run_direct_step.sh 的 Step 5 部分
python << 'EOF'
# 重新生成通路矩阵（增量：扫描所有 HUMAnN 输出，重建矩阵）
import os, glob, re, pandas as pd
humann_dir = "/storage1/zhangrongpeng/fmt-data/wgs_out/02_classify/humann"
output_dir = "/storage1/zhangrongpeng/fmt-data/wgs_out/04_pathway"
# ... 见 run_direct_step.sh 的 run_step5 函数
EOF
```

---

## 步骤 6: 矩阵导出

**脚本**: `Project/WGS.FMT/pipeline/bin/06_matrix_export.py`

**Conda 环境**: `fmt-func`

**输入**:
- Step 3 的 MetaPhlAn profiles
- Step 5 的通路矩阵

**输出目录**: `05_matrix/`
- `relative_abundance_species.tsv` — **物种丰度矩阵（报告核心输入）**
- `relative_abundance_genus.tsv` — 属水平丰度矩阵
- `combined_matrix.tsv` — 联合矩阵

**检测方法**: 检查 `05_matrix/relative_abundance_species.tsv` 的表头是否**包含新样本ID**

**运行示例**:
```bash
# 运行 run_direct_step.sh 的 Step 6 部分
python << 'EOF'
# 重新导出联合矩阵
# ... 见 run_direct_step.sh 的 run_step6 函数
EOF
```

---

## 步骤 7: 代谢物含量矩阵

**脚本**: `Project/WGS.FMT/pipeline/step_metabolite_matrix.py`

**输入**:
- Step 5 的通路丰度矩阵

**输出目录**: `06_metabolite/`
- `metabolite_content_matrix.tsv` — 代谢物含量矩阵

**检测方法**: 检查 `06_metabolite/metabolite_content_matrix.tsv` 表头是否**包含新样本ID**

**运行示例**:
```bash
python step_metabolite_matrix.py \
    --input-file 04_pathway/pathway_abundance_known.tsv \
    --output-file 06_metabolite/metabolite_content_matrix.tsv \
    --no-api
```

---

## 步骤 8: PDF 报告生成

**脚本**: `generate_pdf_report.py` / `domain_tools.ReportGeneratorTool`

**输入**:
- Step 6 的物种矩阵
- Step 7 的代谢物矩阵

**输出目录**: `07_reports/`
- `{sample_id}_health_report.pdf`

---

## 缺口检测算法

```
function detect_gap(sample_id):
    steps = []
    
    if not exists(samples/{id}/*_1.fastq.gz):        steps += [1]
    if not exists(01_knead/{id}_paired_1.fastq):     steps += [2]
    if not exists(02_classify/{id}_profile.tsv):     steps += [3]
    if not exists(02_classify/humann/{id}_pathabundance.tsv): steps += [4]
    
    # 步骤5-7 是矩阵级操作（需要重建整个矩阵以包含新样本）
    if sample_not_in_matrix(04_pathway/pathway_abundance_known.tsv): steps += [5]
    if sample_not_in_matrix(05_matrix/relative_abundance_species.tsv): steps += [6]
    if sample_not_in_matrix(06_metabolite/metabolite_content_matrix.tsv): steps += [7]
    
    return steps  # 需要运行的步骤列表