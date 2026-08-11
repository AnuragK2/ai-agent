from tools.base import Tool, ToolKind, ToolResult, ToolInvocation
from pydantic import BaseModel, Field
from ddgs import DDGS

class WebSearchParams(BaseModel):
    query: str = Field(..., description='The search query to perform')
    max_results: int = Field(10, ge=1, le=100, description='The maximum number of search results to return (default: 10)')

class WebSearchTool(Tool):
    name = 'web_search'
    description = 'Search the web for information. Returns search results with titles, URLs, and snippets.'
    kind = ToolKind.NETWORK
    schema = WebSearchParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WebSearchParams(**invocation.params)
        
        try:
            results = DDGS().text(
                params.query,
                region='us-en',
                safesearch='off',
                timelimit='y',
                max_results=params.max_results,
                backend='auto',
            )
        except Exception as e:
            return ToolResult.error_result(f"Error searching the web: {e}")
        
        if not results:
            return ToolResult.success_result(f"No search results found for query: {params.query}", metadata={
                "results": 0
            })
        
        output_lines = [f'Search Results for: {params.query}']
        for i, result in enumerate(results, start=1):
            title = result.get('title') or '(no title)'
            url = result.get('href') or result.get('url') or ''
            snippet = result.get('body') or result.get('description') or ''
            output_lines.append(f'{i}. Title: {title}')
            if url:
                output_lines.append(f'  URL: {url}')
            if snippet:
                output_lines.append(f'  Snippet: {snippet}')
            output_lines.append('')
        
        return ToolResult.success_result("\n".join(output_lines), metadata={
            "results": len(results)
        })