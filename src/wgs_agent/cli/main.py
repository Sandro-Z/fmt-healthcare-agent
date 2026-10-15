"""WGS.FMT-Agent CLI 入口"""

from __future__ import annotations

import asyncio
import os

import typer

from wgs_agent.core.config import get_config

cli = typer.Typer(
    name="wgs-agent",
    help="WGS.FMT 肠道微生物组多智能体分析平台",
    no_args_is_help=True,
)


@cli.command()
def daemon(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="监听地址"),
    port: int = typer.Option(7438, "--port", "-p", help="监听端口"),
) -> None:
    """启动 WGS.FMT-Agent daemon 服务"""
    from dotenv import load_dotenv
    load_dotenv()

    os.environ["WGS_HOST"] = host
    os.environ["WGS_PORT"] = str(port)

    from wgs_agent.core.app import CoreApp
    asyncio.run(CoreApp().run())


@cli.command()
def ping() -> None:
    """测试 daemon 连通性"""
    from dotenv import load_dotenv
    load_dotenv()

    config = get_config()
    import asyncio
    import json

    async def _ping():
        reader, writer = await asyncio.open_connection(config.host, config.port)
        request = json.dumps({
            "jsonrpc": "2.0",
            "id": "cli-ping",
            "method": "core.ping",
            "params": {},
        }) + "\n"
        writer.write(request.encode())
        await writer.drain()
        response = await reader.readline()
        print(response.decode().strip())
        writer.close()
        await writer.wait_closed()

    try:
        asyncio.run(_ping())
    except ConnectionRefusedError:
        typer.echo("daemon 未运行，请先执行: wgs-agent daemon", err=True)
        raise typer.Exit(1)


@cli.command()
def run(
    sample_id: str = typer.Option(..., "--sample", "-s", help="样本 ID"),
    task: str = typer.Option("analyze", "--task", "-t", help="任务类型: analyze/report/full"),
) -> None:
    """运行宏基因组分析任务"""
    from dotenv import load_dotenv
    load_dotenv()

    config = get_config()
    import asyncio
    import json

    async def _run():
        reader, writer = await asyncio.open_connection(config.host, config.port)
        request = json.dumps({
            "jsonrpc": "2.0",
            "id": "cli-run",
            "method": "agent.run",
            "params": {
                "goal": f"对样本 {sample_id} 执行 {task} 分析",
                "sample_id": sample_id,
                "task_type": task,
            },
        }) + "\n"
        writer.write(request.encode())
        await writer.drain()
        response = await reader.readline()
        print(response.decode().strip())
        writer.close()
        await writer.wait_closed()

    try:
        asyncio.run(_run())
    except ConnectionRefusedError:
        typer.echo("daemon 未运行，请先执行: wgs-agent daemon", err=True)
        raise typer.Exit(1)


@cli.command()
def tui(
    replay_run_id: str | None = typer.Option(None, "--replay", help="回放指定 run_id 的历史事件"),
) -> None:
    """启动 Textual TUI 界面"""
    from dotenv import load_dotenv
    load_dotenv()

    from wgs_agent.core.config import get_config
    from wgs_agent.tui.app import run as tui_run

    config = get_config()
    tui_run(config, replay_run_id=replay_run_id)


if __name__ == "__main__":
    cli()
