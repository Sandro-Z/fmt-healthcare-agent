# 单服务器架构

```text
浏览器 http://<服务器IP>:8502
        |
        v
Next.js 0.0.0.0:8502
        | /backend/* -> /*
        v
FastAPI 127.0.0.1:8503
        |-- var/ 下的本地数据库和文件
        |-- 本机模型服务 127.0.0.1:11434（可选）
        |-- 本机 LitKG 127.0.0.1:8080（可选）
        `-- 本机 Redis / Elasticsearch（可选）
```

浏览器中的 API 和文件地址保持同源相对路径。服务器 IP 改变后无需重新编译浏览器地址。
API 和 daemon 仅绑定回环地址；默认不启用跨域访问，如需独立前端可配置
`WGS_CORS_ORIGINS`。不再创建 SSH 转发，也不依赖旧服务器或跳板机。

## 数据布局

默认 `WGS_WORKSPACE=<项目根目录>/var`，所有相对路径均以项目根目录解析，
与执行命令时的工作目录无关。只设置 `WGS_WORKSPACE` 即可整体移动默认数据位置；
显式设置的单项路径优先。

| 目录/文件 | 用途 | 可选覆盖变量 |
|---|---|---|
| `var/db/wgs_agent.db` | 用户、认证会话、对话、消息、审计元数据 | `WGS_CONVERSATION_DB_FILE` |
| `var/knowledge/kb.db` | 本地文献与知识数据库 | `WGS_KB_SQLITE_PATH` 或 `WGS_KNOWLEDGE_DB` |
| `var/knowledge/documents/` | 知识文档 | `WGS_KB_DIR` |
| `var/knowledge/index/` | 知识索引预留位置 | `WGS_KB_INDEX_DIR` |
| `var/agent-config/` | Agent、Skill、设置及待确认动作 | `WGS_AGENT_CONFIG_DIR` |
| `var/uploads/` | 原始测序上传 | `WGS_UPLOAD_ROOT` |
| `var/upload-jobs/` | 上传任务状态 | `WGS_UPLOAD_JOB_ROOT` |
| `var/bioinformatics/` | 单样本分析结果、矩阵和 runner 状态 | `WGS_BIOINFORMATICS_OUTPUT_ROOT` |
| `var/bioinformatics/legacy/` | 兼容旧流程的矩阵结果（初始为空） | `WGS_LEGACY_PIPELINE_OUTPUT_DIR` |
| `var/results/` | 分析 JSON、报告及配型图 | `WGS_RESULTS_DIR` |
| `var/reference/` | 健康参考数据 | `WGS_REFERENCE_DIR` |
| `var/databases/` | 生信数据库 | 各工具数据库配置 |
| `var/model-training/`、`var/model-registry/` | 模型训练产物与注册信息 | `WGS_FMT_TRIPLET_MODEL_DIR`、`WGS_MODEL_REGISTRY_ROOT` |
| `var/fmt/` | 供体丰度及配对数据 | `WGS_FMT_DATA_ROOT` |
| `var/sandboxes/` | 用户/会话文件沙箱 | `WGS_AGENT_SANDBOX_ROOT` |
| `var/workspaces/default/` | 进程执行沙箱 | `WGS_SANDBOX_WORKSPACE` |
| `var/agent-audit/`、`var/logs/`、`var/traces/`、`var/run/` | 审计、日志、追踪、PID | 对应 `WGS_*` 配置 |
| `var/sessions/`、`var/runs/`、`var/policy.toml` | 可选 daemon 的会话、运行与权限策略 | `WGS_SESSIONS_DIR`、`WGS_RUNS_DIR`、`WGS_POLICY_FILE` |

`knowledge_base/` 仅保留 schema、脚本和文档；运行数据库和下载文献不再写入源码目录。
运行数据受 `.gitignore` 排除。新目录默认权限为 700，新数据文件为 600。

## 全新初始化

完成 Python 依赖安装后，在项目根目录运行：

```bash
.venv/bin/python scripts/init_data.py
```

脚本创建空的会话/用户数据库和知识数据库，不导入旧数据、不下载参考库、不调用外部接口、
不启动任何服务。重复执行会保留新环境中已有的记录。它不支持自动清空已有数据库。
首次启动 API 时会补齐默认 Agent/Skill/设置及系统内部用户；真实登录账号通过页面注册。

本地持久化默认使用 SQLite。`WGS_DATABASE_URL` 可显式切换数据库，初始化脚本只负责
本地 SQLite，并跳过显式配置的外部数据库；MySQL 等外部数据库需另行初始化。Redis、Elasticsearch 和 LitKG 不由
本项目启动；缺少这些可选服务时，相关记忆或检索功能会返回错误/降级状态。

生信 worker 默认路径为项目内的
`runtime/scripts/postfmt_pipeline/process_postfmt_sample.sh`，兼容流程脚本默认位于
`runtime/pipeline/`。仓库不包含这些外部工具、参考库和训练模型；缺失时分析功能会明确
返回不可用状态，不会自动读取其他项目目录。可通过 `.env.example` 中的变量指定本机安装位置。

## 后续启动

参考 [README](../README.md) 完成前端构建后，才可手动运行 `bash deploy/start.sh`。
前端构建和启动必须使用相同的 `WGS_API_PORT`；修改该值需要重新构建。
启动脚本不会安装依赖、构建前端、修改防火墙或连接 SSH 跳板机。
