from rich.console import Console
from rich.theme import Theme

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
    "tool_read": "cyan",
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
    def __init__(self, console: Console | None = None)-> None:
        self.console = console or get_console()
        
    def stream_assistant_delta(self, content: str)-> None:
        self.console.print(content, end="", markup=False)
        
    
        