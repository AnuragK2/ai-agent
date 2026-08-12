from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field
from config.config import Config
import uuid


class TodosParams(BaseModel):
    action: str = Field(
        ...,
        description=(
            "Action: 'add' (create one or more todos), 'complete' (mark done by id), "
            "'list', or 'clear'."
        ),
    )
    id: str | None = Field(None, description="Todo ID (required for complete)")
    content: str | None = Field(None, description="Single todo text (for add)")
    items: list[str] | None = Field(
        None,
        description=(
            "Multiple todo texts to add at once. Prefer this when planning a multi-step "
            "task so every stage is tracked before you start implementing."
        ),
    )


class TodosTool(Tool):
    name = "todos"
    description = (
        "Manage a session task list. For multi-step work (especially when the user asks "
        "you to plan), add the plan steps first with action=add and items=[...], then "
        "complete each id as you finish. Do not wait until the end to create todos."
    )
    kind = ToolKind.MEMORY
    schema = TodosParams

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._todos: dict[str, str] = {}

    def _snapshot(self) -> list[dict[str, str]]:
        return [{"id": todo_id, "content": text} for todo_id, text in self._todos.items()]

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = TodosParams(**invocation.params)
        action = params.action.lower().strip()

        if action == "add":
            to_add: list[str] = []
            if params.items:
                to_add.extend(item.strip() for item in params.items if item and item.strip())
            if params.content and params.content.strip():
                to_add.append(params.content.strip())
            if not to_add:
                return ToolResult.error_result("`content` or `items` is required for 'add'")

            added: list[dict[str, str]] = []
            for text in to_add:
                todo_id = str(uuid.uuid4())[:8]
                self._todos[todo_id] = text
                added.append({"id": todo_id, "content": text})

            lines = [f"Added {len(added)} todo(s):"]
            for item in added:
                lines.append(f"- [{item['id']}] {item['content']}")
            return ToolResult.success_result(
                "\n".join(lines),
                metadata={
                    "action": "add",
                    "count": len(added),
                    "open": len(self._todos),
                    "added": added,
                    "todos": self._snapshot(),
                },
            )

        if action == "complete":
            if not params.id:
                return ToolResult.error_result("`id` is required for 'complete'")
            if params.id not in self._todos:
                return ToolResult.error_result(f"Todo not found: {params.id}")
            content = self._todos.pop(params.id)
            completed = {"id": params.id, "content": content}
            return ToolResult.success_result(
                f"Completed [{params.id}]: {content}",
                metadata={
                    "action": "complete",
                    "open": len(self._todos),
                    "completed": completed,
                    "todos": self._snapshot(),
                },
            )

        if action == "list":
            snapshot = self._snapshot()
            if not snapshot:
                return ToolResult.success_result(
                    "No open todos.",
                    metadata={"action": "list", "open": 0, "todos": []},
                )
            lines = [f"{len(snapshot)} open todo(s):"]
            for item in snapshot:
                lines.append(f"- [{item['id']}] {item['content']}")
            return ToolResult.success_result(
                "\n".join(lines),
                metadata={
                    "action": "list",
                    "open": len(snapshot),
                    "todos": snapshot,
                },
            )

        if action == "clear":
            count = len(self._todos)
            self._todos.clear()
            return ToolResult.success_result(
                f"Cleared {count} todo(s).",
                metadata={"action": "clear", "cleared": count, "open": 0, "todos": []},
            )

        return ToolResult.error_result(f"Invalid action: {params.action}")
