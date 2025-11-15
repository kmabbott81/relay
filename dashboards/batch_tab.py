from __future__ import annotations

import glob
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from relay_ai.batch import corpus_hash, load_tasks_from_path, run_batch

# Corpus cache: avoid reloading same corpus across tasks
_CORPUS_CACHE: dict[str, Any] = {}


async def _run_once(task_text: str, corpus_paths: list[str] | None, cfg: dict[str, Any]) -> dict[str, Any]:
    """
    Try REAL path first (debate+judge+select); fallback to MOCK select() if imports/keys missing.
    Returns dict with keys: status, provider, text, reason, usage (list), redaction_metadata.
    """
    grounded = bool(corpus_paths)
    try:
        from relay_ai.corpus import load_corpus
        from relay_ai.debate import run_debate
        from relay_ai.judge import judge_drafts
        from relay_ai.publish import select_publish_text

        # Use corpus cache to avoid reloading
        cor_hash = corpus_hash(corpus_paths)
        corpus_docs = _CORPUS_CACHE.get(cor_hash)
        if grounded and corpus_docs is None:
            corpus_docs = load_corpus(corpus_paths)
            _CORPUS_CACHE[cor_hash] = corpus_docs
        drafts = run_debate(
            task=task_text,
            max_tokens=int(cfg.get("max_tokens", 1000)),
            temperature=float(cfg.get("temperature", 0.3)),
            corpus_docs=corpus_docs,
            allowed_models=sum(
                [(cfg.get("allowed_models") or {}).get(p, []) for p in ("openai", "anthropic", "google")], []
            ),
        )
        if hasattr(drafts, "__await__"):
            import asyncio

            drafts = asyncio.get_event_loop().run_until_complete(drafts)

        judgment = judge_drafts(
            drafts=drafts, task=task_text, require_citations=2 if grounded else 0, corpus_docs=corpus_docs
        )
        if hasattr(judgment, "__await__"):
            import asyncio

            judgment = asyncio.get_event_loop().run_until_complete(judgment)

        status, provider, text, reason, redaction = select_publish_text(judgment)

        # best-effort usage aggregation from draft/judge
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
            usage_rows = []

        return {
            "status": status,
            "provider": provider,
            "text": text,
            "reason": reason,
            "usage": usage_rows,
            "redaction_metadata": redaction,
        }
    except Exception:
        # MOCK fallback
        from relay_ai.publish import select_publish_text

        status, provider, text, reason, redaction = select_publish_text(
            {"text": task_text, "corpus_paths": corpus_paths, "grounded": grounded}
        )
        return {
            "status": status,
            "provider": provider,
            "text": text,
            "reason": reason,
            "usage": [],
            "redaction_metadata": redaction,
        }


def render_batch_tab(cfg: dict[str, Any]):
    st.subheader("Batch Runner")
    st.caption("Queue multiple tasks, enforce cost caps, and export a cost/latency report.")

    colx, coly = st.columns([2, 1])
    task_file = colx.file_uploader("Tasks file (.csv / .txt / .md)", type=["csv", "txt", "md"])
    per_run_cap = coly.number_input("Per-run cap ($)", min_value=0.0, step=0.10, value=1.00)
    per_batch_cap = coly.number_input("Per-batch cap ($)", min_value=0.0, step=0.50, value=5.00)
    concurrency = coly.slider("Concurrency", 1, 8, 3)

    grounded_batch = st.toggle("Grounded mode (batch uses uploaded corpus)", value=False)
    uploaded_batch = st.file_uploader(
        "Optional corpus files for batch (.txt/.md/.pdf)", type=["txt", "md", "pdf"], accept_multiple_files=True
    )

    st.info(f"Using policy={cfg.get('policy')}  temp={cfg.get('temperature')}  max_tokens={cfg.get('max_tokens')}")

    resume_chk = st.toggle(
        "Resume from prior results", value=True, help="Skip tasks already completed in runs/ui/batch/"
    )
    live_chk = st.toggle("Show live progress", value=True)

    run_batch_btn = st.button("Run Batch")

    if run_batch_btn:
        # Persist the tasks file for reproducibility
        tasks = []
        if task_file is not None:
            tmp_path = Path("runs/ui/batch") / f"tasks-{int(time.time())}-{task_file.name}"
            tmp_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_bytes(task_file.read())
            tasks = load_tasks_from_path(str(tmp_path))
        else:
            st.error("Please upload a tasks file.")
            return

        st.write(f"Loaded {len(tasks)} tasks.")
        # Save corpus if provided
        local_corpus: list[str] = []
        if uploaded_batch and grounded_batch:
            cdir = Path("runs/ui/batch/corpus")
            cdir.mkdir(parents=True, exist_ok=True)
            for f in uploaded_batch:
                p = cdir / f.name
                p.write_bytes(f.read())
                local_corpus.append(str(p))

        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        save_dir = "runs/ui/batch"
        prog_file = Path(save_dir) / "progress.json"

        def _runner():
            return asyncio.get_event_loop().run_until_complete(
                run_batch(
                    tasks,
                    _run_once,
                    local_corpus if grounded_batch else None,
                    cfg,
                    per_run_cap=float(per_run_cap),
                    per_batch_cap=float(per_batch_cap),
                    concurrency=int(concurrency),
                    save_dir=save_dir,
                    progress_path=str(prog_file),
                    resume=bool(resume_chk),
                )
            )

        res = None
        if live_chk:
            # Show live progress
            bar = st.progress(0.0)
            cols = st.columns(3)
            m_cost = cols[0].empty()
            m_done = cols[1].empty()
            m_eta = cols[2].empty()

            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_runner)
                while not fut.done():
                    time.sleep(0.5)
                    try:
                        data = json.loads(prog_file.read_text(encoding="utf-8"))
                        total = max(1, int(data.get("total", 1)))
                        done = int(data.get("done", 0))
                        cost = float(data.get("cost", 0.0))
                        eta_s = data.get("eta_s")
                        bar.progress(min(1.0, done / total))
                        m_cost.metric("Cost (est.)", f"${cost:.4f}")
                        m_done.metric("Completed", f"{done}/{total}")
                        m_eta.metric("ETA", f"{eta_s}s" if eta_s is not None else "—")
                    except Exception:
                        pass
                res = fut.result()
        else:
            # No live progress, just spinner
            with st.spinner("Running batch..."):
                res = _runner()

        st.success("Batch complete.")
        st.json(res["summary"])

        # Export a compact CSV of the latest batch rows
        rows = []
        for fn in sorted(glob.glob("runs/ui/batch/batch-*.json")):
            try:
                d = json.load(open(fn, encoding="utf-8"))
                rows.append(
                    {
                        "id": d.get("id"),
                        "status": d.get("status"),
                        "provider": d.get("provider"),
                        "duration_s": d.get("duration_s"),
                        "cost_est": d.get("cost_estimate"),
                        "task": (d.get("task") or "")[:140],
                    }
                )
            except Exception:
                pass
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download batch report CSV", data=csv, file_name="batch_report.csv", mime="text/csv")
        else:
            st.info("No per-run rows recorded yet.")
