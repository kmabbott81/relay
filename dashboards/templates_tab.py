from __future__ import annotations

import json
import time
from datetime import date as date_type
from pathlib import Path
from typing import Any

import streamlit as st

from relay_ai.config_ui import to_allowed_models
from relay_ai.templates import (
    InputDef,
    TemplateRenderError,
    check_budget,
    clone_template,
    create_template_artifact,
    estimate_batch_cost,
    estimate_template_cost,
    export_docx,
    export_markdown,
    list_templates,
    load_csv_for_batch,
    process_batch_dry_run,
    render_template,
    to_slug,
    validate_inputs,
)


# Optional: import real path; fallback to select() mock if not available
def _run_once_real(draft_text: str, grounded: bool, local_corpus, cfg: dict[str, Any]):
    """Try real DJP; fallback to select(). Returns (status, provider, text, reason, redaction, usage_rows)."""
    try:
        from relay_ai.corpus import load_corpus
        from relay_ai.debate import run_debate
        from relay_ai.judge import judge_drafts
        from relay_ai.publish import select_publish_text

        corpus_docs = load_corpus(local_corpus) if grounded else None
        drafts = run_debate(
            task=draft_text,
            max_tokens=int(cfg.get("max_tokens", 1000)),
            temperature=float(cfg.get("temperature", 0.3)),
            corpus_docs=corpus_docs,
            allowed_models=to_allowed_models(cfg),
        )
        if hasattr(drafts, "__await__"):
            import asyncio

            drafts = asyncio.get_event_loop().run_until_complete(drafts)
        judgment = judge_drafts(
            drafts=drafts, task=draft_text, require_citations=2 if grounded else 0, corpus_docs=corpus_docs
        )
        if hasattr(judgment, "__await__"):
            import asyncio

            judgment = asyncio.get_event_loop().run_until_complete(judgment)
        status, provider, text, reason, redaction = select_publish_text(judgment)
        usage_rows = []
        try:
            for d in drafts:
                pr = getattr(d, "provider", "")
                pt = int(getattr(d, "prompt_tokens", 0))
                ct = int(getattr(d, "completion_tokens", 0))
                usage_rows.append(
                    {"phase": "debate", "provider": pr, "prompt_tokens": pt, "completion_tokens": ct, "latency_s": 0}
                )
            pr = getattr(judgment, "provider", provider or "")
            pt = int(getattr(judgment, "prompt_tokens", 0))
            ct = int(getattr(judgment, "completion_tokens", 0))
            usage_rows.append(
                {"phase": "judge", "provider": pr, "prompt_tokens": pt, "completion_tokens": ct, "latency_s": 0}
            )
            usage_rows.append(
                {
                    "phase": "select",
                    "provider": provider or "",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "latency_s": 0,
                }
            )
        except Exception:
            pass
        return status, provider, text, reason, redaction, usage_rows
    except Exception:
        from relay_ai.publish import select_publish_text

        status, provider, text, reason, redaction = select_publish_text({"text": draft_text, "grounded": grounded})
        return status, provider, text, reason, redaction, []


