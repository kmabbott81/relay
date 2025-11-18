# Relay MVP - Local Sandbox & Demo Tool

## ⚠️ IMPORTANT: What This IS and IS NOT

### This IS:
- **A local development sandbox** for testing multi-AI conversations
- **A fallback demo** that always works, even when Railway is down
- **A simple proof-of-concept** showing core chat functionality
- **A playground** for experimenting with OpenAI and Claude side-by-side

### This IS NOT:
- ❌ **NOT the production Relay system** (that's the main Magic Box on Railway + Supabase)
- ❌ **NOT meant to replace** the main Relay architecture
- ❌ **NOT production-ready** (no auth, no file connectors, no robust SSE, no metrics)
- ❌ **NOT the final product** - treat this as a lab bench, not the canonical system

**The main Relay product** (at ~85% to beta) with Supabase auth, SSE, connectors, and metrics is the north star. This MVP is just a local tool that runs independently.

---

## What This Tool Provides

A **working** multi-AI chat application with:
- ✅ Real AI conversations (OpenAI GPT + Anthropic Claude)
- ✅ Conversation history (SQLite database)
- ✅ Streaming responses
- ✅ Multi-model comparison (ask both AIs at once)
- ✅ Simple web UI that actually works

## Setup in 5 Minutes

### 1. Install Dependencies

```bash
pip install -r requirements_mvp.txt
```

### 2. Set Up Your API Keys

Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` and add your actual API keys:
```
OPENAI_API_KEY=sk-your-actual-openai-key
ANTHROPIC_API_KEY=sk-ant-your-actual-anthropic-key
```

### 3. Run the Backend

```bash
python simple_api.py
```

You should see:
```
==================================================
🚀 Starting Relay MVP API
==================================================

Endpoints available at http://localhost:8000
API documentation at http://localhost:8000/docs

Make sure you have set OPENAI_API_KEY in .env file
==================================================
```

### 4. Open the UI

Open `simple_ui.html` in your browser (just double-click it).

## How to Use

1. **Single AI Chat**: Type a message and click "Send"
2. **Compare AIs**: Type a message and click "Ask Both" to get responses from GPT and Claude
3. **Switch Models**: Use the radio buttons to choose between GPT-3.5, GPT-4, or Claude
4. **New Session**: Click "New Session" to start a fresh conversation
5. **Clear History**: Click "Clear History" to delete current session messages

## API Endpoints

- `GET /` - Check if API is running
- `GET /health` - Health check with status
- `POST /chat` - Send message, get response
- `POST /chat/stream` - Streaming responses
- `POST /multi-chat` - Get responses from both AIs
- `GET /history/{user_id}` - Get conversation history
- `GET /sessions/{user_id}` - List all sessions
- `DELETE /history/{user_id}/{session_id}` - Clear session

## Testing the API

### Quick Test with curl:
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, are you working?", "model": "gpt-3.5-turbo"}'
```

### Interactive API Docs:
Visit http://localhost:8000/docs for interactive API documentation

## Troubleshooting

### "API Offline" Error in UI
- Make sure `python simple_api.py` is running
- Check that port 8000 is not in use

### "OpenAI API key not configured"
- Make sure you created `.env` file (not just `.env.example`)
- Verify your API key starts with `sk-`
- Restart the API after adding keys

### "Anthropic API key not configured"
- Claude features require an Anthropic API key
- Get one at https://console.anthropic.com/
- Add to `.env` as `ANTHROPIC_API_KEY=sk-ant-...`

## Major Limitations vs. Full Relay

This local MVP intentionally **lacks** many features of the production Relay system:

| Feature | Local MVP | Production Relay |
|---------|-----------|------------------|
| Authentication | ❌ None | ✅ Supabase auth + RBAC |
| Database | ❌ SQLite (local only) | ✅ PostgreSQL (Supabase) |
| File Uploads | ❌ Not supported | ✅ R2 storage + embeddings |
| Service Connectors | ❌ None | ✅ Gmail, Slack, etc. |
| SSE/Streaming | ⚠️ Basic only | ✅ Robust implementation |
| Metrics & Telemetry | ❌ None | ✅ Full observability |
| Multi-tenancy | ❌ Single user | ✅ Workspace isolation |
| Cost Tracking | ❌ None | ✅ Token budgets |
| API Security | ❌ No rate limits | ✅ API keys + quotas |

**Bottom line:** Use this MVP for quick local testing, NOT as a production replacement.

## What's Next?

Optional enhancements for this local tool:
1. Add simple Gmail OAuth flow (see `LOCAL_SETUP_PLAN.md`)
2. Add basic cost tracking per session
3. Export conversation history to JSON/CSV
4. Add more model options (GPT-4o, Claude Opus, etc.)

**For production features**, work on the main Relay stack instead.

## Files in This MVP

- `simple_api.py` - FastAPI backend with all endpoints
- `simple_ui.html` - Complete web interface
- `requirements_mvp.txt` - Python dependencies
- `.env.example` - Environment variable template
- `relay_chat.db` - SQLite database (created automatically)

---

## How to Reset/Clean Up

Reset the SQLite database:
```bash
# Delete the database file to start fresh
rm relay_chat.db

# Restart the API - it will recreate the database
python simple_api.py
```

---

**This local MVP actually works.** Simple setup, minimal dependencies, always functional - even when Railway is down. Use it as your local playground while building the production Relay system.
