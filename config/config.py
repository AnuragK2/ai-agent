from pydantic import BaseModel, Field
from pathlib import Path
import os

class ModelConfig(BaseModel):
    name: str = "gpt-4o-mini"
    temperature: float = Field(default=1, ge=0.0, le=2.0)
    context_window: int | None = None
    
    
    

class Config(BaseModel):
    model: ModelConfig = Field(default=ModelConfig())
    cwd: Path = Field(default=Path.cwd())
    max_turns: int = 100
    max_tool_output_tokens: int = 50_000
    
    developer_instructions: str | None = None
    user_instructions: str | None = None
    debug: bool = False
    
    @property
    def api_key(self) -> str | None:
        return os.environ.get("OPENAI_API_KEY") or os.environ.get("API_KEY")
    
    @property
    def base_url(self) -> str | None:
        return os.environ.get("BASE_URL")
    
    @property
    def model_name(self) -> str:
        return self.model.name
    
    @model_name.setter
    def model_name(self, value: str) -> None:
        self.model.name = value
        
    @property
    def temperature(self) -> float:
        return self.model.temperature
    
    @temperature.setter
    def temperature(self, value: float) -> None:
        self.model.temperature = value
        
    def validate(self) -> None:
        errors: list[str] = []
        if not self.api_key:
            errors.append("OPENAI_API_KEY is not set. Set OPENAI_API_KEY in the environment (or .env)")
        if not self.cwd.exists():
            errors.append(f"Working directory {self.cwd} does not exist")
        
        return errors
    
    