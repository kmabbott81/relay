"""
MVP Chat Console Router

Provides a simple web-based chat interface for testing multi-AI functionality.
Mounted at /mvp on the beta API.
"""

import logging
import os
import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from models_config import validate_and_resolve
from relay_ai.platform.api import mvp_db


# Redact sensitive data from logs
class SensitiveDataFilter(logging.Filter):
    """Filter out API keys and sensitive tokens from logs."""

    REDACT_PATTERNS = [
        r"(sk-[a-zA-Z0-9]{48})",  # OpenAI keys
        r"(sk-ant-[a-zA-Z0-9-]{95})",  # Anthropic keys
        r"(Bearer [a-zA-Z0-9._-]+)",  # JWT tokens
    ]

    def filter(self, record):
        for pattern in self.REDACT_PATTERNS:
            record.msg = re.sub(pattern, "[REDACTED]", str(record.msg))
        return True


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

# Initialize logger with SensitiveDataFilter applied
logger = logging.getLogger(__name__)
for handler in logger.handlers:
    handler.addFilter(SensitiveDataFilter())
# Also ensure the root logger filters sensitive data for all descendant loggers
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    handler.addFilter(SensitiveDataFilter())


# Pydantic models
class ChatRequest(BaseModel):
    message: str
    model: str = "gpt-3.5-turbo"
    user_id: Optional[UUID] = None
    thread_id: Optional[UUID] = None
    session_id: str = "default"  # kept for backward compatibility


class ChatResponse(BaseModel):
    response: str
    model: str
    timestamp: str
    tokens_used: int = 0
    thread_id: Optional[UUID] = None


