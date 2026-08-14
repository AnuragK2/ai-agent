from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field
from config.config import Config
from config.loader import get_data_dir
import uuid
import json


class MemoryParams(BaseModel):
    action: str = Field(
        ...,
        description=(
            "Action: 'set', 'get', 'delete', 'list', or 'clear'."
        ),
    )
    key: str | None = Field(None, description="Key to store the memory or retrieve the value from (required for 'set', 'get' and 'delete')")
    value: str | None = Field(None, description="Value to store for the key (required for 'set')")

class MemoryTool(Tool):
    name = "memory"
    description = (
        "Store and retrieve persistent memory. Use this to remember user preferences, important context or notes."
    )
    kind = ToolKind.MEMORY
    schema = MemoryParams
    
    def _load_memory(self) -> dict:
        data_dir = get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        path= data_dir/'user_memory.json'
        
        if not path.exists():
            return {'entries': {}}
        
        try:
            content=path.read_text(encoding='utf-8')
            return json.loads(content)
        except Exception:
            return {'entries': {}}
        
    
    def _save_memory(self, memory: dict) -> None:
        data_dir = get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        path= data_dir/'user_memory.json'
        path.write_text(json.dumps(memory, indent=2, ensure_ascii=False), encoding='utf-8')
        
        
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = MemoryParams(**invocation.params)
        
        if params.action.lower() == "set":
            if not params.key and not params.value:
                return ToolResult.error_result("Key and value are required for 'set' action")
            
            memory=self._load_memory()
            memory['entries'][params.key] = params.value
            self._save_memory(memory)
            return ToolResult.success_result(f"Memory set for key: {params.key}")
        
        elif params.action.lower() == "get":
            if not params.key:
                return ToolResult.error_result("Key is required for 'get' action")
            
            memory=self._load_memory()
            if params.key not in memory.get('entries', {}):
                return ToolResult.error_result(f"Memory entry not found: {params.key}")
            
            return ToolResult.success_result(memory.get('entries', {})[params.key])
        
        elif params.action.lower() == "delete":
            if not params.key:
                return ToolResult.error_result("Key is required for 'delete' action")
            
            memory=self._load_memory()
            if params.key not in memory.get('entries', {}):
                return ToolResult.error_result(f"Memory entry not found: {params.key}", metadata={
                    "found": False
                })
            
            del memory.get['entries'][params.key]
            self._save_memory(memory)
            return ToolResult.success_result(f"Memory deleted for key: {params.key}", metadata={
                "found": True
            })
            
        elif params.action.lower() == "list":
            memory=self._load_memory()
            entries=memory.get('entries', {})
            if not entries:
                return ToolResult.success_result("No memory entries found", metadata={
                    "found": False
                })
            
            lines=[f"Stored memory entries: {len(entries)}"]
            for key, value in sorted(entries.items()):
                lines.append(f"- {key}: {value}")
            return ToolResult.success_result("\n".join(lines), metadata={
                "found": True
            })
            
        elif params.action.lower() == "clear":
            memory=self._load_memory()
            count=len(memory.get('entries', {}))
            memory['entries'] = {}
            
            if count == 0:
                return ToolResult.success_result("No memory entries to clear")
            
            self._save_memory({'entries': {}})
            return ToolResult.success_result(f"Memory cleared: {count} entries")
            
        else:
            return ToolResult.error_result(f"Invalid action: {params.action}")