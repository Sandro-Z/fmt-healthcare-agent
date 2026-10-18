# WGS-FMT-Agent v2

肠道菌群临床分析智能体。当前活动界面是 Next.js，业务接口是 FastAPI；样本处理、FMT
配型、知识检索、报告生成和 Agent 工具保留为共享 Python 包。旧 Streamlit 界面和旧 8000
端口 API 已从活动源码移除。

第一次接触本项目，请先阅读 `docs/PROJECT_ARCHITECTURE_GUIDE.md`，其中包含整体调用链、
常用依赖、模块对应关系、数据存储方式和完整安装启动流程。

## 目录结构

```text
apps/
  workspace-web/          Next.js 用户界面（8502）
  workspace-api/          FastAPI 工作区接口（8503）
    app/
src/
  wgs_agent/              Agent、Pipeline、工具和领域逻辑
  wgs_fmt_platform/       契约、基础设施、模型和报告能力
deploy/
  start.sh                启动当前系统
  stop.sh                 停止当前系统
  status.sh               查看状态
  restore-reverse-tunnels.sh
data/                     本地运行数据（不提交 Git）
datasets/                 评测数据集
knowledge_base/           本地知识资源
infrastructure/           MySQL/PostgreSQL/SQLite 初始化资源
scripts/                  离线处理、训练和运维脚本
tests/                    共享 Python 单元与集成测试
```

运行期日志、PID、结果和上传文件位于项目外：
`/storage/main/users/zhangrongpeng/data/fmt/wgs-fmt-agent-v2-data`。

Git 仓库仅保存源码、测试、文档和配置模板。`.env`、数据库、样本、报告、审计日志、
模型产物、下载文献、向量索引及字体二进制均由 `.gitignore` 排除。中文 PDF 字体的本地
安装方式见 `src/wgs_agent/tools/fonts/README.md`。

## 启动与停止

首次部署或重建依赖环境时，先按照 `docs/ENVIRONMENT.md` 创建 Conda/Node 环境并配置
生产 `.env`。完整且精确锁定的 Python 包版本位于 `requirements.txt`，前端版本位于
`apps/workspace-web/package-lock.json`。日常启动命令如下：

```bash
cd /storage/main/users/zhangrongpeng/data/fmt/apps/WGS-FMT-Agent-v2
bash deploy/start.sh
bash deploy/status.sh
```

浏览器访问：`http://10.181.9.172:8502/`。前端通过 `/backend/*` 反向代理到本机
8503 端口，外部用户不需要直接访问后端。

```bash
bash deploy/stop.sh
```

默认路径可以用 `WGS_APP_ROOT`、`WGS_ENV_ROOT` 和 `WGS_WORKSPACE` 覆盖。

## 开发与验证

```bash
# Python
/storage/main/users/zhangrongpeng/data/fmt/runtime/envs/wgs-fmt-agent-v2/bin/pip install -e '.[dev,infra,legacy]'
/storage/main/users/zhangrongpeng/data/fmt/runtime/envs/wgs-fmt-agent-v2/bin/pytest

# Web
cd apps/workspace-web
npm install
npm run build
```

FastAPI 开发启动：

```bash
python -m uvicorn app.main:app --app-dir apps/workspace-api --host 0.0.0.0 --port 8503 --reload
```

## 安全约束

- API Key 只通过环境变量或权限受控的运行期配置注入，不提交到源码。
- Pipeline、报告覆盖及其他写操作必须经过确认和审计。
- 临床关联结果仅供科研分析，不能替代临床诊断或治疗决策。
- 沙箱只允许访问配置的工作区根目录。

## 迁移与回退

本次目录整理说明及完整备份位置见 `docs/ACTIVE_SYSTEM.md`。
