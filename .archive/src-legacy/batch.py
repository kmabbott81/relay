from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .env_utils import pricing_for

# Corpus cache: avoid reloading same corpus across tasks
_CORPUS_CACHE: dict[str, Any] = {}


def load_tasks_from_path(path: str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    if p.suffix.lower() == ".csv":
        rows = []
        with p.open("r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append(
                    {"task": (r.get("task") or r.get("prompt") or "").strip(), "id": (r.get("id") or "").strip()}
                )
        return [r for r in rows if r["task"]]
    # Fallback: one task per non-empty line for .txt/.md
    lines = p.read_text(encoding="utf-8").splitlines()
    return [{"task": ln.strip(), "id": str(i + 1)} for i, ln in enumerate(lines) if ln.strip()]


def corpus_hash(paths: Iterable[str] | None) -> str:
    if not paths:
        return "none"
    h = hashlib.sha256()
    for p in sorted(paths):
        b = Path(p).read_bytes()
        h.update(hashlib.sha256(b).digest())
    return h.hexdigest()[:16]


def estimate_cost(provider: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = pricing_for(provider)
    return (prompt_tokens / 1000.0) * price.get("prompt_per_1k", 0.0) + (completion_tokens / 1000.0) * price.get(
        "completion_per_1k", 0.0
    )


async def run_batch(
    tasks: list[dict[str, Any]],
    run_once_fn: Callable[[str, list[str] | None, dict[str, Any]], Any],
    corpus_paths: list[str] | None,
    cfg: dict[str, Any],
    *,
    per_run_cap: float = 1.00,
    per_batch_cap: float = 5.00,
    concurrency: int = 3,
    save_dir: str = "runs/ui/batch",
    progress_path: str | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    Path(save_dir).mkdir(parents=True, exist_ok=True)

    # Progress file setup
    prog_file = Path(progress_path) if progress_path else Path(save_dir) / "progress.json"

    # Build completed set if resuming
    completed: set[str] = set()
    if resume:
        for fp in Path(save_dir).glob("batch-*.json"):
            try:
                d = json.loads(fp.read_text(encoding="utf-8"))
                if d.get("id"):
                    completed.add(str(d["id"]))
            except Exception:
                pass

    # Helper to generate stable task IDs
    def _tid(item: dict[str, Any]) -> str:
        tid = (item.get("id") or "").strip()
        if not tid:
            tid = hashlib.sha1((item.get("task") or "").encode("utf-8")).hexdigest()[:10]
        return tid

    # Filter tasks if resuming
    todo = [t for t in tasks if (not resume) or (_tid(t) not in completed)]

    q = asyncio.Queue()
    for t in todo:
        q.put_nowait(t)

    totals = {"cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "runs": 0}
    results = []
    cor_hash = corpus_hash(corpus_paths)

    # Progress tracking
    total = len(todo)
    start_ts = time.time()

    def _write_progress(done: int, cost: float, pt: int, ct: int):
        avg = ((time.time() - start_ts) / done) if done else None
        eta = (total - done) * avg if (avg and total) else None
        payload = {
            "total": total,
            "done": done,
            "cost": round(cost, 6),
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "eta_s": round(eta, 1) if eta else None,
            "started": start_ts,
        }
        try:
            tmp = prog_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(prog_file)
        except Exception:
            pass

    _write_progress(0, 0.0, 0, 0)

    async def worker(wid: int):
        nonlocal totals
        while not q.empty():
            item = await q.get()
            task = item.get("task", "")
            tid = item.get("id", "")
            # stop if batch cap exceeded
            if totals["cost"] >= per_batch_cap:
                q.task_done()
                continue

            attempt, last_err = 0, None
            while attempt < 3:
                try:
                    t0 = time.time()
                    result = await run_once_fn(task, corpus_paths, cfg)
                    dur = time.time() - t0
                    usage = result.get("usage", []) or []

                    # aggregate usage
                    cost_run, pt, ct = 0.0, 0, 0
                    for row in usage:
                        prov = (row.get("provider") or "").strip()
                        ptk = int(row.get("prompt_tokens", 0))
                        ctk = int(row.get("completion_tokens", 0))
                        pt += ptk
                        ct += ctk
                        if prov:
                            cost_run += estimate_cost(prov, ptk, ctk)

                    # enforce per-run cap
                    if cost_run > per_run_cap:
                        status = "blocked_cost_cap"
                        reason = f"Per-run cap ${per_run_cap:.2f} exceeded (est ${cost_run:.4f})"
                        cost_run = 0.0
                    else:
                        status = result.get("status", "unknown")
                        reason = result.get("reason", "")
                        totals["cost"] += cost_run
                        totals["prompt_tokens"] += pt
                        totals["completion_tokens"] += ct
                        totals["runs"] += 1

                    out = {
                        "id": tid,
                        "task": task,
                        "duration_s": round(dur, 3),
                        "status": status,
                        "provider": result.get("provider", ""),
                        "text": result.get("text", ""),
                        "reason": reason,
                        "usage": usage,
                        "cost_estimate": round(cost_run, 6),
                        "corpus_hash": cor_hash,
                    }
                    results.append(out)
                    # Update progress
                    _write_progress(
                        totals["runs"], totals["cost"], totals["prompt_tokens"], totals["completion_tokens"]
                    )
                    # save each result
                    Path(save_dir, f"batch-{int(time.time()*1000)}-{tid or 'x'}.json").write_text(
                        json.dumps(out, indent=2), encoding="utf-8"
                    )
                    break
                except Exception as e:
                    last_err = e
                    await asyncio.sleep(0.8 * (attempt + 1))
                    attempt += 1

            if attempt == 3 and last_err:
                results.append({"id": tid, "task": task, "error": str(last_err), "status": "failed"})

            q.task_done()

    workers = [asyncio.create_task(worker(i)) for i in range(max(1, int(concurrency)))]
    await q.join()
    for w in workers:
        w.cancel()

    # Final progress write
    _write_progress(totals["runs"], totals["cost"], totals["prompt_tokens"], totals["completion_tokens"])

    summary = {
        "totals": totals,
        "count": len(results),
        "per_run_cap": per_run_cap,
        "per_batch_cap": per_batch_cap,
        "concurrency": concurrency,
        "corpus_hash": cor_hash,
        "savedir": save_dir,
    }
    Path(save_dir, "batch-summary.json").write_text(
        json.dumps({"summary": summary, "results": results}, indent=2), encoding="utf-8"
    )
    return {"summary": summary, "results": results}
