"""Streamlit dashboard for DJP workflow observability."""

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Add parent directory to path to import src modules
sys.path.append(str(Path(__file__).parent.parent))
from relay_ai.metrics import (
    filter_runs_by_date,
    filter_runs_by_preset,
    filter_runs_by_provider,
    filter_runs_by_template,
    load_runs,
    summarize_kpis,
    summarize_template_kpis,
)

st.set_page_config(
    page_title="DJP Workflow Observability", page_icon="📊", layout="wide", initial_sidebar_state="expanded"
)

st.title("📊 DJP Workflow Observability Dashboard")
st.markdown("Monitor costs, performance, and reliability of your Debate-Judge-Publish workflows")


# Load data
@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_dashboard_data():
    """Load workflow data with caching."""
    return load_runs()


# Load runs data
with st.spinner("Loading workflow data..."):
    df = load_dashboard_data()

if df.empty:
    st.warning("No workflow runs found in the `runs/` directory. Run some workflows first!")
    st.info("Example: `python -m src.run_workflow --task 'Test task' --preset quick`")
    st.stop()

# Sidebar filters
st.sidebar.header("🔍 Filters")

# Date range filter
date_options = {"Last 24 hours": 1, "Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90, "All time": None}

selected_period = st.sidebar.selectbox("Time Period", list(date_options.keys()), index=1)
days_filter = date_options[selected_period]

if days_filter:
    filtered_df = filter_runs_by_date(df, days_filter)
    st.sidebar.info(f"Showing {len(filtered_df)} runs from last {days_filter} days")
else:
    filtered_df = df
    st.sidebar.info(f"Showing all {len(filtered_df)} runs")

# Preset filter
presets = ["All"] + sorted(df["preset_name"].unique().tolist())
selected_preset = st.sidebar.selectbox("Preset", presets)
if selected_preset != "All":
    filtered_df = filter_runs_by_preset(filtered_df, selected_preset)

# Provider filter
providers = ["All"] + sorted(df["provider"].dropna().unique().tolist())
selected_provider = st.sidebar.selectbox("Provider", providers)
if selected_provider != "All":
    filtered_df = filter_runs_by_provider(filtered_df, selected_provider)

# Template filter (Sprint 3)
templates = ["All"] + sorted(df[df["template_name"] != ""]["template_name"].unique().tolist())
selected_template = st.sidebar.selectbox("Template", templates)
if selected_template != "All":
    filtered_df = filter_runs_by_template(filtered_df, selected_template)

# Grounded and Redacted filters
grounded_only = st.sidebar.checkbox("Grounded Only")
if grounded_only:
    filtered_df = filtered_df[filtered_df["grounded"]]

redacted_only = st.sidebar.checkbox("Redacted Only")
if redacted_only:
    filtered_df = filtered_df[filtered_df["redacted"]]

# Calculate KPIs for filtered data
kpis = summarize_kpis(filtered_df)

# Main dashboard
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Total Runs",
        f"{kpis['total_runs']:,}",
        delta=f"+{len(filtered_df) - len(df) + kpis['total_runs']:,}" if days_filter else None,
    )

with col2:
    st.metric(
        "Advisory Rate",
        f"{kpis['advisory_rate']:.1%}",
        delta=f"{kpis['advisory_rate'] - 0.1:.1%}" if kpis["advisory_rate"] > 0.1 else None,
        delta_color="inverse",
    )

with col3:
    st.metric(
        "Avg Cost",
        f"${kpis['avg_cost']:.4f}",
        delta=f"${kpis['avg_cost'] - 0.005:.4f}" if kpis["avg_cost"] > 0.005 else None,
        delta_color="inverse",
    )

with col4:
    st.metric(
        "Avg Tokens",
        f"{kpis['avg_tokens']:.0f}",
        delta=f"{kpis['avg_tokens'] - 500:.0f}" if kpis["avg_tokens"] > 500 else None,
        delta_color="inverse",
    )

# Grounded and Redacted KPIs
col1, col2, col3, col4 = st.columns(4)

with col1:
    grounded_count = filtered_df[filtered_df["grounded"]].shape[0]
    grounded_pct = (grounded_count / kpis["total_runs"] * 100) if kpis["total_runs"] > 0 else 0
    st.metric("Grounded Runs", f"{grounded_count} ({grounded_pct:.1f}%)")

