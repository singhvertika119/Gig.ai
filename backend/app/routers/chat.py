import sys
import os
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from app.config import settings

router = APIRouter(prefix="/api/chat", tags=["chat"])

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    answer: str
    generated_sql: str | None = None

@router.post("", response_model=ChatResponse)
async def chat_query(request: ChatRequest):
    """
    Connects to the MCP server via stdio, calls the 'ask_database_nl' tool,
    and returns a natural language summary answer along with the generated SQL.
    """
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Query message cannot be empty.")

    # Build execution environment inheriting current environment variables
    env = os.environ.copy()
    if settings.groq_api_key:
        env["GROQ_API_KEY"] = settings.groq_api_key

    # Specify standard stdio server parameters to spawn the MCP server
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"],
        env=env
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize the MCP session
                await session.initialize()
                
                # Invoke the natural language tool on the MCP server
                response = await session.call_tool(
                    "ask_database_nl", 
                    arguments={"question": request.message}
                )
                
                if not response.content:
                    raise HTTPException(
                        status_code=500, 
                        detail="No content received from the MCP server tool."
                    )
                
                # Parse output
                result_text = ""
                for block in response.content:
                    if block.type == "text":
                        result_text += block.text
                
                try:
                    data = json.loads(result_text)
                    return ChatResponse(
                        answer=data.get("answer", "No answer compiled."),
                        generated_sql=data.get("generated_sql")
                    )
                except json.JSONDecodeError:
                    # Fallback if the tool returned a raw string rather than structured JSON
                    return ChatResponse(
                        answer=result_text,
                        generated_sql=None
                    )
                    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to communicate with MCP server: {str(e)}"
        )