def _render_input_widget(inp: InputDef) -> Any:
    """
    Render appropriate Streamlit widget based on input type.

    Args:
        inp: InputDef describing the input field

    Returns:
        User input value
    """
    help_text = inp.help if inp.help else None
    label = f"{inp.label}{'*' if inp.required else ''}"

    # String type
    if inp.type == "string":
        return st.text_input(label, value=str(inp.default or ""), help=help_text, placeholder=inp.placeholder or "")

    # Text type (multiline)
    elif inp.type == "text":
        return st.text_area(
            label, value=str(inp.default or ""), help=help_text, height=100, placeholder=inp.placeholder or ""
        )

    # Integer type
    elif inp.type == "int":
        min_val = inp.validators.get("min", 0)
        max_val = inp.validators.get("max", 1000000)
        default_val = int(inp.default) if inp.default is not None else min_val
        return st.number_input(label, min_value=min_val, max_value=max_val, value=default_val, step=1, help=help_text)

    # Float type
    elif inp.type == "float":
        min_val = float(inp.validators.get("min", 0.0))
        max_val = float(inp.validators.get("max", 1000000.0))
        default_val = float(inp.default) if inp.default is not None else min_val
        return st.number_input(
            label, min_value=min_val, max_value=max_val, value=default_val, step=0.1, format="%.2f", help=help_text
        )

    # Boolean type
    elif inp.type == "bool":
        default_val = bool(inp.default) if inp.default is not None else False
        return st.checkbox(label, value=default_val, help=help_text)

    # Enum type (single select)
    elif inp.type == "enum":
        choices = inp.validators.get("choices", [])
        if not choices:
            st.error(f"Enum field '{inp.label}' has no choices defined")
            return None
        default_idx = 0
        if inp.default and inp.default in choices:
            default_idx = choices.index(inp.default)
        return st.selectbox(label, choices, index=default_idx, help=help_text)

    # Multiselect type
    elif inp.type == "multiselect":
        choices = inp.validators.get("choices", [])
        if not choices:
            st.error(f"Multiselect field '{inp.label}' has no choices defined")
            return []
        default_val = inp.default if isinstance(inp.default, list) else []
        return st.multiselect(label, choices, default=default_val, help=help_text)

    # Date type
    elif inp.type == "date":
        try:
            if inp.default:
                from datetime import datetime

                default_val = datetime.strptime(str(inp.default), "%Y-%m-%d").date()
            else:
                default_val = date_type.today()
        except Exception:
            default_val = date_type.today()
        return st.date_input(label, value=default_val, help=help_text)

    # Email type (text input with validation)
    elif inp.type == "email":
        return st.text_input(label, value=str(inp.default or ""), help=help_text, placeholder="user@example.com")

    # URL type (text input with validation)
    elif inp.type == "url":
        return st.text_input(label, value=str(inp.default or ""), help=help_text, placeholder="https://example.com")

    # Fallback
    else:
        st.warning(f"Unknown input type: {inp.type}")
        return st.text_input(label, value=str(inp.default or ""), help=help_text)


