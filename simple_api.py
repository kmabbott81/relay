"""
Relay MVP - Simple Working API
This actually works, unlike the complex setup.
"""

import json
import os
import sqlite3
from datetime import datetime

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="Relay MVP - Actually Works", description="A simple chat API that actually functions", version="0.1.0"
)

# Configure CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize AI clients with new SDK syntax
openai_api_key = os.getenv("OPENAI_API_KEY")
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

# Initialize clients only if keys are available
openai_client = None
anthropic_client = None

if openai_api_key:
    try:
        openai_client = OpenAI(api_key=openai_api_key)
        print("✓ OpenAI client initialized")
    except Exception as e:
        print(f"⚠ OpenAI client failed: {e}")

if anthropic_api_key:
    try:
        anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)
        print("✓ Anthropic client initialized")
    except Exception as e:
        print(f"⚠ Anthropic client failed: {e}")

if not openai_client and not anthropic_client:
    print("\n⚠ WARNING: No AI clients configured!")
    print("Add OPENAI_API_KEY or ANTHROPIC_API_KEY to .env file\n")


# Simple SQLite database setup
def init_db():
    """Initialize the SQLite database"""
    conn = sqlite3.connect("relay_chat.db")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            user_message TEXT NOT NULL,
            ai_response TEXT NOT NULL,
            model TEXT NOT NULL,
            tokens_used INTEGER DEFAULT 0
        )
    """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_session
        ON conversations(user_id, session_id, timestamp DESC)
    """
    )
    conn.commit()
    conn.close()
    print("✅ Database initialized")


# Initialize database on startup
init_db()


# Request/Response models
class ChatRequest(BaseModel):
    message: str
    model: str = "gpt-3.5-turbo"
    user_id: str = "demo-user"
    session_id: str = "default"
    stream: bool = False


class ChatResponse(BaseModel):
    response: str
    model: str
    timestamp: str
    tokens_used: int = 0


class HistoryItem(BaseModel):
    id: int
    user_message: str
    ai_response: str
    timestamp: str
    model: str