with col2:
    grounded_runs = filtered_df[filtered_df["grounded"]]
    avg_citations = grounded_runs["citations_count"].mean() if len(grounded_runs) > 0 else 0
    st.metric("Avg Citations/Run", f"{avg_citations:.1f}")

with col3:
    redacted_count = filtered_df[filtered_df["redacted"]].shape[0]
    redacted_pct = (redacted_count / kpis["total_runs"] * 100) if kpis["total_runs"] > 0 else 0
    st.metric("Redacted Runs", f"{redacted_count} ({redacted_pct:.1f}%)")

with col4:
    total_redactions = filtered_df["redaction_count"].sum()
    st.metric("Redaction Events", f"{int(total_redactions):,}")

# Recent runs table
st.header("🕐 Recent Runs")
recent_df = filtered_df.head(20)

if not recent_df.empty:
    # Format the display table
    display_df = recent_df[
        ["timestamp", "preset_name", "status", "provider", "total_tokens", "est_cost", "duration", "advisory_reason"]
    ].copy()

    display_df["timestamp"] = display_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M")
    display_df["est_cost"] = display_df["est_cost"].apply(lambda x: f"${x:.4f}")
    display_df["duration"] = display_df["duration"].apply(lambda x: f"{x:.1f}s")

    st.dataframe(
        display_df,
        column_config={
            "timestamp": "Time",
            "preset_name": "Preset",
            "status": "Status",
            "provider": "Provider",
            "total_tokens": "Tokens",
            "est_cost": "Cost",
            "duration": "Duration",
            "advisory_reason": "Advisory Reason",
        },
        use_container_width=True,
        height=400,
    )
else:
    st.info("No runs match the current filters.")

# Charts section
st.header("📈 Trends and Analysis")

col1, col2 = st.columns(2)

with col1:
    if len(filtered_df) > 1:
        st.subheader("Cost Over Time")

        # Prepare data for time series
        time_df = filtered_df.copy()
        time_df = time_df.sort_values("timestamp")

        fig_cost = px.line(
            time_df,
            x="timestamp",
            y="est_cost",
            title="Estimated Cost Trend",
            labels={"est_cost": "Cost ($)", "timestamp": "Time"},
        )
        fig_cost.update_layout(height=400)
        st.plotly_chart(fig_cost, use_container_width=True)
    else:
        st.info("Need more than 1 run to show cost trend")

with col2:
    if kpis["provider_mix"]:
        st.subheader("Provider Distribution")

        providers = list(kpis["provider_mix"].keys())
        percentages = list(kpis["provider_mix"].values())

        fig_providers = px.pie(values=percentages, names=providers, title="Published Content by Provider")
        fig_providers.update_layout(height=400)
        st.plotly_chart(fig_providers, use_container_width=True)
    else:
        st.info("No published content to show provider distribution")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Status Distribution")

    status_counts = filtered_df["status"].value_counts()

    fig_status = px.bar(
        x=status_counts.index,
        y=status_counts.values,
        title="Runs by Status",
        labels={"x": "Status", "y": "Count"},
        color=status_counts.index,
        color_discrete_map={"published": "#28a745", "advisory_only": "#ffc107", "none": "#dc3545"},
    )
    fig_status.update_layout(height=400)
    st.plotly_chart(fig_status, use_container_width=True)

with col2:
    if kpis["top_failure_reasons"]:
        st.subheader("Top Advisory Reasons")

        reasons = list(kpis["top_failure_reasons"].keys())
        counts = list(kpis["top_failure_reasons"].values())

        fig_reasons = px.bar(
            x=counts,
            y=reasons,
            orientation="h",
            title="Most Common Advisory Reasons",
            labels={"x": "Count", "y": "Reason"},
        )
        fig_reasons.update_layout(height=400)
        st.plotly_chart(fig_reasons, use_container_width=True)
    else:
        st.info("No advisory reasons to display")

