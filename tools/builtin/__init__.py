from tools.builtin.read_file import ReadFileTool
from tools.base import Tool
from config.config import Config
from tools.builtin.write_file import WriteFileTool
from tools.builtin.edit_file import EditTool
from tools.builtin.shell import ShellTool
from tools.builtin.list_dir import ListDirTool
from tools.builtin.grep import GrepTool
from tools.builtin.glob import GlobTool
from tools.builtin.web_search import WebSearchTool
from tools.builtin.web_fetch import WebFetchTool

__all__=['ReadFileTool', 'WriteFileTool', 'EditTool', 'ShellTool', 'get_all_builtin_tools', 'ListDirTool', 'GrepTool', 'GlobTool', 'WebSearchTool', 'WebFetchTool']

def get_all_builtin_tools(config: Config)->list[type[Tool]]:
    return [
        ReadFileTool,
        WriteFileTool,
        EditTool,
        ShellTool,
        ListDirTool,
        GrepTool,
        GlobTool,
        WebSearchTool,
        WebFetchTool,
    ]
