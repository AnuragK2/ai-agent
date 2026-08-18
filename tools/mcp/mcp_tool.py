from tools.base import Tool, ToolKind, ToolResult, ToolInvocation
from config.config import Config
from tools.mcp.client import MCPToolInfo
from tools.mcp.client import MCPClient
from typing import Any

class MCPTool(Tool):
    
    def __init__(self, config: Config, tool_info: MCPToolInfo, name: str, client: MCPClient) -> None:
        super().__init__(config)
        self._tool_info = tool_info
        self._client = client
        self.name = name
        self.description = tool_info.description

    @property
    def schema(self) -> dict[str, Any]:
        input_schema = self._tool_info.input_schema or {}
        return {
            'type': 'object',
            'properties': input_schema.get('properties', {}),
            'required': input_schema.get('required', []),
        }
    
    def is_mutating(self, params) -> bool:
        return True
    
    kind = ToolKind.MCP
    
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        try:
            result = await self._client.call_tool(self._tool_info.name, invocation.params)
            output = result.get('output', '')
            is_error=result.get('is_error', False)
            if is_error:
                return ToolResult.error_result(output)
            return ToolResult.success_result(output)
        except Exception as e:
            return ToolResult.error_result(f"Error calling MCP tool {self.name}: {str(e)}")
    