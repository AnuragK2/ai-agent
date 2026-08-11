from tools.base import Tool, ToolKind, ToolResult, ToolInvocation
from pydantic import BaseModel, Field
from pathlib import Path
from utils.paths import resolve_path


SKIP_DIR_NAMES = {
    'node_modules',
    '__pycache__',
    '.git',
    '.svn',
    '.hg',
    '.vscode',
    '.idea',
    '.pytest_cache',
    '.mypy_cache',
    '.ruff_cache',
    '.venv',
    'venv',
    '.tox',
    'dist',
    'build',
    '.egg-info',
}


class GlobParams(BaseModel):
    pattern: str = Field(
        ...,
        description=(
            'Glob pattern to match files. Patterns are recursive by default: '
            '`*.py` finds Python files in all subdirectories. Use `**` explicitly '
            'if you want (e.g. `src/**/*.ts`).'
        ),
    )
    path: str = Field('.', description='Directory path to search in (default: current directory)')


class GlobTool(Tool):
    name = 'glob'
    description = (
        'Find files matching a glob pattern across the directory tree. '
        '`*.py` and similar patterns search recursively (not just the root).'
    )
    kind = ToolKind.READ
    schema = GlobParams

    MAX_MATCHES = 1000

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = GlobParams(**invocation.params)
        search_path = resolve_path(invocation.cwd, params.path)
        if not search_path.exists() or not search_path.is_dir():
            return ToolResult.error_result(
                f"Directory {search_path} does not exist or is not a directory",
            )

        pattern = self._normalize_pattern(params.pattern)

        try:
            matches = [
                p
                for p in search_path.glob(pattern)
                if p.is_file() and not self._is_ignored(p, search_path)
            ]
        except Exception as e:
            return ToolResult.error_result(
                f"Error searching for files: {e}",
            )

        matches.sort(key=lambda p: str(p).lower())
        truncated = len(matches) > self.MAX_MATCHES
        matches = matches[: self.MAX_MATCHES]

        cwd = Path(invocation.cwd).resolve()
        output_lines: list[str] = []
        for file_path in matches:
            resolved = file_path.resolve()
            try:
                rel_path = resolved.relative_to(cwd)
            except ValueError:
                try:
                    rel_path = resolved.relative_to(search_path)
                except ValueError:
                    rel_path = resolved
            output_lines.append(rel_path.as_posix())

        if truncated:
            output_lines.append(f"... (limited to {self.MAX_MATCHES} matches)")

        if not output_lines:
            return ToolResult.success_result(
                f"No files matched `{params.pattern}`",
                metadata={
                    'path': str(search_path),
                    'pattern': params.pattern,
                    'matches': 0,
                },
            )

        return ToolResult.success_result(
            '\n'.join(output_lines),
            truncated=truncated,
            metadata={
                'path': str(search_path),
                'pattern': params.pattern,
                'matches': len(matches),
            },
        )

    def _normalize_pattern(self, pattern: str) -> str:
        pattern = pattern.strip().replace('\\', '/')
        while pattern.startswith('./'):
            pattern = pattern[2:]
        if pattern.startswith('/'):
            pattern = pattern.lstrip('/')
        if not pattern:
            return '**/*'
        if pattern.startswith('**/'):
            return pattern
        return f'**/{pattern}'

    def _is_ignored(self, path: Path, root: Path) -> bool:
        try:
            parts = path.relative_to(root).parts
        except ValueError:
            parts = path.parts
        return any(part in SKIP_DIR_NAMES for part in parts[:-1])
