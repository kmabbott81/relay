"""
MVP Chat Console Router

Provides a simple web-based chat interface for testing multi-AI functionality.
Mounted at /mvp on the beta API.
"""

import logging
import os
from datetime import datetime

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
    # Embedded HTML to avoid file path issues in Docker
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Relay MVP - Beta Testing</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }
            .header h1 { font-size: 28px; margin-bottom: 10px; }
            .header p { font-size: 14px; opacity: 0.9; }
            .content { padding: 30px; }
            .form-group { margin-bottom: 20px; }
            label { display: block; margin-bottom: 8px; font-weight: 600; color: #333; }
            textarea, select {
                width: 100%;
                padding: 12px;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                font-size: 14px;
                font-family: inherit;
            }
            textarea { resize: vertical; min-height: 100px; }
            .btn {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 12px 30px;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s;
            }
            .btn:hover { transform: translateY(-2px); }
            .btn:disabled { opacity: 0.6; cursor: not-allowed; }
            .response {
                margin-top: 20px;
                padding: 20px;
                background: #f8f9fa;
                border-radius: 8px;
                border-left: 4px solid #667eea;
            }
            .response h3 { margin-bottom: 10px; color: #667eea; }
            .response pre {
                background: white;
                padding: 15px;
                border-radius: 6px;
                white-space: pre-wrap;
                word-wrap: break-word;
            }
            .error { border-left-color: #dc3545; }
            .error h3 { color: #dc3545; }
            .loading { text-align: center; padding: 20px; color: #667eea; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 Relay MVP - Beta Testing</h1>
                <p>Test your beta API with GPT and Claude</p>
            </div>
            <div class="content">
                <div class="form-group">
                    <label for="message">Message</label>
                    <textarea id="message" placeholder="Enter your message here...">Hello! Can you help me test this API?</textarea>
                </div>
                <div class="form-group">
                    <label for="model">AI Model</label>
                    <select id="model">
                        <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
                        <option value="gpt-4">GPT-4</option>
                        <option value="claude-3-haiku">Claude 3 Haiku</option>
                        <option value="multi">Compare Both (Multi-AI)</option>
                    </select>
                </div>
                <button class="btn" onclick="sendMessage()">Send Message</button>
                <div id="response"></div>
            </div>
        </div>
        <script>
            const API_URL = window.location.origin + '/mvp';

            async function sendMessage() {
                const message = document.getElementById('message').value;
                const model = document.getElementById('model').value;
                const responseDiv = document.getElementById('response');

                if (!message.trim()) {
                    alert('Please enter a message');
                    return;
                }

                responseDiv.innerHTML = '<div class="loading">⏳ Sending request...</div>';

                try {
                    const endpoint = model === 'multi' ? `${API_URL}/multi-chat` : `${API_URL}/chat`;
                    const response = await fetch(endpoint, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            message: message,
                            model: model === 'multi' ? 'gpt-3.5-turbo' : model,
                            user_id: 'beta-tester',
                            session_id: 'test-session'
                        })
                    });

                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }

                    const data = await response.json();

                    let html = '<div class="response">';

                    if (model === 'multi' && data.responses) {
                        html += '<h3>📊 Multi-AI Responses</h3>';
                        for (const [modelName, modelResponse] of Object.entries(data.responses)) {
                            html += `<h4>${modelName}</h4><pre>${escapeHtml(modelResponse)}</pre>`;
                        }
                    } else {
                        html += `<h3>✅ ${data.model}</h3>`;
                        html += `<pre>${escapeHtml(data.response)}</pre>`;
                        if (data.tokens_used) {
                            html += `<p style="margin-top: 10px; color: #666; font-size: 12px;">Tokens used: ${data.tokens_used}</p>`;
                        }
                    }

                    html += '</div>';
                    responseDiv.innerHTML = html;

                } catch (error) {
                    responseDiv.innerHTML = `<div class="response error"><h3>❌ Error</h3><pre>${escapeHtml(error.message)}</pre></div>`;
                }
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            // Allow Enter to send (Shift+Enter for new line)
            document.getElementById('message').addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
        </script>
    </body>
    </html>
    """

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