def render_templates_tab():
    """Render the Templates tab with type-aware widgets and inline validation."""
    st.subheader("Template Library")
    st.caption("Pick a template, edit variables, preview, run via DJP, and export results.")

    # Load templates
    tdefs = list_templates()
    if not tdefs:
        st.info("No templates found. Add YAML files to ./templates/")
        st.info("Templates must conform to schemas/template.json")
        return

    # Template selector
    tkeys = [f"{t.name} (v{t.version}) · {t.key}" for t in tdefs]
    idx = st.selectbox("Choose template", list(range(len(tdefs))), format_func=lambda i: tkeys[i])
    template = tdefs[idx]

    # Display template info
    st.write(f"**Description:** {template.description}")
    st.caption(f"Context: {template.context} | Version: {template.version} | Path: {template.path.name}")

    # Clone button (Sprint 4)
    col_clone1, col_clone2 = st.columns([3, 1])
    with col_clone2:
        if st.button("+ Clone Template", key="clone_btn"):
            st.session_state["show_clone_dialog"] = True

    # Clone dialog
    if st.session_state.get("show_clone_dialog", False):
        with st.form("clone_form"):
            st.markdown("### Clone Template")
            new_name = st.text_input("Template Name", value=f"{template.name} (Copy)")
            new_desc = st.text_area("Description", value=template.description)

            col_submit, col_cancel = st.columns(2)
            submitted = col_submit.form_submit_button("Create Clone")
            cancelled = col_cancel.form_submit_button("Cancel")

            if submitted:
                try:
                    cloned_path = clone_template(template, new_name, new_desc)
                    st.success(f"✅ Created: {cloned_path.name}")
                    st.session_state["show_clone_dialog"] = False
                    st.rerun()
                except ValueError as e:
                    st.error(f"❌ Error: {e}")

            if cancelled:
                st.session_state["show_clone_dialog"] = False
                st.rerun()

    st.markdown("---")

    # Input form
    st.markdown("#### Input Variables")
    vars_state: dict[str, Any] = {}

    for inp in template.inputs:
        value = _render_input_widget(inp)
        vars_state[inp.id] = value

    st.markdown("---")

    # Validate inputs
    validation_errors = validate_inputs(template, vars_state)
    if validation_errors:
        st.error("**Validation Errors:**")
        for err in validation_errors:
            st.error(f"• {err}")

    # Cost projection (show before validation errors)
    if not validation_errors:
        try:
            cost_est = estimate_template_cost(template, vars_state)
            st.info(
                f"💰 **Projected Cost:** ${cost_est['cost_usd']:.4f} (±{cost_est['margin_pct']:.0f}%) | "
                f"~{cost_est['tokens_estimated']:,} tokens"
            )
        except Exception:
            pass  # Silently skip if cost estimation unavailable

    # Budget controls
    col_budget1, col_budget2 = st.columns(2)
    budget_usd = col_budget1.number_input("Budget (USD)", min_value=0.0, value=0.0, step=0.01, help="Set 0 to disable")
    budget_tokens = col_budget2.number_input(
        "Budget (tokens)", min_value=0, value=0, step=1000, help="Set 0 to disable"
    )

    # Check budget if set
    budget_error = ""
    if not validation_errors and (budget_usd > 0 or budget_tokens > 0):
        try:
            cost_est = estimate_template_cost(template, vars_state)
            within_budget, warning, error = check_budget(
                cost_est["cost_usd"],
                cost_est["tokens_estimated"],
                budget_usd if budget_usd > 0 else None,
                budget_tokens if budget_tokens > 0 else None,
            )
            budget_error = error
            if warning:
                st.warning(f"⚠️ {warning}")
            if error:
                st.error(f"❌ {error}")
        except Exception:
            pass

    # Action buttons
    col1, col2, col3, col4, col5 = st.columns(5)
    grounded = col1.toggle("Grounded mode", value=False)
    require_approval = col2.checkbox(
        "Require Approval", value=False, help="Run will need manual approval before publishing"
    )
    preview_btn = col3.button("Preview", disabled=bool(validation_errors))
    run_btn = col4.button("Run via DJP", disabled=bool(validation_errors) or bool(budget_error))
    export_section = col5.expander("Export")

    with export_section:
        export_md = st.button("Export Markdown")
        export_dx = st.button("Export DOCX")

    # Preview section
    if preview_btn:
        st.markdown("#### Preview")
        try:
            preview_text = render_template(template, vars_state)
            st.code(preview_text, language="markdown")
        except TemplateRenderError as e:
            st.error(f"**Render Error:** {e}")
        except Exception as e:
            st.error(f"**Unexpected Error:** {e}")

    # Export handlers
    if export_md and not validation_errors:
        try:
            preview_text = render_template(template, vars_state)
            fname = f"{to_slug(template.name)}-{int(time.time())}"
            p = export_markdown(preview_text, fname)
            st.success(f"Saved Markdown: {p}")
        except Exception as e:
            st.error(f"Export failed: {e}")

    if export_dx and not validation_errors:
        try:
            preview_text = render_template(template, vars_state)
            fname = f"{to_slug(template.name)}-{int(time.time())}"
            # Use template style if specified
            style_path = template.style if template.style else None
            p = export_docx(preview_text, fname, heading=template.name, style_path=style_path)
            st.success(f"Saved DOCX: {p}")
        except Exception as e:
            st.error(f"Export failed: {e}")

    # Run via DJP
    if run_btn and not validation_errors:
        st.markdown("#### DJP Result")

        # Corpus upload
        up = st.file_uploader("Optional corpus (.txt/.md/.pdf)", type=["txt", "md", "pdf"], accept_multiple_files=True)
        local_corpus = []
        if up and grounded:
            cdir = Path("runs/ui/templates/corpus")
            cdir.mkdir(parents=True, exist_ok=True)
            for f in up:
                p = cdir / f.name
                p.write_bytes(f.read())
                local_corpus.append(str(p))

        try:
            # Render template first
            draft_text = render_template(template, vars_state)

            # Get cost projection
            try:
                cost_projection = estimate_template_cost(template, vars_state)
            except Exception:
                cost_projection = None

            # Run DJP
            cfg = st.session_state.get("cfg", {})
            status, provider, text, reason, redaction, usage_rows = _run_once_real(
                draft_text, grounded, local_corpus, cfg
            )

            # Handle approval workflow (Sprint 4)
            if require_approval and status == "published":
                status = "pending_approval"
                reason = f"Awaiting approval | Provider: {provider}"

            st.markdown(f"**Status:** `{status}`  **Provider:** `{provider}`")
            if reason:
                st.caption(f"Reason: {reason}")
            st.text_area("Output", text, height=240)
            if redaction:
                st.json(redaction)

            # Approval buttons (Sprint 4)
            if status == "pending_approval":
                st.markdown("---")
                st.markdown("### Approval Required")
                col_approve, col_reject = st.columns(2)

                with col_approve:
                    if st.button("✅ Approve & Publish", key="approve_btn"):
                        status = "published"
                        reason = ""
                        st.success("Approved! Status updated to Published.")
                        st.rerun()

                with col_reject:
                    rejection_reason = st.text_input("Rejection reason", placeholder="e.g., Needs more detail")
                    if st.button("❌ Reject", key="reject_btn") and rejection_reason:
                        status = "advisory_only"
                        reason = f"Rejected by reviewer: {rejection_reason}"
                        st.warning(f"Rejected: {rejection_reason}")
                        st.rerun()

            # Calculate actual cost
            actual_cost = 0.0
            actual_tokens = 0
            for row in usage_rows:
                actual_tokens += row.get("prompt_tokens", 0) + row.get("completion_tokens", 0)

            # Show cost comparison
            if cost_projection:
                st.caption(
                    f"Projected: ${cost_projection['cost_usd']:.4f} | Actual: ${actual_cost:.4f} (usage data incomplete)"
                )

            # Create structured artifact
            result = {
                "status": status,
                "provider": provider,
                "text": text,
                "reason": reason,
                "usage": usage_rows,
                "redaction_metadata": redaction,
            }

            artifact = create_template_artifact(
                template=template,
                variables=vars_state,
                rendered_body=draft_text,
                result=result,
                cost_projection=cost_projection,
            )

            # Save artifact with proper naming
            out_dir = Path("runs/ui/templates")
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            fname = f"{ts}-{to_slug(template.key)}-{to_slug(status)}.json"
            fp = out_dir / fname
            fp.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
            st.success(f"Saved run artifact: {fp}")

        except TemplateRenderError as e:
            st.error(f"**Render Error:** {e}")
        except Exception as e:
            st.error(f"**Error:** {e}")

    # Batch processing section (Sprint 3)
    st.markdown("---")
    st.markdown("#### Batch Processing (CSV)")

    batch_expander = st.expander("Batch Run from CSV")
    with batch_expander:
        st.caption("Upload a CSV file with columns matching template input IDs. Process multiple rows at once.")

        csv_file = st.file_uploader("Upload CSV file", type=["csv"], key="batch_csv")

        if csv_file:
            # Save uploaded file temporarily
            import tempfile

            with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as tmp:
                tmp.write(csv_file.read())
                csv_path = tmp.name

            try:
                # Load and validate CSV
                rows, errors = load_csv_for_batch(csv_path, template)

                if errors:
                    st.error(f"**CSV Validation Errors ({len(errors)}):**")
                    for error in errors[:10]:  # Show first 10 errors
                        st.error(f"• {error}")
                    if len(errors) > 10:
                        st.caption(f"... and {len(errors) - 10} more errors")

                if rows:
                    st.success(f"Loaded {len(rows)} valid rows from CSV")

                    # Show preview of first 3 rows
                    st.markdown("**Preview (first 3 rows):**")
                    for row in rows[:3]:
                        st.json(row)

                    # Estimate batch cost
                    batch_est = estimate_batch_cost(template, rows)

                    st.info(
                        f"💰 **Batch Cost Estimate:** ${batch_est['total_cost_usd']:.4f} | "
                        f"~{batch_est['total_tokens']:,} tokens for {batch_est['num_rows']} rows"
                    )

                    # Batch budget controls
                    col_b1, col_b2 = st.columns(2)
                    batch_budget_usd = col_b1.number_input(
                        "Batch Budget (USD)", min_value=0.0, value=0.0, step=0.01, key="batch_budget_usd"
                    )
                    batch_budget_tokens = col_b2.number_input(
                        "Batch Budget (tokens)", min_value=0, value=0, step=1000, key="batch_budget_tokens"
                    )

                    # Check batch budget
                    batch_budget_error = ""
                    if batch_budget_usd > 0 or batch_budget_tokens > 0:
                        dry_run = process_batch_dry_run(
                            template,
                            rows,
                            batch_budget_usd if batch_budget_usd > 0 else None,
                            batch_budget_tokens if batch_budget_tokens > 0 else None,
                        )

                        if dry_run["warnings"]:
                            for warning in dry_run["warnings"]:
                                st.warning(f"⚠️ {warning}")

                        if dry_run["errors"]:
                            for error in dry_run["errors"]:
                                st.error(f"❌ {error}")
                            batch_budget_error = dry_run["errors"][0]

                    # Batch action buttons
                    col_b3, col_b4 = st.columns(2)
                    dry_run_btn = col_b3.button("Dry Run (Preview Only)", disabled=bool(errors and not rows))
                    process_batch_btn = col_b4.button(
                        "Process Batch", disabled=bool(errors and not rows) or bool(batch_budget_error)
                    )

                    if dry_run_btn:
                        st.markdown("**Dry Run Results:**")
                        st.write(f"Would process {len(rows)} rows")
                        st.write(f"Estimated cost: ${batch_est['total_cost_usd']:.4f}")
                        st.write(f"Estimated tokens: {batch_est['total_tokens']:,}")
                        st.success("Dry run complete. No artifacts created.")

                    if process_batch_btn:
                        st.markdown("**Processing Batch...**")

                        batch_id = int(time.time())
                        batch_dir = Path("runs/ui/templates/batch") / str(batch_id)
                        batch_dir.mkdir(parents=True, exist_ok=True)

                        successful = 0
                        failed = 0
                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        for i, row in enumerate(rows):
                            try:
                                rendered = render_template(template, row)

                                # Create preview artifact (no DJP in batch mode)
                                artifact = {
                                    "template": {
                                        "name": template.name,
                                        "version": template.version,
                                        "key": template.key,
                                        "context": template.context,
                                    },
                                    "inputs": row,
                                    "provenance": {
                                        "template_body": rendered,
                                        "resolved_inputs": row,
                                        "timestamp": int(time.time()),
                                        "batch_id": batch_id,
                                        "batch_index": i,
                                    },
                                    "rendered_output": rendered,
                                }

                                artifact_file = batch_dir / f"{batch_id}-{to_slug(template.key)}-row{i:03d}.json"
                                artifact_file.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

                                successful += 1
                            except Exception as e:
                                failed += 1
                                st.error(f"Row {i+1} failed: {e}")

                            progress_bar.progress((i + 1) / len(rows))
                            status_text.text(f"Processed {i+1}/{len(rows)} rows...")

                        st.success(f"Batch complete: {successful} successful, {failed} failed")
                        st.info(f"Artifacts saved to: {batch_dir}")

            finally:
                # Clean up temp file
                Path(csv_path).unlink()
