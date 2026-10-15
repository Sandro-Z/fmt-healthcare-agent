"""Textual client for the retained WGS-FMT agent daemon."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Footer, Header, Input, RichLog, Static


class WgsAgentTui(App[None]):
    TITLE = "WGS-FMT Agent"
    SUB_TITLE = "Daemon client"

    def __init__(self, config: Any, replay_run_id: str | None = None) -> None:
        super().__init__()
        self.config = config
        self.replay_run_id = replay_run_id
        self._request_id = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            f"Daemon: {self.config.host}:{self.config.port}", id="connection"
        )
        yield RichLog(id="log", wrap=True, markup=True)
        with Horizontal():
            yield Input(placeholder="输入分析目标，例如：分析样本 SRR13068821", id="goal")
            yield Button("运行", id="run", variant="primary")
            yield Button("Ping", id="ping")
        yield Footer()

    async def on_mount(self) -> None:
        await self._ping()
        if self.replay_run_id:
            self.query_one("#log", RichLog).write(
                f"历史回放请求: {self.replay_run_id}（事件文件由 daemon 管理）"
            )

    async def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._request_id += 1
        reader, writer = await asyncio.open_connection(self.config.host, self.config.port)
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        writer.write((json.dumps(request, ensure_ascii=False) + "\n").encode())
        await writer.drain()
        response = await reader.readline()
        writer.close()
        await writer.wait_closed()
        return json.loads(response)

    async def _ping(self) -> None:
        log = self.query_one("#log", RichLog)
        try:
            response = await self._rpc("core.ping", {"client": "tui"})
            log.write(f"[green]Daemon 已连接[/green] {response}")
        except Exception as exc:
            log.write(f"[red]Daemon 连接失败[/red]: {exc}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ping":
            await self._ping()
            return
        if event.button.id != "run":
            return
        goal = self.query_one("#goal", Input).value.strip()
        if not goal:
            self.query_one("#log", RichLog).write("[yellow]请输入分析目标[/yellow]")
            return
        log = self.query_one("#log", RichLog)
        log.write(f"提交任务: {goal}")
        try:
            response = await self._rpc("agent.run", {"goal": goal})
            log.write(json.dumps(response, ensure_ascii=False, indent=2))
        except Exception as exc:
            log.write(f"[red]任务提交失败[/red]: {exc}")


def run(config: Any, replay_run_id: str | None = None) -> None:
    WgsAgentTui(config, replay_run_id=replay_run_id).run()
