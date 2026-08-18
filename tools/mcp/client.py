from __future__ import annotations
from fastmcp import Client
from fastmcp.client import SSETransport, StdioTransport
from config.config import MCPServerConfig
from pathlib import Path
import os
from enum import Enum
from dataclasses import dataclass, field
from typing import Any

class MCPServerStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"

@dataclass
class MCPToolInfo:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""

class MCPClient:
    def __init__(self, name: str, config: MCPServerConfig, cwd: Path)->None:
        self.name = name
        self.config = config
        self.cwd = cwd
        self.status=MCPServerStatus.DISCONNECTED
        self._client: Client | None = None
        self._tools: dict[str, MCPToolInfo] = {}

    @property
    def tools(self) -> list[MCPToolInfo]:
        return list(self._tools.values())

    def _expand_args(self) -> list[str]:
        cwd = str(self.config.cwd or self.cwd)
        return [arg.replace("{cwd}", cwd) for arg in self.config.args]

    def _create_transport(self)-> StdioTransport | SSETransport:
        if self.config.command:
            env = os.environ.copy()
            env.update(self.config.env)
            return StdioTransport(
                command=self.config.command,
                args=self._expand_args(),
                env=env,
                cwd=str(self.config.cwd or self.cwd),
                log_file=Path(os.devnull),
            )
        else:
            return SSETransport(url=self.config.url)
    
    async def connect(self)-> None:
        if self.status == MCPServerStatus.CONNECTED:
            return
        if self.status == MCPServerStatus.CONNECTING:
            return
        self.status = MCPServerStatus.CONNECTING
        
        try:
            self._client = Client(transport=self._create_transport())
            await self._client.__aenter__()
            tool_result= await self._client.list_tools()
            for tool in tool_result:
                self._tools[tool.name] = MCPToolInfo(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=(
                        getattr(tool, "input_schema", None)
                        or getattr(tool, "inputSchema", None)
                        or {}
                    ),
                    server_name=self.name
                )
            self.status = MCPServerStatus.CONNECTED
        except Exception:
            self.status = MCPServerStatus.ERROR
            raise
    
    async def disconnect(self)-> None:
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None
        self._tools.clear()
        self.status = MCPServerStatus.DISCONNECTED
        
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if not self._client or self.status != MCPServerStatus.CONNECTED:
            raise RuntimeError(f"Client not connected to server {self.name}")
        
        result= await self._client.call_tool(tool_name, arguments)
        output = []
        for item in result.content:
            if hasattr(item, "text"):
                output.append(item.text)
            else:
                output.append(str(item))
            
        return {'output': '\n'.join(output), 'is_error': result.is_error}
        
        
        