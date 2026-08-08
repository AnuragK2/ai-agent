from rich.console import Console
from rich.theme import Theme
from rich.rule import Rule
from rich.text import Text
from rich.panel import Panel
from typing import Any
from rich.table import Table
from rich import box
from rich.console import Group
from pathlib import Path
from utils.paths import display_path_rel_to_cwd
import re
from rich.syntax import Syntax
from config.config import Config
from tools.base import FileDiff
from utils.text import truncate_text

AGENT_THEME = Theme({
    #General
    "info": "dim cyan",
    "error": "bold red",
    "success": "bold green",
    "warning": "bold yellow",
    "dim": "dim",
    "muted":"grey50",
    "border":"grey30",
    "highlight": "bold cyan",
    #Roles
    "user":"bold bright_blue",
    "assistant":"bright_white",
    
    #Tools
    "tool":"bright_magenta bold",
    "tool.read": "cyan",
    "tool.write": "yellow",
    "tool.error": "red",
    "tool.success": "green",
    "tool.warning": "yellow",
    "tool.info": "cyan",
    "tool.debug": "magenta",
    "tool.trace": "white",
    "tool.highlight": "bold cyan",
    "tool.dim": "dim",
    "tool.muted": "grey50",
    "tool.border": "grey30",
    "tool.shell":"magenta",
    "tool.network": "bright_blue",
    "tool.memory": "bright_green",
    "tool.file": "bright_yellow",
    "tool.database": "bright_red",
    "tool.api": "magenta",
    "tool.web": "bright_cyan",
    "tool.email": "bright_magenta",
    "tool.calendar": "bright_blue",
    "tool.calendar": "bright_blue",
    "tool.mcp": "bright_cyan",
    "tool.mcp.read": "cyan",
    "tool.mcp.write": "yellow",
    "tool.mcp.error": "red",
    "tool.mcp.success": "green",
    "tool.mcp.warning": "yellow",
    "tool.mcp.info": "cyan",
    "tool.mcp.debug": "magenta",
    "tool.mcp.trace": "white",
    "tool.mcp.highlight": "bold cyan",
    "tool.mcp.dim": "dim",
    "tool.mcp.muted": "grey50",
    "tool.mcp.border": "grey30",
    "tool.mcp.shell":"magenta",
    "tool.mcp.network": "bright_blue",
    "tool.mcp.memory": "bright_green",
    "tool.mcp.file": "bright_yellow",
    "tool.mcp.database": "bright_red",
    "tool.mcp.api": "magenta",
    "tool.mcp.web": "bright_cyan",
    "tool.mcp.email": "bright_magenta",
    "tool.mcp.calendar": "bright_blue",
    "tool.mcp.calendar": "bright_blue",
    "tool.mcp.mcp": "bright_cyan",
    "tool.mcp.mcp.read": "cyan",
    "tool.mcp.mcp.write": "yellow",
    "tool.mcp.mcp.error": "red",
    "tool.mcp.mcp.success": "green",
    "tool.mcp.mcp.warning": "yellow",
    "tool.mcp.mcp.info": "cyan",
    "tool.mcp.mcp.debug": "magenta",
    "tool.mcp.mcp.trace": "white",
    "tool.mcp.mcp.highlight": "bold cyan",
    "tool.mcp.mcp.dim": "dim",
    "tool.mcp.mcp.muted": "grey50",
    "tool.mcp.mcp.border": "grey30",
    "tool.mcp.mcp.shell":"magenta",
    "tool.mcp.mcp.network": "bright_blue",
    "tool.mcp.mcp.memory": "bright_green",
    "tool.mcp.mcp.file": "bright_yellow",
    "tool.mcp.mcp.database": "bright_red",
    "tool.mcp.mcp.api": "magenta",
    "tool.mcp.mcp.web": "bright_cyan",
    "tool.mcp.mcp.email": "bright_magenta",
    "tool.mcp.mcp.calendar": "bright_blue",
    
    #Code/Blocks
    "code": "white",
    "block":"dim grey39",
    "block.border":"grey30",
    "block.border.left":"grey30",
    "block.border.right":"grey30",
    "block.border.top":"grey30",
    "block.border.bottom":"grey30",
    "block.border.top.left":"grey30",
    "block.border.top.right":"grey30",
    "block.border.bottom.left":"grey30",
    "block.border.bottom.right":"grey30",
})

