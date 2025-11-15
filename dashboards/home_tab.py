"""Home tab with personalized dashboard cards and quick actions."""

import os

import streamlit as st

# Feature flag
FEATURE_HOME = os.getenv("FEATURE_HOME", "true").lower() == "true"


def render_home_tab():
    """Render the Home tab with personalized cards."""
    if not FEATURE_HOME:
        st.info("Home dashboard is disabled. Set FEATURE_HOME=true to enable.")
        return

    st.title("🏠 Home")

    # Get current user context
    user_id = st.session_state.get("user_id", "anonymous")
    tenant_id = st.session_state.get("tenant_id", "default")

    # Tenant switcher (if user has multiple tenants)
    available_tenants = st.session_state.get("available_tenants", [tenant_id])
    if len(available_tenants) > 1:
        col1, col2 = st.columns([3, 1])
        with col2:
            selected_tenant = st.selectbox(
                "Tenant",
                options=available_tenants,
                index=available_tenants.index(tenant_id) if tenant_id in available_tenants else 0,
                key="home_tenant_selector",
            )
            if selected_tenant != tenant_id:
                st.session_state.tenant_id = selected_tenant
                st.rerun()

    # Layout: 2 columns
    col1, col2 = st.columns([2, 1])

    with col1:
        _render_favorites_card(user_id, tenant_id)
        _render_recent_artifacts_card(tenant_id)
        _render_recent_chats_card(tenant_id)

    with col2:
        _render_budget_card(tenant_id)
        _render_quick_actions_card()


def _render_favorites_card(user_id: str, tenant_id: str):
    """Render favorite templates card."""
    st.subheader("⭐ Favorite Templates")

    try:
        from relay_ai.prefs import get_favorite_templates
        from relay_ai.security.authz import Principal, Role

        # Create principal for current user
        principal = Principal(user_id=user_id, tenant_id=tenant_id, role=Role.VIEWER)
        favorites = get_favorite_templates(user_id, tenant_id, principal)

        if not favorites:
            st.info("No favorite templates yet. Star templates from the Templates tab to see them here.")
            return

        # Display favorites with quick run buttons
        for template_slug in favorites[:5]:  # Show top 5
            col1, col2 = st.columns([3, 1])

            with col1:
                st.markdown(f"**{template_slug}**")

            with col2:
                if st.button("▶️ Run", key=f"run_fav_{template_slug}"):
                    st.session_state.active_tab = "Templates"
                    st.session_state.selected_template = template_slug
                    st.rerun()

        if len(favorites) > 5:
            st.caption(f"... and {len(favorites) - 5} more favorites")

    except Exception as e:
        st.error(f"Error loading favorites: {e}")


def _render_recent_artifacts_card(tenant_id: str):
    """Render recent artifacts card."""
    st.subheader("📄 Recent Artifacts")

    try:
        # Get recent artifacts for this tenant
        # This would integrate with src/artifacts.py
        # For now, show placeholder
        recent_artifacts = st.session_state.get("recent_artifacts", [])

        if not recent_artifacts:
            st.info("No recent artifacts. Run a template to generate artifacts.")
            return

        for artifact in recent_artifacts[:10]:  # Show last 10
            artifact_id = artifact.get("id", "unknown")
            title = artifact.get("title", "Untitled")
            status = artifact.get("status", "unknown")
            cost = artifact.get("cost_usd", 0.0)

            col1, col2, col3 = st.columns([3, 1, 1])

            with col1:
                st.markdown(f"**{title}**")

            with col2:
                status_icon = "✅" if status == "approved" else "⏳" if status == "pending" else "❌"
                st.caption(f"{status_icon} {status}")

            with col3:
                st.caption(f"${cost:.3f}")

            if st.button("View", key=f"view_artifact_{artifact_id}"):
                st.session_state.selected_artifact_id = artifact_id
                st.info(f"Viewing artifact: {artifact_id}")

    except Exception as e:
        st.error(f"Error loading artifacts: {e}")


def _render_recent_chats_card(tenant_id: str):
    """Render recent chat sessions card."""
    st.subheader("💬 Recent Chats")

    try:
        # Get recent chats for this tenant
        recent_chats = st.session_state.get("recent_chats", [])

        if not recent_chats:
            st.info("No recent chats. Start a conversation in the Chat tab.")
            return

        for chat in recent_chats[:10]:  # Show last 10
            chat_id = chat.get("id", "unknown")
            title = chat.get("title", "Untitled Chat")
            timestamp = chat.get("timestamp", "")

            col1, col2 = st.columns([4, 1])

            with col1:
                st.markdown(f"**{title}**")
                if timestamp:
                    st.caption(f"Last active: {timestamp}")

            with col2:
                if st.button("Resume", key=f"resume_chat_{chat_id}"):
                    st.session_state.active_tab = "Chat"
                    st.session_state.selected_chat_id = chat_id
                    st.rerun()

    except Exception as e:
        st.error(f"Error loading chats: {e}")


def _render_budget_card(tenant_id: str):  # noqa: ARG001
    """Render budget usage card."""
    st.subheader("💰 Budget Usage")

    try:
        # Get budget data for this tenant
        # This would integrate with budgets system
        daily_used = st.session_state.get("daily_budget_used", 0.0)
        daily_limit = st.session_state.get("daily_budget_limit", 100.0)

        monthly_used = st.session_state.get("monthly_budget_used", 0.0)
        monthly_limit = st.session_state.get("monthly_budget_limit", 3000.0)

        # Daily budget
        st.markdown("**Today**")
        daily_pct = (daily_used / daily_limit * 100) if daily_limit > 0 else 0

        st.progress(min(daily_pct / 100, 1.0))
        st.caption(f"${daily_used:.2f} / ${daily_limit:.2f} ({daily_pct:.1f}%)")

        if daily_pct >= 100:
            st.error("⚠️ Daily budget exceeded!")
        elif daily_pct >= 90:
            st.warning("⚠️ Approaching daily budget limit")

        st.markdown("---")

        # Monthly budget
        st.markdown("**This Month**")
        monthly_pct = (monthly_used / monthly_limit * 100) if monthly_limit > 0 else 0

        st.progress(min(monthly_pct / 100, 1.0))
        st.caption(f"${monthly_used:.2f} / ${monthly_limit:.2f} ({monthly_pct:.1f}%)")

        if monthly_pct >= 100:
            st.error("⚠️ Monthly budget exceeded!")
        elif monthly_pct >= 90:
            st.warning("⚠️ Approaching monthly budget limit")

    except Exception as e:
        st.error(f"Error loading budget: {e}")


def _render_quick_actions_card():
    """Render quick actions card."""
    st.subheader("⚡ Quick Actions")

    if st.button("📝 Browse Templates", key="quick_templates", use_container_width=True):
        st.session_state.active_tab = "Templates"
        st.rerun()

    if st.button("💬 New Chat", key="quick_chat", use_container_width=True):
        st.session_state.active_tab = "Chat"
        st.rerun()

    if st.button("📦 Batch Jobs", key="quick_batch", use_container_width=True):
        st.session_state.active_tab = "Batch"
        st.rerun()

    if st.button("📊 Observability", key="quick_obs", use_container_width=True):
        st.session_state.active_tab = "Observability"
        st.rerun()
