from tools.base import Tool, ToolInvocation, ToolResult
from config.config import Config
from dataclasses import dataclass
from pydantic import BaseModel, Field
import asyncio
from typing import Any

class SubAgentParams(BaseModel):
    goal: str = Field(..., description="The specific task or goal for the subagent to achieve")
    
@dataclass
class SubAgentDefinition:
    name: str
    description: str
    goal_prompt: str
    allowed_tools: list[Tool] | None = None
    max_turns: int = 20
    timeout_seconds: float = 600

class SubagentTool(Tool):
    def __init__(self, config: Config, definition: SubAgentDefinition):
        super().__init__(config)
        self.definition = definition
        
    @property
    def name(self) -> str:
        return f"subagent_{self.definition.name}"
    
    @property
    def description(self) -> str:
        return self.definition.description
    
    
    schema= SubAgentParams
    
    def is_mutating(self, params: dict[str, Any]) -> bool:
        return True
    
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        
        from agent.agent import Agent
        from agent.events import AgentEventType
        
        params= SubAgentParams(**invocation.params)
        if not params.goal:
            return ToolResult.error_result("No goal specified for subagent")
        
        config_dict= self.config.to_dict()   
        config_dict['max_turns']= self.definition.max_turns
        if self.definition.allowed_tools:
            config_dict['allowed_tools']= self.definition.allowed_tools
        
        subagent_config= Config(**config_dict)
        
        prompt=f"""You are a specialized sub-agent with a specific task to complete.
        
        {self.definition.goal_prompt}
        
        YOUR TASK:
        {params.goal}
        
        IMPORTANT:
        -Focus only on completing the specified task
        -Do not engage in unrelated actions
        -Once you have completed the task or have the answer, provide your final response
        -Be concise and direct in your output
        """
        
        tool_calls=[]
        final_response=None
        error=None
        terminate_response='goal'
        
        try:
            async with Agent(subagent_config) as agent:
                deadline=asyncio.get_event_loop().time() + self.definition.timeout_seconds
                async for event in agent.run(prompt):
                    if asyncio.get_event_loop().time() > deadline:
                        terminate_response= 'timeout'
                        final_response= f'Subagent execution timed out after {self.definition.timeout_seconds} seconds'
                        break
                    if event.type == AgentEventType.TOOL_CALL_START:
                        tool_calls.append(event.data.get('name'))
                    elif event.type == AgentEventType.TEXT_COMPLETE:
                        final_response= event.data.get('content')
                    elif event.type == AgentEventType.AGENT_ERROR:
                        terminate_response= 'error'
                        error= event.data.get('error')
                        final_response= f'Subagent execution failed: {error}'
                        break
                    
        except Exception as e:
            terminate_response= 'error'
            error= str(e)
            final_response= f'Subagent execution failed: {error}'
          
        
        result = f"""Subagent {self.definition.name} completed
        Termination reason: {terminate_response}
        Tool calls: {', '.join(tool_calls) if tool_calls else 'No tool calls'}
        Result: {final_response or 'No response'}
        """
        
        if error:
            return ToolResult.error_result(result)
        
        return ToolResult.success_result(result)


CODEBASE_INVESTIGATOR=SubAgentDefinition(
    name='codebase_investigator',
    description='Investigate the codebase to answer questions about the code structure, patterns, dependencies, implementations, and other relevant information.',
    goal_prompt="""You are a codebase investigation specialist. 
    Your job is to explore and understand the code to answer questions about the code structure, patterns, dependencies, implementations, and other relevant information.
    Use read_file, grep, glob and list_dir to investigate the codebase.
    Do not modify any files or directories.""",
    allowed_tools=["read_file", "grep", "glob", "list_dir"],
)    

CODE_REVIEWER=SubAgentDefinition(
    name='code_reviewer',
    description='Reviews the code changes and provides feedback on quality, bugs, and improvements.',
    goal_prompt="""You are a code review specialist. 
    Your job is to review the code changes and provide constructive feedback.
    Look for bugs, performance issues, code smells, security vulnerabilities, and other code quality issues.
    Provide a detailed report of the issues found and suggestions for improvements.
    Use read_file, grep, list_dir and glob to review the code changes.
    Do not modify any files or directories.""",
    allowed_tools=["read_file", "grep", "list_dir", "glob"],
    max_turns=10,
    timeout_seconds=300
)    

def get_default_subagents_definitions() -> list[SubAgentDefinition]:
    return [CODEBASE_INVESTIGATOR, CODE_REVIEWER]