_console : Console | None = None
def get_console() -> Console:
    global _console
    if _console is None:
        _console = Console(theme=AGENT_THEME, highlight=False)
    return _console

class TUI:
    def __init__(self, config: Config, console: Console | None = None)-> None:
        self.console = console or get_console()
        self._assistant_stream_open=False
        self.tool_args_by_call_id: dict[str, dict[str, Any]] = {}
        self.config = config
        self.cwd = self.config.cwd
        self._max_block_tokens=240
    
    def begin_assistant(self)->None:
        self.console.print()
        self.console.print(Rule(Text("Assistant", style="assistant")))
        self._assistant_stream_open=True
    
    def end_assistant(self)->None:
        if self._assistant_stream_open:
            self.console.print()
        self._assistant_stream_open=False
        
    def stream_assistant_delta(self, content: str)-> None:
        self.console.print(content, end="", markup=False)

    def print_error(self, message: str)-> None:
        self.console.print()
        self.console.print(f"[error]Error: {message}[/error]")
        
    def _ordered_args(self, tool_name: str, args: dict[str, Any])-> list[tuple[str, Any]]:
        _PREFERRED_ORDER={
            'read_file':['path','offset','limit'],
            'write_file':['path','create_directories','content'],
        }
        preferred= _PREFERRED_ORDER.get(tool_name, [])
        ordered: list[tuple[str, Any]] = []
        seen: set[str] = set()
        
        for key in preferred:
            if key in args and key not in seen:
                ordered.append((key, args[key]))
                seen.add(key)
                
        remaining_keys=set(args.keys()-seen) 
        ordered.extend((key, args[key]) for key in remaining_keys)
        return ordered
        
    def _render_args_table(self, tool_name: str, args: dict[str, Any])-> Table:
        table=Table.grid(padding=(0,1))
        table.add_column(style="muted", justify="right", no_wrap=True)
        table.add_column(style="code", overflow="fold")
        
        for key, value in self._ordered_args(tool_name, args):
            if isinstance(value, str):
                if key in {'content', 'old_string', 'new_string'}:
                    line_count=len(value.splitlines()) or 0
                    byte_count=len(value.encode('utf-8', errors='replace'))
                    value=f"{line_count} lines • {byte_count} bytes"
                    
            table.add_row(key, value)
        return table
        
    
    def tool_call_start(self, call_id: str, name: str, tool_kind: str | None, arguments: dict[str, Any])-> None:
        self.tool_args_by_call_id[call_id] = arguments
        border_style= f"tool.{tool_kind}" if tool_kind else "tool"
        
        title=Text.assemble(
            ("⏺", "muted"),
            (name, "tool"),
            (" ", "muted"),
            (f"#{call_id[:8]}", "tool.highlight"),
        )
        
        display_args=dict(arguments)
        for key in ('path','cwd'):
            val=display_args.get(key)
            if isinstance(val, str) and self.cwd:
                display_args[key]=str(display_path_rel_to_cwd(val, self.cwd))
                
                
        panel=Panel(
            self._render_args_table(name, display_args) if display_args else Text("(no arguments)", style="tool.dim"),
            title=title,
            padding=(1,2),
            box=box.ROUNDED,
            border_style=border_style,
            subtitle=Text('running...', style="tool.highlight"),
            title_align="left",
            subtitle_align="right",
        )
        self.console.print()
        self.console.print(panel)
        
        
    def _extract_read_file_code(self, text: str) -> tuple[int, str] | None:
        body = text

        header_match = re.match(
            r"^Showing lines (\d+)\s*-\s*(\d+) of (\d+)\.?(?:\s*\|\s*.*)?\n\n",
            text,
        )
        if header_match:
            body = body[header_match.end():]

        code_lines: list[str] = []
        start_line: int | None = None

        for line in body.splitlines():
            # read_file formats as "{n:6} | {content}"
            m = re.match(r"^\s*(\d+) \| (.*)$", line)
            if not m:
                return None
            line_num = int(m.group(1))
            code_line = m.group(2)
            if start_line is None:
                start_line = line_num
            code_lines.append(code_line)

        if start_line is None:
            return None
        return start_line, "\n".join(code_lines)

    def _guess_language(self, path: str | None) -> str:
        if not path:
            return "text"
        suffix = Path(path).suffix.lower()
        return {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "jsx",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".json": "json",
            ".toml": "toml",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".sh": "bash",
            ".bash": "bash",
            ".zsh": "bash",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".kt": "kotlin",
            ".swift": "swift",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".hpp": "cpp",
            ".css": "css",
            ".html": "html",
            ".xml": "xml",
            ".sql": "sql",
        }.get(suffix, "text")
        
    def print_welcome(self, title:str, lines: list[str]) -> None:
        body= "\n".join(lines)
        self.console.print(
            Panel(
                Text(body, style="code"),
                title=Text(title, style="highlight"),
                title_align="left",
                border_style="border",
                box=box.ROUNDED,
                padding=(1,2),
            )
        )

    def tool_call_complete(
        self,
        call_id: str,
        name: str,
        tool_kind: str | None,
        success: bool,
        output: str,
        error: str | None,
        metadata: dict[str, Any] | None,
        truncated: bool,
        diff: str | None,
    ) -> None:
        border_style = f"tool.{tool_kind}" if tool_kind else "tool"
        status_icon = "✔" if success else "✘"
        status_style = "success" if success else "error"

        title = Text.assemble(
            (f"{status_icon} ", status_style),
            (name, "tool"),
            (" ", "muted"),
            (f"#{call_id[:8]}", "tool.highlight"),
        )

        primary_path = None
        blocks: list[Any] = []
        if isinstance(metadata, dict) and isinstance(metadata.get("path"), str):
            primary_path = metadata.get("path")

        if name == "read_file" and success:
            extracted = self._extract_read_file_code(output)
            if extracted is not None and primary_path:
                start_line, code = extracted
                shown_start = metadata.get("shown_start") if metadata else None
                shown_end = metadata.get("shown_end") if metadata else None
                total_lines = metadata.get("total_lines") if metadata else None
                language = self._guess_language(primary_path)

                header_parts = [display_path_rel_to_cwd(primary_path, self.cwd)]
                if (
                    shown_start is not None
                    and shown_end is not None
                    and total_lines is not None
                ):
                    header_parts.append(
                        f" • lines {shown_start}-{shown_end} of {total_lines}"
                    )
                blocks.append(Text("".join(header_parts), style="tool.highlight"))
                blocks.append(
                    Syntax(
                        code,
                        language,
                        theme="monokai",
                        line_numbers=True,
                        start_line=start_line,
                        word_wrap=False,
                    )
                )
            else:
                blocks.append(
                    Syntax(
                        output,
                        self._guess_language(primary_path),
                        theme="monokai",
                        line_numbers=False,
                        word_wrap=False,
                    )
                )
        elif not success and error:
            blocks.append(Text(error, style="error"))
        elif name == "write_file" and success and diff:
            output_line = output.strip() if output.strip() else "Completed"
            blocks.append(Text(output_line, style="tool.success"))
            diff_display = truncate_text(diff, self.config.model_name, self._max_block_tokens)
            blocks.append(Syntax(diff_display, "diff", theme="monokai", word_wrap=True))
        elif output:
            blocks.append(Text(output, style="code"))
            
        if truncated:
            blocks.append(Text("(note: tool output was truncated)", style="warning"))

        if not blocks:
            blocks.append(Text("(no output)", style="tool.dim"))

        panel = Panel(
            Group(*blocks),
            title=title,
            padding=(1, 2),
            box=box.ROUNDED,
            border_style=border_style,
            subtitle=Text("Done" if success else "Failed", style=status_style),
            title_align="left",
            subtitle_align="right",
        )
        self.console.print()
        self.console.print(panel)
        self.tool_args_by_call_id.pop(call_id, None)
