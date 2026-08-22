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
from config.config import ApprovalPolicy, Config

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
        async with Agent(config=self.config, confirmation_callback=self.tui.handle_confirmation) as agent:
            self.agent = agent
            while True:
                try:
                    user_input=console.input("[bold green]You:[/bold green] ").strip()
                    if not user_input:
                        continue
                    
                    if user_input.startswith('/'):
                        should_continue=self._handle_command(user_input)
                        if not should_continue:
                            break
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
        tool=self.agent.session.tool_registry.get(tool_name)
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
                    event.data.get("diff", None),
                    event.data.get("exit_code"),
                )
                
        return final_response
    
    def _handle_command(self, command: str) -> bool:
        cmd=command.lower().strip()
        parts=cmd.split(maxsplit=1)
        cmd_name=parts[0]
        cmd_args=parts[1] if len(parts)>1 else ""
        if cmd_name == '/exit' or cmd_name == '/quit':
            return False
        elif command == '/help':
            self.tui.show_help()
        elif command == '/clear':
            self.agent.session.context_manager.clear()
            self.agent.session.loop_detector.clear()
            console.print("[bold green]Conversation history and loop detection cleared[/bold green]")
        elif command == '/config':
            console.print("\n[bold green]Current configuration:[/bold green]")
            console.print(f"  Model: {self.config.model_name}")
            console.print(f"  Temperature: {self.config.temperature}")
            console.print(f"  Approval: {self.config.approval.value}")
            console.print(f"  Working Dir: {self.config.cwd}")
            console.print(f"  Max Turns: {self.config.max_turns}")
            console.print(f"  Hooks Enabled: {self.config.hooks_enabled}")
        elif cmd_name == '/model':
            if cmd_args:
                self.config.model_name=cmd_args
                console.print(f"[bold green]Model changed to: {self.config.model_name}[/bold green]")
            else:
                console.print(f"Current model: {self.config.model_name}")
        elif cmd_name == '/approval':
            if cmd_args:
                try:
                    approval=ApprovalPolicy(cmd_args)
                    self.config.approval=approval
                    console.print(f"[bold green]Approval Policy changed to: {approval.value}[/bold green]")
                except:
                    console.print(f"[bold red]Invalid approval policy: {cmd_args}[/bold red]")
                    console.print(f"[bold red]Valid policies are: {', '.join([p.value for p in ApprovalPolicy])}.[/bold red]")
            else:
                console.print(f"Current approval policy is: {self.config.approval.value}")
                
        elif cmd_name == '/stats':
            stats=self.agent.session.get_stats()
            console.print("\n[bold green]Session Statistics:[/bold green]")
            for key, value in stats.items():
                console.print(f"  {key.capitalize()}: {value}")
        elif cmd_name == '/tools':
            tools=self.agent.session.tool_registry.get_tools()
            console.print(f"\n[bold green]Available Tools: ({len(tools)})[/bold green]")
            for tool in tools:
                console.print(f" • {tool.name}")
        elif cmd_name == '/mcp':
            mcp_server=self.agent.session.mcp_manager.get_all_servers()
            console.print(f"\n[bold green]Available MCP Servers: ({len(mcp_server)})[/bold green]")
            for server in mcp_server:
                status_color='green' if server['status'] == 'connected' else 'red'
                console.print(f" • {server['name']} (Status: [bold {status_color}]{server['status']}[/bold {status_color}], Tools: {server['tools']})")
        else:
            console.print(f"[bold red]Unknown command: {cmd_name}[/bold red]")
        return True
        
            

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