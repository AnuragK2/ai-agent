import asyncio
import click
from agent.agent import Agent
from agent.events import AgentEventType
from ui.tui import TUI
from ui.tui import get_console
import sys
from dotenv import load_dotenv
from pathlib import Path
from config.loader import load_config
from config.config import Config

load_dotenv()


console=get_console()
class CLI:
    
    def __init__(self, config: Config):
        self.agent : Agent | None = None
        self.tui = TUI(config, console)
        self.config = config
        
    
    async def run_single(self, message : str) -> str | None:
        async with Agent(config=self.config) as agent:
            self.agent = agent
            return await self._process_message(message)
        
    async def run_interactive(self) -> str | None:
        self.tui.print_welcome(
            title="Welcome to the CLI",
            lines=[
                "This is a CLI for the agent.",
                "You can interact with the agent by typing commands.",
                "The agent will respond to your commands and provide information.",
                " ",
                f'model: "{self.config.model.name}"',
                f"cwd: {self.config.cwd}",
                'commands: /help /config /approval /model /exit'
            ],
        )
        async with Agent(config=self.config) as agent:
            self.agent = agent
            while True:
                try:
                    user_input=console.input("[bold green]You:[/bold green] ").strip()
                    if not user_input:
                        continue
                    await self._process_message(user_input)
                    # result = await self._process_message(user_input)
                    # if result:
                    #     console.print(result)
                    # else:
                    #     console.print("[bold red]Error:[/bold red] Failed to process message")
                        
                except KeyboardInterrupt:
                    console.print("\n[dim] Use /exit to quit[/dim]")
                except EOFError:
                    break
        
        console.print("[bold green]Goodbye![/bold green]")
                
    
    def _get_tool_kind(self, tool_name: str) -> str | None:
        tool_kind=None
        tool=self.agent.tool_registry.get(tool_name)
        if not tool:
            tool_kind=None
                
        tool_kind=tool.kind.value
        return tool_kind
    
    
    async def _process_message(self, message: str) -> str | None:
        if not self.agent:
            return None
        
        assistant_streaming=False
        final_response:str | None = None
        
        async for event in self.agent.run(message):
            if event.type==AgentEventType.TEXT_DELTA:
                content = event.data.get("content", "")
                if not assistant_streaming:
                    self.tui.begin_assistant()
                    assistant_streaming=True
                self.tui.stream_assistant_delta(content)    
            elif event.type==AgentEventType.TEXT_COMPLETE:
                    final_response = event.data.get("content", "")
                    if assistant_streaming:
                        self.tui.end_assistant()
                        assistant_streaming=False
            elif event.type==AgentEventType.AGENT_ERROR:
                error = event.data.get("error", "Unknown error occurred")
                if assistant_streaming:
                    self.tui.end_assistant()
                    assistant_streaming=False
                self.tui.print_error(error)
            elif event.type==AgentEventType.TOOL_CALL_START:
                tool_name = event.data.get("name", "Unknown tool")
                tool_kind=self._get_tool_kind(tool_name)
                
                self.tui.tool_call_start(
                    event.data.get("call_id", ""),
                    tool_name,
                    tool_kind,
                    event.data.get("arguments", {}),
                )
            
            elif event.type==AgentEventType.TOOL_CALL_COMPLETE:
                tool_name=event.data.get("name", "Unknown tool")
                tool_kind=self._get_tool_kind(tool_name)
                self.tui.tool_call_complete(
                    event.data.get("call_id", ""),
                    tool_name,
                    tool_kind,
                    event.data.get("success", False),
                    event.data.get("output", ""),
                    event.data.get("error"),
                    event.data.get("metadata"),
                    event.data.get("truncated", False),
                )
                
        return final_response
            

@click.command()
@click.argument("prompt", required=False)
@click.option("--cwd", '-c', help="Current working directory", type=click.Path(exists=True, file_okay=False, path_type=Path))

def main(prompt: str | None, cwd: Path | None):
    try:
        config=load_config(cwd=cwd)
    except Exception as e:
        console.print(f"[error]Configuration error: {e}[/error]")
        sys.exit(1)
    errors=config.validate()
    if errors:
        for error in errors:
            console.print(f"[error]Configuration error: {error}[/error]")
        sys.exit(1)
    
    cli=CLI(config)
    # messages = [{"role": "system", "content": prompt}]
    if prompt:
        result = asyncio.run(cli.run_single(prompt))
        if result is None:
            sys.exit(1)
    else:
        asyncio.run(cli.run_interactive())

if __name__ == "__main__":
    main()