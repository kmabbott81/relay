"""Command palette UI component for keyboard-first navigation."""

import os
from typing import Any, Callable, Optional

import streamlit as st

from dashboards.shortcuts import ActionType, ShortcutAction, get_shortcut_registry


def render_command_palette():
    """Render command palette modal (Ctrl/Cmd+K)."""
    # Feature flag
    if not os.getenv("FEATURE_COMMAND_PALETTE", "true").lower() == "true":
        return

    # Initialize palette state
    if "palette_open" not in st.session_state:
        st.session_state.palette_open = False
    if "palette_query" not in st.session_state:
        st.session_state.palette_query = ""

    # JavaScript for keyboard shortcut (Ctrl+K / Cmd+K)
    # In production, use proper JS event handling via Streamlit components
    st.markdown(
        """
        <script>
        document.addEventListener('keydown', function(e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                // Trigger Streamlit rerun with palette_open=true
                window.parent.postMessage({type: 'streamlit:setComponentValue', value: {palette_open: true}}, '*');
            }
        });
        </script>
        """,
        unsafe_allow_html=True,
    )

    # Render palette if open
    if st.session_state.palette_open:
        _render_palette_modal()


def _render_palette_modal():
    """Render the command palette modal UI."""
    registry = get_shortcut_registry()

    # Create modal container
    with st.container():
        st.markdown(
            """
            <style>
            .command-palette {
                position: fixed;
                top: 20%;
                left: 50%;
                transform: translateX(-50%);
                width: 600px;
                max-width: 90vw;
                background: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                z-index: 9999;
                padding: 16px;
            }
            .palette-header {
                font-size: 14px;
                color: #666;
                margin-bottom: 12px;
            }
            .palette-action {
                padding: 8px 12px;
                border-radius: 4px;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .palette-action:hover {
                background: #f5f5f5;
            }
            .action-icon {
                font-size: 18px;
            }
            .action-label {
                font-weight: 500;
            }
            .action-shortcut {
                margin-left: auto;
                font-size: 12px;
                color: #999;
                font-family: monospace;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="command-palette">', unsafe_allow_html=True)

        # Search input
        st.markdown('<div class="palette-header">⌘K Command Palette</div>', unsafe_allow_html=True)

        query = st.text_input(
            "Search actions...",
            value=st.session_state.palette_query,
            placeholder="Type to search (e.g., 'run', 'approve', 'go to')",
            key="palette_search_input",
            label_visibility="collapsed",
        )

        st.session_state.palette_query = query

        # Get filtered actions
        if query:
            actions = registry.search_actions(query)
        else:
            actions = registry.get_enabled_actions()

        # Group by category
        categories: dict[str, list[ShortcutAction]] = {}
        for action in actions[:10]:  # Limit to top 10 results
            if action.category not in categories:
                categories[action.category] = []
            categories[action.category].append(action)

        # Render actions by category
        for category, category_actions in categories.items():
            st.markdown(f"**{category}**")
            for action in category_actions:
                col1, col2 = st.columns([4, 1])

                with col1:
                    if st.button(
                        f"{action.icon} {action.label}",
                        key=f"palette_action_{action.action_id}",
                        help=action.description,
                    ):
                        _execute_palette_action(action)
                        st.session_state.palette_open = False
                        st.rerun()

                with col2:
                    if action.keyboard_shortcut:
                        st.caption(action.keyboard_shortcut)

        # Close button
        if st.button("Close (Esc)", key="palette_close"):
            st.session_state.palette_open = False
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


def _execute_palette_action(action: ShortcutAction):
    """Execute a command palette action."""
    try:
        # Get current context
        context = {
            "session_state": st.session_state,
            "action_id": action.action_id,
            "action_type": action.action_type,
        }

        # Execute action based on type
        if action.action_type == ActionType.GO_TO_HOME:
            st.session_state.active_tab = "Home"
        elif action.action_type == ActionType.GO_TO_TEMPLATES:
            st.session_state.active_tab = "Templates"
        elif action.action_type == ActionType.GO_TO_CHAT:
            st.session_state.active_tab = "Chat"
        elif action.action_type == ActionType.GO_TO_BATCH:
            st.session_state.active_tab = "Batch"
        elif action.action_type == ActionType.GO_TO_OBSERVABILITY:
            st.session_state.active_tab = "Observability"
        elif action.action_type == ActionType.GO_TO_ADMIN:
            st.session_state.active_tab = "Admin"
        elif action.action_type == ActionType.TOGGLE_THEME:
            current_theme = st.session_state.get("theme", "light")
            st.session_state.theme = "dark" if current_theme == "light" else "light"
        elif action.action_type == ActionType.SHOW_HELP:
            st.session_state.show_help_modal = True
        elif action.action_type == ActionType.FAVORITE_TEMPLATE:
            # Toggle favorite for selected template
            selected_template = st.session_state.get("selected_template")
            if selected_template:
                from relay_ai.prefs import toggle_favorite_template
                from relay_ai.security.authz import Principal, Role

                user_id = st.session_state.get("user_id", "demo-user")
                tenant_id = st.session_state.get("tenant_id", "default")
                principal = Principal(user_id=user_id, tenant_id=tenant_id, role=Role.EDITOR)

                try:
                    is_fav = toggle_favorite_template(user_id, tenant_id, selected_template, principal)
                    status = "added to" if is_fav else "removed from"
                    st.session_state.favorite_toggle_message = f"Template {status} favorites"
                except Exception as e:
                    st.session_state.favorite_toggle_error = str(e)
            else:
                st.session_state.favorite_toggle_error = "No template selected"
        else:
            # Execute custom callback if registered
            registry = get_shortcut_registry()
            registry.execute_action(action.action_id, context)

    except Exception as e:
        st.error(f"Error executing action: {e}")


def register_custom_action(
    action_id: str,
    label: str,
    description: str,
    callback: Callable[[dict[str, Any]], Any],
    keyboard_shortcut: Optional[str] = None,
    category: str = "Custom",
    icon: Optional[str] = None,
):
    """Register a custom action in the command palette."""
    registry = get_shortcut_registry()

    action = ShortcutAction(
        action_id=action_id,
        action_type=ActionType.RUN_TEMPLATE,  # Generic type for custom actions
        label=label,
        description=description,
        keyboard_shortcut=keyboard_shortcut,
        category=category,
        icon=icon or "⚡",
        callback=callback,
    )

    registry.register(action)


def open_command_palette():
    """Programmatically open the command palette."""
    st.session_state.palette_open = True
    st.session_state.palette_query = ""


def close_command_palette():
    """Programmatically close the command palette."""
    st.session_state.palette_open = False
