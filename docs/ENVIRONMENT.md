# 正式运行环境

本项目由 Python 3.12 后端、Next.js 前端、默认随项目启动的 Elasticsearch Docker 实例，
以及可选的 MySQL、Redis、LitKG 服务组成。ES 可关闭自动托管并使用已有实例。
依赖版本由根目录 `environment.yml`、`uv.lock` 和 `apps/workspace-web/package-lock.json`
共同管理；密钥及服务器路径使用 `.env` 管理，但 `.env` 不进入 Git。

## 1. 创建统一环境

最直接的安装方式是在项目根目录使用完整锁定的 `requirements.txt`。该文件包含所有直接和
间接 Python 包的精确版本，以及基础设施、报告分析、FMT 模型和测试依赖：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

npm ci --prefix apps/workspace-web
npm run build --prefix apps/workspace-web
```

也可以使用 Conda 创建包含 Python、Node.js 和 Pandoc 的统一环境：

```bash
conda env create -f environment.yml
conda activate wgs-fmt-agent-v2
python -m pip install -r requirements.txt
npm ci --prefix apps/workspace-web
npm run build --prefix apps/workspace-web
```

已有同名环境更新时：

```bash
conda env update -n wgs-fmt-agent-v2 -f environment.yml --prune
python -m pip install -r requirements.txt
npm ci --prefix apps/workspace-web
npm run build --prefix apps/workspace-web
```

`torch` 在 `fmt` 依赖组中。若服务器需要指定 CUDA 版本，应先按服务器 CUDA/驱动版本安装
PyTorch，再执行其余安装，避免安装不匹配的 GPU wheel。

依赖声明变更后，使用以下命令重新生成精确版本文件：

```bash
uv lock
uv export --frozen --all-extras --no-hashes --no-annotate --no-header \
  --format requirements-txt \
  --output-file requirements.txt
```

## 2. 创建生产配置

```bash
cp .env.production.example .env
chmod 600 .env
```

至少替换以下占位符：

- `WGS_DATABASE_URL` 和 `WGS_MYSQL_URL` 中的 `CHANGE_ME`；
- `WGS_CLAIM_API_TOKEN`；
- `DEEPSEEK_API_KEY`，或者清空它并配置实际使用的其他模型服务。

不要提交 `.env`。部署脚本会在启动服务时读取项目根目录的 `.env`。

## 3. 外部服务

正式环境按实际启用功能准备以下服务：

- MySQL 8：用户、会话和业务数据；
- Redis 7：短期/长期记忆缓存；
- Elasticsearch 8：关键词、向量和融合检索，`deploy/start.sh` 默认通过本机 Docker 启动；
- LitKG Claim API：Claim 和关系知识检索；
- mProject：宏基因组样本处理；
- Nextflow：需要工作流编排时启用；
- TeX Live/XeLaTeX：高质量 PDF 报告，可选。

这些服务不应把口令直接写入仓库。生产环境还应限制其监听地址并配置访问控制。
托管 ES 自动生成私有密码文件，仅发布回环端口。启动前需准备可访问的本机 Docker；
参数及数据卷备份方式见 [单服务器架构](SINGLE_SERVER.md#elasticsearch-随项目启动)。

## 4. 启动与验证

```bash
cd /storage/main/users/zhangrongpeng/data/fmt/apps/WGS-FMT-Agent-v2
bash deploy/start.sh
bash deploy/status.sh

curl -fsS http://127.0.0.1:8503/health
curl -I http://127.0.0.1:8502/
```

当前服务端口：Next.js `8502`、FastAPI `8503`、可选 Agent daemon `7438`。
