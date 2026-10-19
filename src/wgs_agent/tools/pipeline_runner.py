"""Pipeline 自动触发工具 — 检测分析缺口并按需增量运行 WGS Pipeline

提供两个工具:
  PipelineCheckTool  — 扫描文件系统，检测样本在各步骤的输出文件状态
  PipelineRunStepTool — 触发指定步骤的执行（调用对应脚本）
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd  # noqa: F401 — 用于检查矩阵中的列

from wgs_agent.core.tools.base import BaseTool, ToolResult
from wgs_fmt_platform.paths import PROJECT_ROOT, legacy_output_root, project_path, runtime_path

JSON_KEY = "---JSON---"

# ============================================================================
# 路径常量
# ============================================================================
_WGS_OUT = str(legacy_output_root())
_SAMPLES_DIR = str(runtime_path("WGS_LEGACY_SAMPLES_DIR", "samples"))
_PIPELINE_ROOT = project_path(os.environ.get("WGS_PIPELINE_ROOT") or PROJECT_ROOT / "runtime/pipeline")
_PIPELINE_BIN = str(_PIPELINE_ROOT / "bin")
_METABOLITE_SCRIPT = str(_PIPELINE_ROOT / "step_metabolite_matrix.py")


def _activation_prefix(kind: str) -> str:
    """Use the current environment unless a local Conda activation is configured."""
    activate = os.environ.get("WGS_CONDA_ACTIVATE", "").strip()
    if not activate:
        return ""
    name = os.environ.get(f"WGS_{kind.upper()}_ENV", f"fmt-{kind}")
    return f"source {shlex.quote(activate)} {shlex.quote(name)} && "

# Pipeline 步骤定义: (步骤号, 名称, 检查路径模板, 检查方式)
# 检查方式: "file"=检查文件是否存在, "matrix_header"=检查矩阵表头是否包含样本ID
STEP_CHECKS: list[tuple[int, str, str, str]] = [
    (1, "准备输入", f"{_SAMPLES_DIR}/{{sample}}/{{sample}}_1.fastq.gz", "file"),
    (2, "QC+去宿主", f"{_WGS_OUT}/01_knead/{{sample}}/{{sample}}_paired_1.fastq", "file"),
    (3, "MetaPhlAn注释", f"{_WGS_OUT}/02_classify/{{sample}}_profile.tsv", "file"),
    (4, "HUMAnN功能注释", f"{_WGS_OUT}/02_classify/humann/{{sample}}_pathabundance.tsv", "file"),
    (5, "通路映射", f"{_WGS_OUT}/04_pathway/pathway_abundance_known.tsv", "matrix_header"),
    (6, "矩阵导出", f"{_WGS_OUT}/05_matrix/relative_abundance_species.tsv", "matrix_header"),
    (7, "代谢物矩阵", f"{_WGS_OUT}/06_metabolite/metabolite_content_matrix.tsv", "matrix_header"),
]


def _make_result(text: str, data: dict[str, Any]) -> ToolResult:
    return ToolResult(content=f"{text}\n{JSON_KEY}\n{json.dumps(data, ensure_ascii=False, default=str)}")


def _check_file_exists(path_template: str, sample_id: str) -> bool:
    """检查文件模板是否存在（模糊匹配：也检查 sample_id 作为子串）"""
    exact = path_template.format(sample=sample_id)
    if os.path.exists(exact):
        return True
    dir_path = os.path.dirname(exact)
    if os.path.isdir(dir_path):
        for fname in os.listdir(dir_path):
            if sample_id in fname:
                return True
    return False


def _check_sample_in_matrix(matrix_path: str, sample_id: str) -> bool:
    """检查样本ID是否在矩阵文件的列名中"""
    if not os.path.exists(matrix_path):
        return False
    try:
        if matrix_path.endswith(".tsv"):
            df = pd.read_csv(matrix_path, sep="\t", nrows=0)
        else:
            return False
        cols = [str(c) for c in df.columns]
        return sample_id in cols or any(sample_id in c for c in cols)
    except Exception:
        return False


def _detect_pipeline_gap(sample_id: str) -> dict[str, Any]:
    """扫描文件系统，检测样本的 Pipeline 完成状态"""
    completed: list[int] = []
    missing: list[int] = []
    files_found: dict[str, str] = {}
    files_missing: dict[str, str] = {}

    for step_num, name, path_tpl, check_type in STEP_CHECKS:
        path_filled = path_tpl.format(sample=sample_id)
        if check_type == "file":
            ok = _check_file_exists(path_tpl, sample_id)
        else:  # matrix_header
            ok = _check_sample_in_matrix(path_tpl, sample_id)

        if ok:
            completed.append(step_num)
            files_found[name] = path_filled
        else:
            missing.append(step_num)
            files_missing[name] = path_filled

    if not missing:
        start_from = 8
    else:
        start_from = min(missing)

    return {
        "sample_id": sample_id,
        "completed_steps": completed,
        "missing_steps": missing,
        "start_from": start_from,
        "files_found": files_found,
        "files_missing": files_missing,
        "total_steps": len(STEP_CHECKS),
    }


def _readable_gap_report(gap: dict[str, Any]) -> str:
    """生成可读的缺口报告"""
    lines = [
        f"Pipeline 缺口检测 — 样本 {gap['sample_id']}",
        f"  已完成步骤: {gap['completed_steps'] or '(无)'}",
        f"  缺失步骤:   {gap['missing_steps'] or '(无)'}",
        f"  建议从 Step {gap['start_from']} 开始",
        "",
        "已找到的文件:",
    ]
    for name, path in gap["files_found"].items():
        lines.append(f"  ✅ {name}: {path}")
    if gap["files_missing"]:
        lines.append("缺失的文件:")
        for name, path in gap["files_missing"].items():
            lines.append(f"  ❌ {name}: {path}")
    return "\n".join(lines)


# ============================================================================
# Tool 1: Pipeline 缺口检测
# ============================================================================


class PipelineCheckTool(BaseTool):
    name = "pipeline_check"
    description = "扫描 WGS Pipeline 文件系统，检测样本在各步骤的输出文件完成状态，返回缺口报告。"
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "sample_id": {"type": "string", "description": "样本 ID"},
        },
        "required": ["sample_id"],
    }

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        try:
            sid = str(params["sample_id"])
            gap = _detect_pipeline_gap(sid)
            text = _readable_gap_report(gap)
            return _make_result(text, gap)
        except Exception as exc:
            return ToolResult(
                content=f"Pipeline 检测失败: {exc}",
                is_error=True,
                error_type="runtime_error",
            )


# ============================================================================
# Tool 2: Pipeline 步骤执行
# ============================================================================


class PipelineRunStepTool(BaseTool):
    name = "pipeline_run_step"
    description = "触发 WGS Pipeline 的指定步骤执行（调用对应的 Shell 脚本），返回执行结果和状态。"
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "sample_id": {"type": "string", "description": "样本 ID"},
            "start_step": {"type": "integer", "description": "从第几步开始执行 (1-7)"},
            "steps": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "要执行的步骤列表，不指定则从 start_step 开始连续执行",
            },
        },
        "required": ["sample_id", "start_step"],
    }

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        try:
            sid = str(params["sample_id"])
            start_step = int(params.get("start_step", 1))
            steps: list[int] = (
                [int(s) for s in params["steps"]]
                if params.get("steps")
                else [start_step]
            )

            results: list[dict[str, Any]] = []
            all_ok = True

            for step in sorted(steps):
                step_name = (
                    STEP_CHECKS[step - 1][1] if step <= len(STEP_CHECKS)
                    else f"Step {step}"
                )

                if step == 1:
                    result = _run_step1_check(sid)
                elif 2 <= step <= 4:
                    result = _run_sample_step(sid, step)
                elif step == 5:
                    result = _run_matrix_rebuild_step(sid, step)
                elif step == 6:
                    result = _run_matrix_rebuild_step(sid, step)
                elif step == 7:
                    result = _run_metabolite_step(sid)
                else:
                    result = {
                        "step": step,
                        "name": step_name,
                        "status": "skipped",
                        "message": f"步骤 {step} 不存在",
                    }

                results.append(result)
                if result.get("status") == "error":
                    all_ok = False

            summary = "; ".join(
                f"Step {r['step']}: {r.get('status', '?')}" for r in results
            )

            return _make_result(
                f"Pipeline 执行结果 — {sid}\n{summary}",
                {
                    "sample_id": sid,
                    "all_ok": all_ok,
                    "results": results,
                },
            )

        except Exception as exc:
            import traceback
            return ToolResult(
                content=f"Pipeline 执行失败: {exc}\n{traceback.format_exc()}",
                is_error=True,
                error_type="runtime_error",
            )


# ============================================================================
# 步骤执行函数
# ============================================================================


def _run_step1_check(sample_id: str) -> dict[str, Any]:
    """Step 1: 检查输入文件是否就绪"""
    sample_dir = os.path.join(_SAMPLES_DIR, sample_id)
    if os.path.isdir(sample_dir):
        fastq_files = [f for f in os.listdir(sample_dir) if f.endswith(".fastq.gz") or f.endswith(".fq.gz")]
        if fastq_files:
            return {
                "step": 1,
                "name": "准备输入",
                "status": "ok",
                "message": f"已有 {len(fastq_files)} 个 FASTQ 文件",
                "files": fastq_files,
            }
    return {
        "step": 1,
        "name": "准备输入",
        "status": "error",
        "message": f"未找到输入文件: {sample_dir}",
    }


def _run_sample_step(sample_id: str, step: int) -> dict[str, Any]:
    """Step 2-4: 运行单样本处理脚本"""
    step_scripts = {
        2: ("02_qc_preprocess.sh", "QC+去宿主"),
        3: ("03_metaphlan.sh", "MetaPhlAn注释"),
        4: ("04_humann.sh", "HUMAnN功能注释"),
    }

    script_name, step_name = step_scripts.get(step, ("", f"Step {step}"))
    script_path = os.path.join(_PIPELINE_BIN, script_name)

    if not script_name or not os.path.isfile(script_path):
        return {
            "step": step,
            "name": step_name,
            "status": "error",
            "message": f"脚本不存在: {script_path}",
        }

    cmd = _build_step_command(step, sample_id, script_path)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=36000,
            shell=True,
            executable="/bin/bash",
        )
        ok = result.returncode == 0
        return {
            "step": step,
            "name": step_name,
            "status": "ok" if ok else "error",
            "message": (
                f"退出码 {result.returncode}"
                + (f"\nstdout: {result.stdout[:500]}" if result.stdout else "")
            ),
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "step": step,
            "name": step_name,
            "status": "error",
            "message": "执行超时（>10小时）",
        }


def _run_matrix_rebuild_step(sample_id: str, step: int) -> dict[str, Any]:
    """Step 5-6: 重建矩阵"""
    step_name = "通路映射" if step == 5 else "矩阵导出"

    # 使用 run_direct_step.sh 的对应步骤
    run_direct = str(_PIPELINE_ROOT / "run_direct_step.sh")
    cmd = f"bash {shlex.quote(run_direct)} {step}"

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=7200,
            shell=True,
            executable="/bin/bash",
        )
        ok = result.returncode == 0
        return {
            "step": step,
            "name": step_name,
            "status": "ok" if ok else "error",
            "message": f"退出码 {result.returncode}\n{result.stdout[-1000:] if result.stdout else ''}",
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "step": step,
            "name": step_name,
            "status": "error",
            "message": "执行超时（>2小时）",
        }


def _run_metabolite_step(sample_id: str) -> dict[str, Any]:
    """Step 7: 代谢物矩阵"""
    pathway_file = f"{_WGS_OUT}/04_pathway/pathway_abundance_known.tsv"
    output_file = f"{_WGS_OUT}/06_metabolite/metabolite_content_matrix.tsv"

    if not os.path.isfile(_METABOLITE_SCRIPT):
        return {
            "step": 7,
            "name": "代谢物矩阵",
            "status": "skipped",
            "message": f"脚本不存在: {_METABOLITE_SCRIPT}",
        }

    cmd = (
        _activation_prefix("func") +
        f"python {_METABOLITE_SCRIPT} "
        f"--input-file {pathway_file} "
        f"--output-file {output_file} "
        f"--no-api"
    )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
            shell=True,
            executable="/bin/bash",
        )
        ok = result.returncode == 0
        return {
            "step": 7,
            "name": "代谢物矩阵",
            "status": "ok" if ok else "error",
            "message": f"退出码 {result.returncode}\n{result.stdout[-500:] if result.stdout else ''}",
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "step": 7,
            "name": "代谢物矩阵",
            "status": "error",
            "message": "执行超时（>1小时）",
        }


# ============================================================================
# 命令构建
# ============================================================================


def _write_tmp_sample_file(sample_id: str) -> str:
    """创建临时样本列表文件，返回文件路径"""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="pipeline_sample_", delete=False
    )
    tmp.write(f"{sample_id}\n")
    tmp.close()
    return tmp.name


def _build_step_command(step: int, sample_id: str, script_path: str) -> str:
    """根据步骤构建对应的 shell 命令

    注意:
    - Step 3/4 脚本 (03_metaphlan.sh, 04_humann.sh) 内部会在 INPUT_DIR 下
      自动拼接 ${sample_id} 子目录查找文件:
        find "${INPUT_DIR}/${sample_id}" -maxdepth 1 -name "..."
      因此必须传 .../01_knead 根目录，不能传 .../01_knead/{sample_id}
    - 使用临时文件替代 process substitution (<(echo ...))，兼容非交互式 shell
    """
    kneaddata_db = str(runtime_path("WGS_KNEADDATA_DATABASE", "databases", "kneaddata", "hg_39"))
    metaphlan_db = str(runtime_path("WGS_METAPHLAN_DATABASE", "databases", "metaphlan4"))
    metaphlan_index = os.environ.get("WGS_METAPHLAN_INDEX", "mpa_vJan25_CHOCOPhlAnSGB_202503")
    humann_root = str(runtime_path("WGS_HUMANN_DATABASE", "databases", "humann3"))
    humann_protein = f"{humann_root}/uniref"
    humann_nucleotide = f"{humann_root}/chocophlan"

    wgs_out = _WGS_OUT
    knead_root = f"{wgs_out}/01_knead"  # 脚本内部会拼接 /{sample_id}

    # 创建临时样本文件
    tmp_file = _write_tmp_sample_file(sample_id)
    cleanup = f"rm -f {tmp_file}"

    if step == 2:
        return (
            _activation_prefix("tax") +
            f"bash {script_path} "
            f"-i {_SAMPLES_DIR}/{sample_id} "
            f"-o {wgs_out}/01_knead "
            f"-d {kneaddata_db} "
            f"-t 8 -p 1 "
            f"-s {tmp_file} "
            f"-l {wgs_out}/log/step2_{sample_id}.log"
            f"; {cleanup}"
        )
    elif step == 3:
        return (
            _activation_prefix("tax") +
            f"bash {script_path} "
            f"-i {knead_root} "
            f"-o {wgs_out}/02_classify "
            f"-d {metaphlan_db} "
            f"-x {metaphlan_index} "
            f"-t 8 -p 1 --save-bowtie2 "
            f"-s {tmp_file} "
            f"-l {wgs_out}/log/step3_{sample_id}.log"
            f"; {cleanup}"
        )
    elif step == 4:
        # HUMAnN 数据库必须用子目录:
        #   -P uniref/  (蛋白库), nucleotide 用 chocophlan/
        #   同时需要 humann_config 初始化 + export HUMANN_DB
        return (
            _activation_prefix("func") +
            f"export HUMANN_DB='{humann_root}' && "
            f"humann_config --update database_folders protein '{humann_protein}' 2>/dev/null; "
            f"humann_config --update database_folders nucleotide '{humann_nucleotide}' 2>/dev/null; "
            f"humann_config --update database_folders utility_mapping '{humann_root}/utility_mapping' 2>/dev/null; "
            f"bash {script_path} "
            f"-i {knead_root} "
            f"-o {wgs_out}/02_classify/humann "
            f"-m {metaphlan_db} "
            f"-P {humann_protein} "
            f"-t 8 -p 1 "
            f"-s {tmp_file} "
            f"-l {wgs_out}/log/step4_{sample_id}.log"
            f"; {cleanup}"
        )
    # 未匹配步骤时也清理临时文件
    os.unlink(tmp_file)
    return f"echo '未知步骤 {step}'"


# ============================================================================
# 工具注册
# ============================================================================

PIPELINE_TOOLS: list[type[BaseTool]] = [
    PipelineCheckTool,
    PipelineRunStepTool,
]

PIPELINE_TOOL_POLICIES: dict[str, dict[str, object]] = {
    "pipeline_check": {"default": "allow", "reason": "只读文件系统检查"},
    "pipeline_run_step": {"default": "ask", "reason": "执行耗时计算任务，可能需数小时"},
}
