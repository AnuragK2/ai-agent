from tools.builtin.read_file import ReadFileTool
from tools.base import Tool
from config.config import Config
from tools.builtin.write_file import WriteFileTool
from tools.builtin.edit_file import EditTool

__all__=['ReadFileTool', 'get_all_builtin_tools']

def get_all_builtin_tools(config: Config)->list[Tool]:
    return [
        ReadFileTool(config=config),
        WriteFileTool(),
        EditTool(),
    ]
