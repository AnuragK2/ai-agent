from tools.base import Tool, ToolKind, ToolInvocation, ToolResult
from pydantic import BaseModel, Field
from pathlib import Path
import os
import fnmatch
import sys
import asyncio
import signal

BLOCKED_COMMANDS={
    "rm -rf /",
    "rm -rf ~",
    "rm -rf /*",
    "dd if=/dev/zero",
    "dd if=/dev/random",
    "mkfs",
    "fdisk",
    "parted",
    ":(){ :|:& };:",  # Fork bomb
    "chmod 777 /",
    "chmod -R 777",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init 0",
    "init 6",
    "exit",
    "quit",
    "logout",
    "su",
    "sudo",
    "doas",
    "pkexec",
    "kdesudo",
}

class ShellParams(BaseModel):
    command: str = Field(..., description="The shell command to execute.")
    timeout: int = Field(120, ge=1, le=600, description='Timeout in seconds (default: 120). Prefer short timeouts; do not raise them to wait on interactive prompts.')
    cwd: str | None = Field(None, description='Working directory for the command')
    stdin: str | None = Field(
        None,
        description=(
            "Optional text fed to the process on stdin. Required when the command reads "
            "input() or similar prompts — the shell is non-interactive and will not wait "
            "for a human. Example: 'Alice\\n' for a single prompt."
        ),
    )

class ShellTool(Tool):
    name='shell'
    kind=ToolKind.SHELL
    description=(
        "Execute shell commands non-interactively. Stdin is closed unless you pass `stdin`. "
        "For scripts that call input()/read prompts, provide the answers via `stdin` "
        "(e.g. printf-style lines ending with newlines). Do not increase timeout to wait for user input."
    )
    schema=ShellParams
    
    async def execute(self, invocation:ToolInvocation)->ToolResult:
        params=ShellParams(**invocation.params)
        
        command=params.command.lower().strip()
        
        for blocked in BLOCKED_COMMANDS:
            if blocked in command:
                return ToolResult.error_result(
                    f"Command {command} is blocked for safety reasons.",
                    metadata={
                        'blocked':True,
                    }
                )
        
        if params.cwd:
            cwd=Path(params.cwd)
            if not cwd.is_absolute():
                cwd= invocation.cwd / cwd
        else:
            cwd= invocation.cwd
            
        if not cwd.exists():
            return ToolResult.error_result(
                f"Working directory {cwd} does not exist.",
            )
        
        env=self._build_environment()
        if sys.platform == 'win32':
            shell_cmd=['cmd.exe', '/c', params.command]
        else:
            shell_cmd=['/bin/bash', '-c', params.command]

        stdin_bytes: bytes | None = None
        if params.stdin is not None:
            stdin_bytes = params.stdin.encode('utf-8')
            stdin = asyncio.subprocess.PIPE
        else:
            stdin = asyncio.subprocess.DEVNULL
        
        process=await asyncio.create_subprocess_exec(
            *shell_cmd,  
            stdin=stdin,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
            start_new_session=True,
        )
        try:
            stdout_data, stderr_data=await asyncio.wait_for(
                process.communicate(input=stdin_bytes),
                timeout=params.timeout,
            )
        except asyncio.TimeoutError:
            if sys.platform!='win32':
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                process.kill()
            await process.wait()
            return ToolResult.error_result(
                f"Command timed out after {params.timeout} seconds. "
                f"If the command waits for interactive input, re-run with the `stdin` parameter.",
                exit_code=None,
            )
        stdout=stdout_data.decode('utf-8',errors='replace')
        stderr=stderr_data.decode('utf-8',errors='replace')
        exit_code=process.returncode
        
        output=""
        if stdout.strip():
            output+=stdout.rstrip()
        if stderr.strip():
            output+= '\n--- stderr ---\n'
            output+= stderr.rstrip()
        
        if len(output) > 100*1024:
            output=output[:100*1024] + '\n... [output truncated]'
        
        return ToolResult(
            success=exit_code==0,
            output=output,
            error=stderr if exit_code!=0 else None,
            exit_code=exit_code,
        )
        
    def _build_environment(self)->dict[str, str]:
        env=os.environ.copy()
        
        shell_environment=self.config.shell_environment
        
        if not shell_environment.ignore_default_excludes:
            for pattern in shell_environment.exclude_patterns:
                keys_to_remove=[k for k in env.keys() if fnmatch.fnmatch(k.upper(), pattern.upper())]
                for k in keys_to_remove:
                    del env[k]
        
        if shell_environment.set_vars:
            env.update(shell_environment.set_vars)
            
        return env
        
        