# Helper function to save conversation
def save_conversation(user_id: str, session_id: str, user_msg: str, ai_msg: str, model: str, tokens: int = 0):
    """Save a conversation to the database"""
    conn = sqlite3.connect("relay_chat.db")
    conn.execute(
        """INSERT INTO conversations
           (user_id, session_id, timestamp, user_message, ai_response, model, tokens_used)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, session_id, datetime.now().isoformat(), user_msg, ai_msg, model, tokens),
    )
    conn.commit()
    conn.close()


# API Endpoints
@app.get("/")
def root():
    """Root endpoint - verify API is running"""
    return {
        "status": "running",
        "message": "Relay MVP API is actually working!",
        "endpoints": ["/health", "/chat", "/chat/stream", "/history/{user_id}", "/sessions/{user_id}"],
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    # Check if database is accessible
    try:
        conn = sqlite3.connect("relay_chat.db")
        cursor = conn.execute("SELECT COUNT(*) FROM conversations")
        message_count = cursor.fetchone()[0]
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False
        message_count = 0

    # Determine overall status
    ai_available = bool(openai_client or anthropic_client)
    overall_status = "healthy" if (ai_available and db_ok) else "degraded"

    return {
        "status": overall_status,
        "timestamp": datetime.now().isoformat(),
        "checks": {
            "openai_configured": bool(openai_client),
            "anthropic_configured": bool(anthropic_client),
            "database_accessible": db_ok,
            "total_messages": message_count if db_ok else 0,
        },
        "note": "Local MVP sandbox - not production Relay system",
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Main chat endpoint - send a message, get a response"""

    # Determine which AI to use based on model
    if "claude" in request.model.lower():
        # Use Anthropic/Claude
        if not anthropic_client:
            raise HTTPException(status_code=500, detail="Anthropic API key not configured")

        try:
            response = anthropic_client.messages.create(
                model="claude-3-haiku-20240307",  # Fast and cheap model
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
            # Use new OpenAI SDK syntax
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

    # Save to database (for both OpenAI and Claude)
    save_conversation(request.user_id, request.session_id, request.message, ai_response, request.model, tokens_used)

    return ChatResponse(
        response=ai_response, model=request.model, timestamp=datetime.now().isoformat(), tokens_used=tokens_used
    )


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Streaming chat endpoint - get responses in real-time"""

    async def generate():
        full_response = ""

        try:
            if "claude" in request.model.lower():
                # Claude streaming
                if not anthropic_client:
                    yield f"data: {json.dumps({'error': 'Anthropic API key not configured'})}\n\n"
                    return

                with anthropic_client.messages.stream(
                    model="claude-3-haiku-20240307",
                    max_tokens=1000,
                    temperature=0.7,
                    messages=[{"role": "user", "content": request.message}],
                ) as stream:
                    for text in stream.text_stream:
                        full_response += text
                        yield f"data: {json.dumps({'content': text})}\n\n"
            else:
                # OpenAI streaming
                if not openai_client:
                    yield f"data: {json.dumps({'error': 'OpenAI API key not configured'})}\n\n"
                    return

                stream = openai_client.chat.completions.create(
                    model=request.model,
                    messages=[
                        {"role": "system", "content": "You are Relay, a helpful AI assistant."},
                        {"role": "user", "content": request.message},
                    ],
                    max_tokens=1000,
                    temperature=0.7,
                    stream=True,
                )

                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_response += content
                        yield f"data: {json.dumps({'content': content})}\n\n"

            # Save conversation after streaming completes
            save_conversation(request.user_id, request.session_id, request.message, full_response, request.model)

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/history/{user_id}")
def get_history(user_id: str, session_id: str = "default", limit: int = 20):
    """Get conversation history for a user/session"""

    conn = sqlite3.connect("relay_chat.db")
    cursor = conn.execute(
        """SELECT id, user_message, ai_response, timestamp, model, tokens_used
           FROM conversations
           WHERE user_id = ? AND session_id = ?
           ORDER BY timestamp DESC
           LIMIT ?""",
        (user_id, session_id, limit),
    )

    history = []
    for row in cursor.fetchall():
        history.append(
            {
                "id": row[0],
                "user_message": row[1],
                "ai_response": row[2],
                "timestamp": row[3],
                "model": row[4],
                "tokens_used": row[5],
            }
        )

    conn.close()

    # Reverse to get chronological order
    history.reverse()

    return {"user_id": user_id, "session_id": session_id, "history": history}


@app.get("/sessions/{user_id}")
def get_sessions(user_id: str):
    """Get all sessions for a user"""

    conn = sqlite3.connect("relay_chat.db")
    cursor = conn.execute(
        """SELECT DISTINCT session_id,
                  COUNT(*) as message_count,
                  MIN(timestamp) as first_message,
                  MAX(timestamp) as last_message
           FROM conversations
           WHERE user_id = ?
           GROUP BY session_id
           ORDER BY last_message DESC""",
        (user_id,),
    )

    sessions = []
    for row in cursor.fetchall():
        sessions.append(
            {"session_id": row[0], "message_count": row[1], "first_message": row[2], "last_message": row[3]}
        )

    conn.close()

    return {"user_id": user_id, "sessions": sessions}


@app.delete("/history/{user_id}/{session_id}")
def clear_session(user_id: str, session_id: str):
    """Clear a specific session's history"""

    conn = sqlite3.connect("relay_chat.db")
    cursor = conn.execute("DELETE FROM conversations WHERE user_id = ? AND session_id = ?", (user_id, session_id))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    return {"deleted": deleted, "message": f"Cleared {deleted} messages from session"}


# Multi-AI endpoint (bonus feature)
@app.post("/multi-chat")
async def multi_chat(request: ChatRequest):
    """Get responses from multiple models simultaneously"""

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

    # Save combined response
    combined_response = "\n\n".join([f"**{model}:**\n{resp}" for model, resp in responses.items()])
    save_conversation(request.user_id, f"{request.session_id}-multi", request.message, combined_response, "multi-ai", 0)

    return {"timestamp": datetime.now().isoformat(), "responses": responses}


# Run the server
if __name__ == "__main__":
    import uvicorn

    print("\n" + "=" * 50)
    print("Relay Local MVP - Sandbox & Demo Tool")
    print("=" * 50)
    print("\n⚠ NOTE: This is a LOCAL SANDBOX, not the production Relay system")
    print("   Production Relay is on Railway with Supabase, SSE, etc.\n")
    print("Endpoints available at http://localhost:8000")
    print("API documentation at http://localhost:8000/docs")
    print("Web UI: Open simple_ui.html in your browser")

    if not openai_client and not anthropic_client:
        print("\n⚠ WARNING: No AI providers configured!")
        print("   Add OPENAI_API_KEY or ANTHROPIC_API_KEY to .env file")
    else:
        print("\n✓ Configured AI providers:")
        if openai_client:
            print("  - OpenAI (GPT models)")
        if anthropic_client:
            print("  - Anthropic (Claude models)")

    print("\n" + "=" * 50 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
