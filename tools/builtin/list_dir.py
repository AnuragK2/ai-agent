from tools.base import Tool, ToolKind, ToolResult, ToolInvocation
from pydantic import BaseModel, Field
from pathlib import Path
from utils.paths import resolve_path


class ListDirParams(BaseModel):
    path: str = Field('.', description='Directory path to list (default: current directory)')
    include_hidden: bool = Field(False, description='Whether to include hidden files and directories (default: False)')
    recursive: bool = Field(
        False,
        description=(
            'If true, recursively list all files and subdirectories under path. '
            'Use this when exploring a project tree or when the user asks to read/list '
            'everything in a directory — do not call read_file on directory paths.'
        ),
    )


class ListDirTool(Tool):
    name = 'list_dir'
    description = (
        'List the contents of a directory. Set recursive=true to walk subdirectories '
        'and return relative paths for the whole tree. Use list_dir (not read_file) for directories.'
    )
    kind = ToolKind.READ
    schema = ListDirParams

    MAX_ENTRIES = 2000

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ListDirParams(**invocation.params)
        dir_path = resolve_path(invocation.cwd, params.path)
        if not dir_path.exists() or not dir_path.is_dir():
            return ToolResult.error_result(
                f"Directory {dir_path} does not exist",
            )

        try:
            if params.recursive:
                lines, truncated = self._list_recursive(dir_path, params.include_hidden)
            else:
                lines, truncated = self._list_flat(dir_path, params.include_hidden)
        except OSError as e:
            return ToolResult.error_result(
                f"Failed to list directory {dir_path}: {e}",
            )

        if not lines:
            return ToolResult.success_result(
                'Directory is empty',
                metadata={
                    'path': str(dir_path),
                    'entries': 0,
                    'recursive': params.recursive,
                },
            )

        output = '\n'.join(lines)
        if truncated:
            output += f'\n... [truncated at {self.MAX_ENTRIES} entries]'

        return ToolResult.success_result(
            output,
            truncated=truncated,
            metadata={
                'path': str(dir_path),
                'entries': len(lines),
                'recursive': params.recursive,
            },
        )

    def _should_include(self, path: Path, include_hidden: bool) -> bool:
        if include_hidden:
            return True
        return not path.name.startswith('.')

    def _list_flat(self, dir_path: Path, include_hidden: bool) -> tuple[list[str], bool]:
        items = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        items = [item for item in items if self._should_include(item, include_hidden)]
        truncated = len(items) > self.MAX_ENTRIES
        items = items[: self.MAX_ENTRIES]
        lines: list[str] = []
        for item in items:
            lines.append(f'{item.name}/' if item.is_dir() else item.name)
        return lines, truncated

    def _list_recursive(self, dir_path: Path, include_hidden: bool) -> tuple[list[str], bool]:
        lines: list[str] = []
        truncated = False

        def walk(current: Path) -> None:
            nonlocal truncated
            if truncated:
                return
            try:
                children = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except OSError:
                return
            for child in children:
                if truncated:
                    return
                if not self._should_include(child, include_hidden):
                    continue
                rel = child.relative_to(dir_path).as_posix()
                if child.is_dir():
                    lines.append(f'{rel}/')
                    if len(lines) >= self.MAX_ENTRIES:
                        truncated = True
                        return
                    walk(child)
                else:
                    lines.append(rel)
                    if len(lines) >= self.MAX_ENTRIES:
                        truncated = True
                        return

        walk(dir_path)
        return lines, truncated