# Citations compliance
if any(filtered_df["citations_required"] > 0):
    st.header("📚 Citations Compliance")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.metric(
            "Citations Compliance Rate",
            f"{kpis['citations_compliance_rate']:.1%}",
            delta=f"{kpis['citations_compliance_rate'] - 0.8:.1%}" if kpis["citations_compliance_rate"] < 0.8 else None,
        )

    with col2:
        citation_df = filtered_df[filtered_df["citations_required"] > 0]
        compliance_counts = citation_df["citations_ok"].value_counts()

        fig_citations = px.pie(
            values=compliance_counts.values,
            names=["Compliant" if x else "Non-compliant" for x in compliance_counts.index],
            title="Citations Compliance",
            color_discrete_map={"Compliant": "#28a745", "Non-compliant": "#dc3545"},
        )
        st.plotly_chart(fig_citations, use_container_width=True)

# Template KPIs (Sprint 3)
template_kpis = summarize_template_kpis(filtered_df)
if not template_kpis.empty:
    st.header("📝 Template Performance")

    st.dataframe(
        template_kpis,
        column_config={
            "template_name": "Template",
            "template_version": "Version",
            "total_runs": "Total Runs",
            "published_runs": "Published",
            "advisory_runs": "Advisory",
            "success_rate": st.column_config.NumberColumn("Success Rate", format="%.1f%%", help="Published / Total"),
            "avg_cost": st.column_config.NumberColumn("Avg Cost", format="$%.4f"),
            "avg_tokens": st.column_config.NumberColumn("Avg Tokens", format="%.0f"),
            "total_cost": st.column_config.NumberColumn("Total Cost", format="$%.4f"),
        },
        use_container_width=True,
        height=400,
    )

    # Convert success_rate to percentage for display
    display_kpis = template_kpis.copy()
    display_kpis["success_rate"] = display_kpis["success_rate"] * 100

# Artifact viewer
st.header("🔍 Artifact Inspector")

if not filtered_df.empty:
    # Select run to inspect
    run_options = []
    for _, row in filtered_df.head(20).iterrows():
        run_options.append(f"{row['timestamp']:%Y-%m-%d %H:%M} - {row['preset_name']} - {row['status']}")

    selected_run_idx = st.selectbox(
        "Select a run to inspect:", range(len(run_options)), format_func=lambda x: run_options[x]
    )

    if selected_run_idx is not None:
        selected_row = filtered_df.iloc[selected_run_idx]
        artifact_file = selected_row["artifact_file"]

        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader(f"Artifact: {artifact_file}")

            # Load and display the full artifact
            artifact_path = Path("runs") / artifact_file
            if artifact_path.exists():
                try:
                    with open(artifact_path, encoding="utf-8") as f:
                        artifact_data = json.load(f)

                    st.json(artifact_data)

                except Exception as e:
                    st.error(f"Error loading artifact: {e}")
            else:
                st.error(f"Artifact file not found: {artifact_path}")

        with col2:
            st.subheader("Quick Stats")
            st.write(f"**Status:** {selected_row['status']}")
            st.write(f"**Provider:** {selected_row['provider']}")
            st.write(f"**Preset:** {selected_row['preset_name']}")
            st.write(f"**Tokens:** {selected_row['total_tokens']:,}")
            st.write(f"**Cost:** ${selected_row['est_cost']:.4f}")
            st.write(f"**Duration:** {selected_row['duration']:.1f}s")

            if selected_row["advisory_reason"]:
                st.write(f"**Advisory Reason:** {selected_row['advisory_reason']}")

            # Grounded information
            if selected_row["grounded"]:
                st.write("**Grounded:** Yes")
                st.write(f"**Citations:** {int(selected_row['citations_count'])}")

            # Redacted information
            if selected_row["redacted"]:
                st.write("**Redacted:** Yes")
                st.write(f"**Redaction Events:** {int(selected_row['redaction_count'])}")
                if pd.notna(selected_row["redaction_types"]) and selected_row["redaction_types"]:
                    st.write(f"**Redaction Types:** {selected_row['redaction_types']}")

            # Link to open file (for local development)
            st.write(f"**File:** `{artifact_path}`")

# Footer
st.markdown("---")
st.markdown("💡 **Tip:** Use the sidebar filters to drill down into specific time periods, presets, or providers.")
st.markdown("📝 **Note:** Data refreshes every 5 minutes. Click refresh in your browser to update sooner.")
