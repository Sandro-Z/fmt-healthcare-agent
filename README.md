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
  common.sh               统一读取环境与本机路径
var/                      单服务器运行数据（不提交 Git）
datasets/                 评测数据集
knowledge_base/           本地知识资源
infrastructure/           MySQL/PostgreSQL/SQLite 初始化资源
scripts/                  离线处理、训练和运维脚本
tests/                    共享 Python 单元与集成测试
```

运行数据默认位于当前项目的 `var/`，可用 `WGS_WORKSPACE` 整体切换到本机其他专用目录。
相对路径均以项目根目录为基准。全新环境创建空数据库，不读取、复制旧服务器的数据。

Git 仓库仅保存源码、测试、文档和配置模板。`.env`、数据库、样本、报告、审计日志、
模型产物、下载文献、向量索引及字体二进制均由 `.gitignore` 排除。中文 PDF 字体的本地
安装方式见 `src/wgs_agent/tools/fonts/README.md`。

## 单服务器准备（不启动服务）

首次部署或重建依赖环境时，先按照 `docs/ENVIRONMENT.md` 创建 Conda/Node 环境并配置
生产 `.env`。完整且精确锁定的 Python 包版本位于 `requirements.txt`，前端版本位于
`apps/workspace-web/package-lock.json`。日常启动命令如下：

```bash
cp .env.example .env
# 使用 Python 3.12 或更高版本
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,infra,legacy]'
.venv/bin/python scripts/init_data.py
cd apps/workspace-web
npm ci
NEXT_TELEMETRY_DISABLED=1 npm run build
```

初始化只创建目录和本地 SQLite 表，不启动 Web、API、数据库服务器或 SSH 隧道。
样本、报告和知识文献初始为空。参考数据库、FMT 模型及生信 worker 需要另行准备。

## 以后部署时启动与停止

仅在决定部署时，从项目根目录执行：

```bash
bash deploy/start.sh
bash deploy/status.sh
bash deploy/stop.sh
```

浏览器访问 `http://<当前服务器IP>:8502/`。Next.js 默认监听 `0.0.0.0:8502`，
通过同源 `/backend/*` 转发到 `127.0.0.1:8503`；可选 daemon 仅监听 `127.0.0.1:7438`。
无需域名、跳板机或反向 SSH 隧道。脚本不修改防火墙或路由。

端口可通过 `.env` 的 `WGS_WEB_PORT`、`WGS_API_PORT`、`WGS_PORT` 修改。
修改 API 端口后必须重新构建前端，使代理路由与后端一致。默认依赖环境为项目的 `.venv/`，
可通过 `WGS_ENV_ROOT` 覆盖；启动、停止和状态脚本读取同一份 `.env`。

完整数据目录与可选依赖说明见 [单服务器架构](docs/SINGLE_SERVER.md)。

## 开发与验证

```bash
# Python
.venv/bin/pytest

# Web
cd apps/workspace-web
npm ci
npm run build
```

FastAPI 开发启动：

```bash
.venv/bin/python -m uvicorn app.main:app --app-dir apps/workspace-api --host 127.0.0.1 --port 8503 --reload
```

## 安全约束

- API Key 只通过环境变量或权限受控的运行期配置注入，不提交到源码。
- Pipeline、报告覆盖及其他写操作必须经过确认和审计。
- 临床关联结果仅供科研分析，不能替代临床诊断或治疗决策。
- 沙箱只允许访问配置的工作区根目录。

服务列表见 [当前系统](docs/ACTIVE_SYSTEM.md)。
