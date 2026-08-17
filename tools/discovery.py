import importlib.util
import inspect
import logging
import sys
from pathlib import Path
from types import ModuleType

from config.config import Config
from config.loader import get_config_dir
from tools.base import Tool
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolDiscoveryManager:
    def __init__(self, config: Config, registry: ToolRegistry):
        self.config = config
        self.registry = registry

    def _load_module(self, file_path: Path) -> ModuleType:
        module_name = f"discovered_tool_{file_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to load module {module_name} from {file_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def _find_tool_classes(self, module: ModuleType) -> list[type[Tool]]:
        tools: list[type[Tool]] = []
        for name in dir(module):
            obj = getattr(module, name)
            if (
                inspect.isclass(obj)
                and issubclass(obj, Tool)
                and obj is not Tool
                and obj.__module__ == module.__name__
            ):
                tools.append(obj)
        return tools

    def discover_from_directory(self, tool_dir: Path) -> None:
        if not tool_dir.exists() or not tool_dir.is_dir():
            return
        for file in tool_dir.glob("*.py"):
            if file.name.startswith("__"):
                continue
            try:
                module = self._load_module(file)
                tool_classes = self._find_tool_classes(module)
                if not tool_classes:
                    logger.debug("No Tool subclasses found in %s", file)
                    continue
                for tool_class in tool_classes:
                    tool = tool_class(self.config)
                    self.registry.register_tool(tool)
                    logger.debug("Discovered tool %s from %s", tool.name, file)
            except Exception:
                logger.exception("Failed to load discovered tool from %s", file)

    def discover_all(self) -> None:
        self.discover_from_directory(Path(self.config.cwd) / ".ai-agent" / "tools")
        self.discover_from_directory(get_config_dir() / "tools")
