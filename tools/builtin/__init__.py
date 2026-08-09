from tools.builtin.read_file import ReadFileTool
from tools.base import Tool
from config.config import Config
from tools.builtin.write_file import WriteFileTool
from tools.builtin.edit_file import EditTool
from tools.builtin.shell import ShellTool

__all__=['ReadFileTool', 'WriteFileTool', 'EditTool', 'ShellTool', 'get_all_builtin_tools']

def get_all_builtin_tools(config: Config)->list[type[Tool]]:
    return [
        ReadFileTool,
        WriteFileTool,
        EditTool,
        ShellTool
    ]
