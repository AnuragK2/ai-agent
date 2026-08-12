from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field
from urllib.parse import urlparse
import httpx

class WebFetchParams(BaseModel):
    url: str = Field(..., description="The URL to fetch content from (must be http:// or https://).")
    timeout: int = Field(
        30,
        ge=5,
        le=120,
        description="Request timeout in seconds (default: 120).",
    )
    
class WebFetchTool(Tool):
    name= "web_fetch"
    description= "Fetch content from a URL. Returns the response body as text."
    kind= ToolKind.NETWORK
    schema= WebFetchParams
    
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WebFetchParams(**invocation.params)
        
        parsed = urlparse(params.url)
        if not parsed.scheme or parsed.scheme not in ["http", "https"]:
            return ToolResult.error_result(f"Url must be http:// or https://: {params.url}")
        
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(params.timeout),
                follow_redirects=True,
            ) as client:
                response = await client.get(params.url)
                response.raise_for_status()
                text = response.text
        
        except httpx.HTTPStatusError as e:
            return ToolResult.error_result(f"HTTP error: {e.response.status_code} {e.response.reason_phrase}")
        except httpx.TimeoutException as e:
            return ToolResult.error_result(f"Request timed out after {params.timeout} seconds : {e}")
        except Exception as e:
            return ToolResult.error_result(f"Unexpected error: {e}")
        
        if len(text) > 100*1024:
            text= text[:100*1024] + "\n... [content truncated]"
        
        return ToolResult.success_result(
            text,
            metadata={
                "status_code": response.status_code,
                "content_length": len(response.content),
            },
        )
    
    
    
