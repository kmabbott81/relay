"""
MVP Chat Console Router

Provides a simple web-based chat interface for testing multi-AI functionality.
Mounted at /mvp on the beta API.
"""

import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# Initialize OpenAI and Anthropic clients
try:
    from openai import OpenAI

    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None
except Exception as e:
    openai_client = None
    logging.warning(f"OpenAI client not available: {e}")

try:
    import anthropic

    anthropic_client = (
        anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY")) if os.getenv("ANTHROPIC_API_KEY") else None
    )
except Exception as e:
    anthropic_client = None
    logging.warning(f"Anthropic client not available: {e}")

router = APIRouter()


# Pydantic models
class ChatRequest(BaseModel):
    message: str
    model: str = "gpt-3.5-turbo"
    user_id: str = "beta-tester"
    session_id: str = "default"


class ChatResponse(BaseModel):
    response: str
    model: str
    timestamp: str
    tokens_used: int = 0


@router.get("", response_class=HTMLResponse, include_in_schema=False)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_mvp_console():
    """
    Serve the MVP chat console HTML.

    This is a simple web interface for testing the beta API with GPT and Claude.
    """
    # Read the simple_ui.html file
    html_path = Path(__file__).parent.parent.parent.parent / "simple_ui.html"

    if not html_path.exists():
        return HTMLResponse(
            content=f"""
            <html>
                <head><title>MVP Console Not Found</title></head>
                <body>
                    <h1>MVP Console</h1>
                    <p>simple_ui.html not found. Expected at: {html_path}</p>
                </body>
            </html>
            """,
            status_code=404,
        )

    # Read and return the HTML
    html_content = html_path.read_text()

    # Replace localhost API_URL with window.location.origin + /mvp
    html_content = html_content.replace(
        "const API_URL = 'http://localhost:8000';", "const API_URL = window.location.origin + '/mvp';"
    )

    return HTMLResponse(content=html_content)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Single AI chat endpoint.

    Sends a message to either OpenAI or Anthropic based on the model specified.
    """
    # Determine which AI to use based on model
    if "claude" in request.model.lower():
        # Use Anthropic/Claude
        if not anthropic_client:
            raise HTTPException(status_code=500, detail="Anthropic API key not configured")

        try:
            response = anthropic_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1000,
                temperature=0.7,
                messages=[{"role": "user", "content": request.message}],
            )
            ai_response = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Claude API error: {str(e)}") from e
    else:
        # Use OpenAI
        if not openai_client:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")

        try:
            response = openai_client.chat.completions.create(
                model=request.model,
                messages=[
                    {"role": "system", "content": "You are Relay, a helpful AI assistant."},
                    {"role": "user", "content": request.message},
                ],
                max_tokens=1000,
                temperature=0.7,
            )
            ai_response = response.choices[0].message.content
            tokens_used = response.usage.total_tokens
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"OpenAI API error: {str(e)}") from e

    return ChatResponse(
        response=ai_response, model=request.model, timestamp=datetime.now().isoformat(), tokens_used=tokens_used
    )


@router.post("/multi-chat")
async def multi_chat(request: ChatRequest):
    """
    Multi-AI chat endpoint.

    Gets responses from both OpenAI and Anthropic simultaneously for comparison.
    """
    responses = {}

    # Try GPT-3.5
    if openai_client:
        try:
            gpt_response = await chat(
                ChatRequest(
                    message=request.message,
                    model="gpt-3.5-turbo",
                    user_id=request.user_id,
                    session_id=f"{request.session_id}-multi-gpt",
                )
            )
            responses["gpt-3.5-turbo"] = gpt_response.response
        except Exception as e:
            responses["gpt-3.5-turbo"] = f"Error: {str(e)}"
    else:
        responses["gpt-3.5-turbo"] = "OpenAI not configured"

    # Try Claude
    if anthropic_client:
        try:
            claude_response = await chat(
                ChatRequest(
                    message=request.message,
                    model="claude-3-haiku",
                    user_id=request.user_id,
                    session_id=f"{request.session_id}-multi-claude",
                )
            )
            responses["claude-3-haiku"] = claude_response.response
        except Exception as e:
            responses["claude-3-haiku"] = f"Error: {str(e)}"
    else:
        responses["claude-3-haiku"] = "Anthropic not configured"

    return {"timestamp": datetime.now().isoformat(), "responses": responses}
