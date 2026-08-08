from tools.builtin.read_file import ReadFileTool
from tools.base import Tool
from config.config import Config

__all__=['ReadFileTool', 'get_all_builtin_tools']

def get_all_builtin_tools(config: Config)->list[Tool]:
    return [
        ReadFileTool(
            model_name=config.model.name,
            max_output_tokens=config.max_tool_output_tokens,
        )
    ]
