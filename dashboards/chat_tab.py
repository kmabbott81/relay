"""Conversational chat tab for DJP Workflow."""

import asyncio
import time
from datetime import datetime
from typing import Any

import streamlit as st


def render_chat_tab(cfg: dict[str, Any], real_mode: bool):
    """Render conversational chat interface."""
    st.subheader("💬 Chat")

    # Initialize chat history
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    # Display chat messages
    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg.get("metadata"):
                with st.expander("Metadata"):
                    st.json(msg["metadata"])

    # Chat input
    if prompt := st.chat_input("Ask a question or request analysis..."):
        # Add user message
        st.session_state["chat_history"].append({"role": "user", "content": prompt})

        with st.chat_message("user"):
            st.write(prompt)

        # Generate response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                if real_mode:
                    response, metadata = _generate_response_real(prompt, cfg)
                else:
                    response, metadata = _generate_response_mock(prompt)

                st.write(response)

                if metadata:
                    with st.expander("Response Metadata"):
                        st.json(metadata)

        # Add assistant response
        st.session_state["chat_history"].append({"role": "assistant", "content": response, "metadata": metadata})

    # Sidebar controls
    with st.sidebar:
        st.subheader("Chat Controls")

        if st.button("Clear Chat History"):
            st.session_state["chat_history"] = []
            st.rerun()

        if st.button("Save Chat to Artifact"):
            _save_chat_artifact(st.session_state["chat_history"])
            st.success("Chat saved to runs/ui/chat/")

        st.caption(f"{len(st.session_state['chat_history'])} messages")


def _generate_response_mock(prompt: str) -> tuple[str, dict]:
    """Generate mock response."""
    time.sleep(0.5)  # Simulate latency

    response = f"[Mock response to: {prompt}]\n\nThis is a simulated conversational response. In real mode, this would invoke the DJP workflow or a chat agent."

    metadata = {"mode": "mock", "timestamp": datetime.utcnow().isoformat(), "latency_ms": 500}

    return response, metadata


def _generate_response_real(prompt: str, cfg: dict) -> tuple[str, dict]:
    """Generate real response using DJP or chat agent."""
    from relay_ai.config_ui import to_allowed_models
    from relay_ai.debate import run_debate
    from relay_ai.judge import judge_drafts
    from relay_ai.publish import select_publish_text

    start = time.time()

    try:
        # Run simplified DJP workflow
        drafts = asyncio.run(
            run_debate(
                task=prompt,
                max_tokens=cfg.get("max_tokens", 1000),
                temperature=cfg.get("temperature", 0.3),
                corpus_docs=None,
                allowed_models=to_allowed_models(cfg),
            )
        )

        judgment = asyncio.run(judge_drafts(drafts=drafts, task=prompt, require_citations=0))

        status, provider, text, reason, redaction_meta = select_publish_text(
            judgment, drafts, to_allowed_models(cfg), enable_redaction=True
        )

        latency = time.time() - start

        metadata = {
            "mode": "real",
            "provider": provider,
            "status": status,
            "latency_s": round(latency, 3),
            "timestamp": datetime.utcnow().isoformat(),
        }

        return text, metadata

    except Exception as e:
        return f"Error generating response: {str(e)}", {"error": str(e)}


def _save_chat_artifact(history: list):
    """Save chat history to artifact."""
    import json
    from pathlib import Path

    chat_dir = Path("runs/ui/chat")
    chat_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    filepath = chat_dir / f"chat-{ts}.json"

    artifact = {"timestamp": datetime.utcnow().isoformat(), "message_count": len(history), "messages": history}

    filepath.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
