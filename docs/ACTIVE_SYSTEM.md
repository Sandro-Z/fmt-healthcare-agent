# 当前活动系统与迁移记录

## 唯一活动 Web 系统

| 服务 | 目录 | 端口 | 用途 |
|---|---|---:|---|
| workspace-web | `apps/workspace-web` | 8502 | Next.js 登录、样本、对话、知识库、报告与设置 |
| workspace-api | `apps/workspace-api` | 8503 | FastAPI 会话、样本、Agent、权限与基础设施接口 |
| agent-daemon | `src/wgs_agent` | 7438 | 可选 JSON-RPC 后台，仅配置模型密钥时启动 |

已停用并从活动源码删除：Streamlit 8501 服务、旧 FastAPI 8000 服务及其容器入口。

## 完整回退包

- 文件：`/storage/main/users/zhangrongpeng/data/fmt/apps/backups/WGS-FMT-Agent-v2-pre-monorepo-20261011-130527.tar.gz`
- SHA-256：`94281e4eb017e5727aefc88a9a12f410921dafeb73bb2f71408f6dd828504b6e`
- 校验状态：已通过 `tar -tzf` 完整性检查

项目迁移前没有 `.git` 目录，因此该归档是本次结构迁移的完整回退点。不要在确认新系统稳定前删除它。

## 回退原则

先停止当前服务，将当前目录改名保留，再把归档解压到 `apps` 目录。不要直接覆盖运行中的目录，
以免混合新旧文件。恢复后使用归档内原有部署脚本启动。