@router.get("", response_class=HTMLResponse, include_in_schema=False)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_mvp_console():
    """
    Serve the MVP chat console with full conversation history, thread management, and file uploads.

    Features:
    - Conversation threads on left sidebar
    - Thread-based chat history
    - File upload with persistent storage
    - Multi-AI comparison
    - Model selection
    """
    # Embedded HTML - conversation history UI with file uploads
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Relay MVP - Chat & Files</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                background: #f5f5f5;
                height: 100vh;
                overflow: hidden;
            }
            .app { display: flex; height: 100vh; }
            .sidebar {
                width: 280px;
                background: white;
                border-right: 1px solid #e0e0e0;
                display: flex;
                flex-direction: column;
                overflow-y: auto;
            }
            .sidebar-header {
                padding: 15px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                font-weight: 600;
                font-size: 14px;
            }
            .new-thread-btn {
                margin: 10px;
                padding: 10px 15px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-weight: 600;
                font-size: 13px;
            }
            .new-thread-btn:hover { opacity: 0.9; }
            .threads-list {
                flex: 1;
                overflow-y: auto;
                padding: 10px;
            }
            .thread-item {
                padding: 12px;
                margin-bottom: 8px;
                background: #f8f9fa;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                cursor: pointer;
                font-size: 13px;
                line-height: 1.4;
                transition: all 0.2s;
            }
            .thread-item:hover { background: #f0f0f0; border-color: #667eea; }
            .thread-item.active {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border-color: #667eea;
            }
            .thread-title { font-weight: 500; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .thread-date { font-size: 11px; opacity: 0.7; }
            .chat-area {
                flex: 1;
                display: flex;
                flex-direction: column;
                background: white;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                text-align: center;
                border-bottom: 1px solid #e0e0e0;
            }
            .header h1 { font-size: 20px; margin-bottom: 5px; }
            .header p { font-size: 12px; opacity: 0.9; }
            .messages-container {
                flex: 1;
                overflow-y: auto;
                padding: 20px;
                background: #f8f9fa;
            }
            .message {
                margin-bottom: 16px;
                display: flex;
                animation: fadeIn 0.3s;
            }
            @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
            .message.user { justify-content: flex-end; }
            .message-bubble {
                max-width: 70%;
                padding: 12px 16px;
                border-radius: 12px;
                word-wrap: break-word;
            }
            .message.user .message-bubble {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border-bottom-right-radius: 4px;
            }
            .message.ai .message-bubble {
                background: white;
                border: 1px solid #e0e0e0;
                border-bottom-left-radius: 4px;
            }
            .loading-text { text-align: center; padding: 20px; color: #999; }
            .input-area {
                padding: 20px;
                background: white;
                border-top: 1px solid #e0e0e0;
            }
            .form-group { margin-bottom: 12px; }
            label { display: block; margin-bottom: 6px; font-weight: 600; color: #333; font-size: 13px; }
            textarea, select {
                width: 100%;
                padding: 10px;
                border: 2px solid #e0e0e0;
                border-radius: 6px;
                font-size: 13px;
                font-family: inherit;
            }
            textarea { resize: vertical; min-height: 60px; }
            textarea:focus, select:focus { outline: none; border-color: #667eea; }
            .input-controls {
                display: flex;
                gap: 10px;
                margin-top: 10px;
            }
            .btn {
                flex: 1;
                padding: 10px 16px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s;
            }
            .btn:hover:not(:disabled) { transform: translateY(-1px); }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .btn-secondary { background: #6c757d; flex: 0.5; }
            .file-input-label {
                display: flex;
                align-items: center;
                gap: 6px;
                padding: 8px 12px;
                background: #f0f0f0;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                cursor: pointer;
                font-size: 12px;
                font-weight: 600;
            }
            .file-input-label:hover { background: #e8e8e8; }
            #fileInput { display: none; }
            .error { color: #dc3545; font-size: 12px; margin-top: 5px; }
        </style>
    </head>
    <body>
        <div class="app">
            <!-- Left Sidebar: Thread List -->
            <div class="sidebar">
                <div class="sidebar-header">💬 Conversations</div>
                <button class="new-thread-btn" onclick="createNewThread()">+ New Thread</button>
                <div class="threads-list" id="threadsList">
                    <div class="loading-text">Loading conversations...</div>
                </div>
            </div>

            <!-- Right: Chat Area -->
            <div class="chat-area">
                <div class="header">
                    <h1>🚀 Relay MVP</h1>
                    <p id="currentThreadTitle">No conversation selected</p>
                </div>

                <div class="messages-container" id="messagesContainer">
                    <div class="loading-text">Select or create a conversation to start chatting</div>
                </div>

                <div class="input-area">
                    <div class="form-group">
                        <label for="model">AI Model</label>
                        <select id="model">
                            <option value="gpt-fast">GPT-4o Mini (Fast)</option>
                            <option value="gpt-strong">GPT-4o (Strong)</option>
                            <option value="claude-fast">Claude Haiku 4.5 (Fast)</option>
                            <option value="claude-strong">Claude Sonnet 4.5 (Strong)</option>
                            <option value="multi">Compare Both (Multi-AI)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="message">Message</label>
                        <textarea id="message" placeholder="Type your message..." disabled></textarea>
                    </div>
                    <div class="input-controls">
                        <label class="file-input-label">
                            📎 Attach File
                            <input type="file" id="fileInput" onchange="handleFileSelect(event)">
                        </label>
                        <button class="btn" onclick="sendMessage()" id="sendBtn" disabled>Send Message</button>
                    </div>
                    <div id="errorMsg" class="error"></div>
                </div>
            </div>
        </div>

        <script>
            const API_URL = window.location.origin + '/mvp';
            let currentThreadId = null;
            let threads = [];

            async function loadThreads() {
                try {
                    const res = await fetch(`${API_URL}/threads`);
                    const data = await res.json();
                    threads = data.threads || [];
                    renderThreads();
                } catch (e) {
                    console.error('Error loading threads:', e);
                }
            }

            function renderThreads() {
                const list = document.getElementById('threadsList');
                if (threads.length === 0) {
                    list.innerHTML = '<div class="loading-text">No conversations yet</div>';
                    return;
                }
                list.innerHTML = threads.map(t => `
                    <div class="thread-item ${t.id === currentThreadId ? 'active' : ''}" onclick="selectThread('${t.id}', '${escapeHtml(t.title)}')">
                        <div class="thread-title">${escapeHtml(t.title)}</div>
                        <div class="thread-date">${formatDate(t.updated_at)}</div>
                    </div>
                `).join('');
            }

            async function createNewThread() {
                try {
                    const res = await fetch(`${API_URL}/threads`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title: 'New Conversation' })
                    });
                    const data = await res.json();
                    await loadThreads();
                    selectThread(data.id, 'New Conversation');
                } catch (e) {
                    showError('Failed to create thread');
                }
            }

            async function selectThread(threadId, title) {
                currentThreadId = threadId;
                document.getElementById('currentThreadTitle').textContent = title;
                document.getElementById('message').disabled = false;
                document.getElementById('sendBtn').disabled = false;
                renderThreads();
                await loadMessages();
            }

            async function loadMessages() {
                if (!currentThreadId) return;
                try {
                    const res = await fetch(`${API_URL}/threads/${currentThreadId}/messages`);
                    const data = await res.json();
                    const container = document.getElementById('messagesContainer');
                    if (!data.messages || data.messages.length === 0) {
                        container.innerHTML = '<div class="loading-text">No messages in this conversation yet</div>';
                        return;
                    }
                    container.innerHTML = data.messages.map(m => `
                        <div class="message ${m.role}">
                            <div class="message-bubble">${escapeHtml(m.content)}</div>
                        </div>
                    `).join('');
                    container.scrollTop = container.scrollHeight;
                } catch (e) {
                    console.error('Error loading messages:', e);
                }
            }

            async function sendMessage() {
                const msg = document.getElementById('message').value.trim();
                const model = document.getElementById('model').value;
                if (!msg || !currentThreadId) return;

                const container = document.getElementById('messagesContainer');
                if (container.textContent.includes('No messages')) {
                    container.innerHTML = '';
                }

                // Add user message
                const userMsg = document.createElement('div');
                userMsg.className = 'message user';
                userMsg.innerHTML = `<div class="message-bubble">${escapeHtml(msg)}</div>`;
                container.appendChild(userMsg);

                document.getElementById('message').value = '';
                document.getElementById('sendBtn').disabled = true;
                container.scrollTop = container.scrollHeight;

                try {
                    const endpoint = model === 'multi' ? `${API_URL}/multi-chat` : `${API_URL}/chat`;
                    const res = await fetch(endpoint, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            message: msg,
                            model: model === 'multi' ? 'gpt-3.5-turbo' : model,
                            thread_id: currentThreadId
                        })
                    });
                    const data = await res.json();

                    // Add AI response
                    const aiMsg = document.createElement('div');
                    aiMsg.className = 'message ai';
                    if (model === 'multi' && data.responses) {
                        aiMsg.innerHTML = `<div class="message-bubble">${Object.entries(data.responses).map(([k,v]) => `<strong>${k}:</strong> ${escapeHtml(v)}`).join('<br><br>')}</div>`;
                    } else {
                        aiMsg.innerHTML = `<div class="message-bubble">${escapeHtml(data.response || data.responses?.['gpt-3.5-turbo'] || 'No response')}</div>`;
                    }
                    container.appendChild(aiMsg);
                    container.scrollTop = container.scrollHeight;
                    await loadThreads();
                } catch (e) {
                    showError('Failed to send message');
                } finally {
                    document.getElementById('sendBtn').disabled = false;
                }
            }

            async function handleFileSelect(e) {
                const file = e.target.files[0];
                if (!file) return;

                if (!currentThreadId) {
                    showError('Create a thread first before uploading files');
                    document.getElementById('fileInput').value = '';
                    return;
                }

                // Create FormData for multipart upload
                const formData = new FormData();
                formData.append('file', file);
                formData.append('thread_id', currentThreadId);

                try {
                    document.getElementById('sendBtn').disabled = true;
                    const res = await fetch(`${API_URL}/files?thread_id=${currentThreadId}`, {
                        method: 'POST',
                        body: formData
                    });

                    if (!res.ok) {
                        const error = await res.json();
                        showError(`Upload failed: ${error.detail || 'Unknown error'}`);
                    } else {
                        const data = await res.json();
                        const msg = `📎 File uploaded: ${data.filename} (${(data.file_size / 1024).toFixed(1)}KB)`;
                        showError(msg); // Reuse for success message

                        // Refresh file list
                        await loadThreadFiles();
                    }
                } catch (e) {
                    showError('Failed to upload file');
                } finally {
                    document.getElementById('fileInput').value = '';
                    document.getElementById('sendBtn').disabled = false;
                }
            }

            async function loadThreadFiles() {
                if (!currentThreadId) return;
                try {
                    const res = await fetch(`${API_URL}/threads/${currentThreadId}/files`);
                    const data = await res.json();
                    const fileList = document.getElementById('fileList');
                    fileList.innerHTML = '';

                    if (data.files && data.files.length > 0) {
                        const title = document.createElement('div');
                        title.style.fontSize = '11px';
                        title.style.color = '#666';
                        title.style.marginTop = '10px';
                        title.textContent = `${data.files.length} file(s):`;
                        fileList.appendChild(title);

                        data.files.forEach(f => {
                            const item = document.createElement('div');
                            item.style.fontSize = '11px';
                            item.style.padding = '5px';
                            item.style.background = '#f0f0f0';
                            item.style.borderRadius = '3px';
                            item.style.marginBottom = '5px';
                            item.style.display = 'flex';
                            item.style.justifyContent = 'space-between';
                            item.style.alignItems = 'center';

                            const info = document.createElement('span');
                            info.textContent = `📎 ${f.filename} (${(f.file_size / 1024).toFixed(1)}KB)`;

                            const delBtn = document.createElement('button');
                            delBtn.textContent = '×';
                            delBtn.style.border = 'none';
                            delBtn.style.background = 'none';
                            delBtn.style.cursor = 'pointer';
                            delBtn.style.fontSize = '16px';
                            delBtn.onclick = async () => {
                                try {
                                    const res = await fetch(`${API_URL}/files/${f.id}`, { method: 'DELETE' });
                                    if (res.ok) {
                                        await loadThreadFiles();
                                    }
                                } catch (e) {
                                    showError('Failed to delete file');
                                }
                            };

                            item.appendChild(info);
                            item.appendChild(delBtn);
                            fileList.appendChild(item);
                        });
                    }
                } catch (e) {
                    // Silently fail - files might not be available yet
                }
            }

            function formatDate(dateStr) {
                const d = new Date(dateStr);
                const now = new Date();
                const diff = (now - d) / 1000;
                if (diff < 60) return 'now';
                if (diff < 3600) return Math.floor(diff/60) + 'm ago';
                if (diff < 86400) return Math.floor(diff/3600) + 'h ago';
                return d.toLocaleDateString();
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            function showError(msg) {
                const err = document.getElementById('errorMsg');
                err.textContent = msg;
                setTimeout(() => err.textContent = '', 5000);
            }

            // Allow Enter to send (Shift+Enter for new line)
            document.getElementById('message').addEventListener('keydown', e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });

            // Load threads on start
            loadThreads();
            setInterval(loadThreads, 5000); // Auto-refresh every 5 seconds
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
    Persists conversation to database if DATABASE_URL is configured.
    """
    # Check if database is available
    db_available = os.getenv("DATABASE_URL") is not None

    # Get user_id (default to Kyle if not provided)
    user_id = request.user_id
    if not user_id and db_available:
        try:
            user_id = await mvp_db.get_default_user_id()
        except Exception as e:
            logging.warning(f"Failed to get default user_id: {e}")
            db_available = False

    # Resolve model key to provider and actual model ID (Phase 2C integration)
    resolved_model_id = None
    try:
        _, resolved_model_id, config = validate_and_resolve(request.model)
    except ValueError as e:
        logging.warning(f"Model validation failed: {e}, using request.model as-is")
        # Fallback: use request.model as-is
        resolved_model_id = request.model

    # Handle thread_id: create new thread if not provided
    thread_id = request.thread_id
    if db_available and user_id and not thread_id:
        try:
            # Create thread title from first ~80 chars of message
            title = request.message[:80] + "..." if len(request.message) > 80 else request.message
            thread_id = await mvp_db.create_thread(user_id, title)
        except Exception as e:
            logging.warning(f"Failed to create thread: {e}")
            db_available = False

    # Insert user message to database (Phase 2C: include model_key and model_id)
    if db_available and user_id and thread_id:
        try:
            await mvp_db.create_message(
                thread_id=thread_id,
                user_id=user_id,
                role="user",
                content=request.message,
                model_key=request.model,  # Logical key from request
                model_id=resolved_model_id,  # Resolved provider model ID
            )
        except Exception as e:
            logging.warning(f"Failed to insert user message: {e}")

    # Determine which AI to use based on model
    if "claude" in request.model.lower():
        # Use Anthropic/Claude
        if not anthropic_client:
            raise HTTPException(status_code=500, detail="Anthropic API key not configured")

        try:
            response = anthropic_client.messages.create(
                model=resolved_model_id,
                max_tokens=1000,
                temperature=0.7,
                messages=[{"role": "user", "content": request.message}],
            )
            ai_response = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens
            token_usage_json = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": tokens_used,
            }
        except Exception as e:
            logger.error("Anthropic API call failed", exc_info=True, extra={"model": resolved_model_id})
            raise HTTPException(status_code=500, detail="AI service temporarily unavailable") from e
    else:
        # Use OpenAI
        if not openai_client:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")

        try:
            response = openai_client.chat.completions.create(
                model=resolved_model_id,
                messages=[
                    {"role": "system", "content": "You are Relay, a helpful AI assistant."},
                    {"role": "user", "content": request.message},
                ],
                max_tokens=1000,
                temperature=0.7,
            )
            ai_response = response.choices[0].message.content
            tokens_used = response.usage.total_tokens
            token_usage_json = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": tokens_used,
            }
        except Exception as e:
            logger.error("OpenAI API call failed", exc_info=True, extra={"model": resolved_model_id})
            raise HTTPException(status_code=500, detail="AI service temporarily unavailable") from e

    # Insert assistant message to database (Phase 2C: include model_key and model_id)
    if db_available and user_id and thread_id:
        try:
            await mvp_db.create_message(
                thread_id=thread_id,
                user_id=user_id,
                role="assistant",
                content=ai_response,
                model_name=request.model,
                model_key=request.model,  # Logical key from request
                model_id=resolved_model_id,  # Resolved provider model ID
                token_usage_json=token_usage_json,
            )
        except Exception as e:
            logging.warning(f"Failed to insert assistant message: {e}")

    return ChatResponse(
        response=ai_response,
        model=request.model,
        timestamp=datetime.now().isoformat(),
        tokens_used=tokens_used,
        thread_id=thread_id,
    )


@router.post("/multi-chat")
async def multi_chat(request: ChatRequest):
    """
    Multi-AI chat endpoint.

    Gets responses from both OpenAI and Anthropic simultaneously for comparison.
    Persists both responses to database if DATABASE_URL is configured.
    """
    # Check if database is available
    db_available = os.getenv("DATABASE_URL") is not None

    # Get user_id (default to Kyle if not provided)
    user_id = request.user_id
    if not user_id and db_available:
        try:
            user_id = await mvp_db.get_default_user_id()
        except Exception as e:
            logging.warning(f"Failed to get default user_id: {e}")
            db_available = False

    # Handle thread_id: create new thread if not provided
    thread_id = request.thread_id
    if db_available and user_id and not thread_id:
        try:
            # Create thread title from first ~80 chars of message
            title = "[Multi-AI] " + (request.message[:70] + "..." if len(request.message) > 70 else request.message)
            thread_id = await mvp_db.create_thread(user_id, title)
        except Exception as e:
            logging.warning(f"Failed to create thread: {e}")
            db_available = False

    # Insert user message to database (only once for multi-chat)
    if db_available and user_id and thread_id:
        try:
            await mvp_db.create_message(
                thread_id=thread_id,
                user_id=user_id,
                role="user",
                content=request.message,
            )
        except Exception as e:
            logging.warning(f"Failed to insert user message: {e}")

    responses = {}

    # Try GPT-3.5
    if openai_client:
        try:
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are Relay, a helpful AI assistant."},
                    {"role": "user", "content": request.message},
                ],
                max_tokens=1000,
                temperature=0.7,
            )
            ai_response = response.choices[0].message.content
            tokens_used = response.usage.total_tokens
            responses["gpt-3.5-turbo"] = ai_response

            # Insert GPT assistant message to database
            if db_available and user_id and thread_id:
                try:
                    await mvp_db.create_message(
                        thread_id=thread_id,
                        user_id=user_id,
                        role="assistant",
                        content=ai_response,
                        model_name="gpt-3.5-turbo",
                        token_usage_json={
                            "prompt_tokens": response.usage.prompt_tokens,
                            "completion_tokens": response.usage.completion_tokens,
                            "total_tokens": tokens_used,
                        },
                    )
                except Exception as e:
                    logging.warning(f"Failed to insert GPT assistant message: {e}")
        except Exception:
            logger.error("Multi-chat OpenAI API call failed", exc_info=True)
            responses["gpt-3.5-turbo"] = "Error: AI service temporarily unavailable"
    else:
        responses["gpt-3.5-turbo"] = "OpenAI not configured"

    # Try Claude
    if anthropic_client:
        try:
            response = anthropic_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1000,
                temperature=0.7,
                messages=[{"role": "user", "content": request.message}],
            )
            ai_response = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens
            responses["claude-3-haiku"] = ai_response

            # Insert Claude assistant message to database
            if db_available and user_id and thread_id:
                try:
                    await mvp_db.create_message(
                        thread_id=thread_id,
                        user_id=user_id,
                        role="assistant",
                        content=ai_response,
                        model_name="claude-3-haiku",
                        token_usage_json={
                            "input_tokens": response.usage.input_tokens,
                            "output_tokens": response.usage.output_tokens,
                            "total_tokens": tokens_used,
                        },
                    )
                except Exception as e:
                    logging.warning(f"Failed to insert Claude assistant message: {e}")
        except Exception:
            logger.error("Multi-chat Anthropic API call failed", exc_info=True)
            responses["claude-3-haiku"] = "Error: AI service temporarily unavailable"
    else:
        responses["claude-3-haiku"] = "Anthropic not configured"

    return {"timestamp": datetime.now().isoformat(), "responses": responses, "thread_id": thread_id}


@router.get("/threads")
async def list_user_threads(user_id: Optional[UUID] = None):
    """
    List conversation threads for a user.

    Returns threads ordered by most recent activity first.
    """
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(status_code=503, detail="Database not configured")

    # Get user_id (default to Kyle if not provided)
    if not user_id:
        try:
            user_id = await mvp_db.get_default_user_id()
        except Exception as e:
            logger.error("Failed to get default user", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to retrieve user information") from e

    try:
        threads = await mvp_db.list_threads(user_id)
        # Convert datetime objects to ISO format strings
        for thread in threads:
            thread["created_at"] = thread["created_at"].isoformat()
            thread["updated_at"] = thread["updated_at"].isoformat()
            thread["id"] = str(thread["id"])
            thread["user_id"] = str(thread["user_id"])
        return {"threads": threads}
    except Exception as e:
        logger.error("Failed to list threads", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve threads") from e


@router.get("/threads/{thread_id}/messages")
async def list_thread_messages(thread_id: UUID, user_id: Optional[UUID] = None):
    """
    List messages in a conversation thread.

    Returns messages in chronological order.
    Verifies thread ownership before returning messages.
    """
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(status_code=503, detail="Database not configured")

    # Get user_id (default to Kyle if not provided)
    if not user_id:
        try:
            user_id = await mvp_db.get_default_user_id()
        except Exception as e:
            logger.error("Failed to get default user", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to retrieve user information") from e

    try:
        # Verify thread exists
        thread = await mvp_db.get_thread(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        # Verify ownership
        is_owner = await mvp_db.verify_thread_ownership(thread_id, user_id)
        if not is_owner:
            raise HTTPException(status_code=403, detail="You do not have access to this thread")

        # Get messages
        messages = await mvp_db.list_messages(thread_id)
        # Convert datetime and UUID objects to strings
        for message in messages:
            message["created_at"] = message["created_at"].isoformat()
            message["id"] = str(message["id"])
            message["thread_id"] = str(message["thread_id"])
            message["user_id"] = str(message["user_id"])

        return {"messages": messages}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list messages", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve messages") from e


# File Management Endpoints


@router.post("/files")
async def upload_file(thread_id: UUID, file: UploadFile = File(...), user_id: Optional[UUID] = None):
    """
    Upload a file to a thread.

    Accepts any file type, stores it with database metadata.
    Option B: Full database integration with persistent storage.
    """
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(status_code=503, detail="Database not configured")

    # Get user_id (default to Kyle if not provided)
    if not user_id:
        try:
            user_id = await mvp_db.get_default_user_id()
        except Exception as e:
            logger.error("Failed to get default user", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to retrieve user information") from e

    try:
        # Verify thread exists
        thread = await mvp_db.get_thread(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        # Verify ownership
        is_owner = await mvp_db.verify_thread_ownership(thread_id, user_id)
        if not is_owner:
            raise HTTPException(status_code=403, detail="You do not have access to this thread")

        # Read file content
        content = await file.read()
        file_size = len(content)

        # Validate file size (50MB max)
        max_size = 50 * 1024 * 1024
        if file_size > max_size:
            raise HTTPException(status_code=413, detail=f"File too large. Max {max_size / 1024 / 1024}MB")

        # Create temp storage path (in production, this would be S3/cloud storage)
        # For now, use a deterministic path based on UUID
        file_id = UUID(str(__import__("uuid").uuid4()))
        storage_dir = "/tmp/relay_files"
        os.makedirs(storage_dir, exist_ok=True)
        storage_path = os.path.join(storage_dir, f"{file_id}_{file.filename}")

        # Write file to storage
        with open(storage_path, "wb") as f:
            f.write(content)

        # Create file record in database
        file_record_id = await mvp_db.create_file(
            user_id=user_id,
            thread_id=thread_id,
            filename=file.filename,
            file_size=file_size,
            mime_type=file.content_type or "application/octet-stream",
            storage_path=storage_path,
        )

        logger.info(f"File uploaded: {file.filename} ({file_size} bytes) to thread {thread_id}")

        return {
            "file_id": str(file_record_id),
            "filename": file.filename,
            "file_size": file_size,
            "mime_type": file.content_type,
            "created_at": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("File upload failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to upload file") from e


@router.get("/threads/{thread_id}/files")
async def list_thread_files(thread_id: UUID, user_id: Optional[UUID] = None):
    """
    List all files in a thread.

    Returns file metadata (filename, size, uploaded date).
    """
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(status_code=503, detail="Database not configured")

    # Get user_id (default to Kyle if not provided)
    if not user_id:
        try:
            user_id = await mvp_db.get_default_user_id()
        except Exception as e:
            logger.error("Failed to get default user", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to retrieve user information") from e

    try:
        # Verify thread exists and ownership
        thread = await mvp_db.get_thread(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        is_owner = await mvp_db.verify_thread_ownership(thread_id, user_id)
        if not is_owner:
            raise HTTPException(status_code=403, detail="You do not have access to this thread")

        # Get files
        files = await mvp_db.list_thread_files(thread_id)

        # Convert datetime and UUID objects to strings
        for file_record in files:
            file_record["created_at"] = file_record["created_at"].isoformat()
            file_record["id"] = str(file_record["id"])
            file_record["thread_id"] = str(file_record["thread_id"])
            file_record["user_id"] = str(file_record["user_id"])

        return {"files": files}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list thread files", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve files") from e


@router.delete("/files/{file_id}")
async def delete_file(file_id: UUID, user_id: Optional[UUID] = None):
    """
    Delete a file from a thread.

    Removes file metadata from database and storage.
    Only file owner can delete.
    """
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(status_code=503, detail="Database not configured")

    # Get user_id (default to Kyle if not provided)
    if not user_id:
        try:
            user_id = await mvp_db.get_default_user_id()
        except Exception as e:
            logger.error("Failed to get default user", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to retrieve user information") from e

    try:
        # Verify file exists
        file_record = await mvp_db.get_file(file_id)
        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")

        # Verify ownership
        is_owner = await mvp_db.verify_file_ownership(file_id, user_id)
        if not is_owner:
            raise HTTPException(status_code=403, detail="You do not have access to this file")

        # Delete file from storage
        storage_path = file_record.get("storage_path")
        if storage_path and os.path.exists(storage_path):
            try:
                os.remove(storage_path)
            except Exception as e:
                logger.warning(f"Failed to delete file from storage: {e}")

        # Delete file record from database
        await mvp_db.delete_file(file_id)

        logger.info(f"File deleted: {file_id}")

        return {"success": True, "message": "File deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete file", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete file") from e
