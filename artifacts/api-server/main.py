from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Header, HTTPException, Path as RoutePath
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DEEPBRIEF_DB", str(ROOT / "deepbrief.sqlite3")))

STAGES = [
    ("Input Normalizer & Intent Expansion", "Validates the brief and expands it into orthogonal research vectors."),
    ("Multi-Source Harvester", "Collects parallel evidence from standards, benchmark labs, and incident reports."),
    ("DOM Sanitizer & Content Distiller", "Removes boilerplate and extracts comparable numeric evidence."),
    ("Cross-Source Fact Corroborator", "Aligns claims, scores agreement, and marks single-source caveats."),
    ("Intelligence Synthesizer", "Builds the executive summary, architectural findings, and action plan."),
    ("Artifact Builder & Cryptographic Signer", "Compiles the dossier, team card, and SHA-256 signature."),
]

POLICIES = [
    "Input validation; bounded expansion",
    "Three retries with exponential backoff; circuit-breaker fallback",
    "Idempotent normalization checkpoint",
    "Require independent evidence; flag uncorroborated claims",
    "Synthesize only from saved evidence",
    "Deterministic Markdown build; SHA-256 integrity hash",
]

ACTIVE_RUNS: set[str] = set()
ACTIVE_LOCK = asyncio.Lock()


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                completed_stages INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER,
                inject_rate_limit INTEGER NOT NULL DEFAULT 0,
                inject_outage INTEGER NOT NULL DEFAULT 0,
                crash_at_stage4 INTEGER NOT NULL DEFAULT 0,
                resume_count INTEGER NOT NULL DEFAULT 0,
                dossier_json TEXT,
                verification_hash TEXT
            );
            CREATE TABLE IF NOT EXISTS stage_checkpoints (
                run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                stage INTEGER NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                duration_ms INTEGER,
                attempts INTEGER NOT NULL DEFAULT 0,
                output_json TEXT,
                input_context_json TEXT,
                resilience_policy TEXT NOT NULL,
                message TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (run_id, stage)
            );
            CREATE TABLE IF NOT EXISTS run_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                event_type TEXT NOT NULL,
                data_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_run_events_run_id_id
                ON run_events(run_id, id);
            """
        )
        interrupted = conn.execute(
            "SELECT id FROM runs WHERE status IN ('queued', 'running')"
        ).fetchall()
        for row in interrupted:
            run_id = row["id"]
            now = utc_now()
            conn.execute(
                "UPDATE runs SET status = 'paused', updated_at = ? WHERE id = ?",
                (now, run_id),
            )
            conn.execute(
                "INSERT INTO run_events (run_id, event_type, data_json, created_at) VALUES (?, ?, ?, ?)",
                (
                    run_id,
                    "process_recovery",
                    json.dumps(
                        {
                            "runId": run_id,
                            "message": "The worker restarted. Saved checkpoints are intact and can be resumed.",
                        }
                    ),
                    now,
                ),
            )


class RunInput(BaseModel):
    topic: str = Field(min_length=8, max_length=280)
    injectRateLimit: bool = False
    injectOutage: bool = False
    crashAtStage4: bool = False


def decode_json(value: str | None) -> Any:
    return json.loads(value) if value else None


def serialize_run(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "topic": row["topic"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "completedAt": row["completed_at"],
        "completedStages": row["completed_stages"],
        "durationMs": row["duration_ms"],
        "injectRateLimit": bool(row["inject_rate_limit"]),
        "injectOutage": bool(row["inject_outage"]),
        "crashAtStage4": bool(row["crash_at_stage4"]),
    }


def serialize_stage(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "stage": row["stage"],
        "name": row["name"],
        "status": row["status"],
        "durationMs": row["duration_ms"],
        "attempts": row["attempts"],
        "output": decode_json(row["output_json"]),
        "inputContext": decode_json(row["input_context_json"]),
        "resiliencePolicy": row["resilience_policy"],
        "message": row["message"],
    }


def get_run_detail(run_id: str) -> dict[str, Any]:
    with connect() as conn:
        run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        stages = conn.execute(
            "SELECT * FROM stage_checkpoints WHERE run_id = ? ORDER BY stage",
            (run_id,),
        ).fetchall()
    return {
        **serialize_run(run),
        "stages": [serialize_stage(stage) for stage in stages],
        "dossier": decode_json(run["dossier_json"]),
        "verificationHash": run["verification_hash"],
    }


def save_event(run_id: str, event_type: str, data: dict[str, Any]) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO run_events (run_id, event_type, data_json, created_at) VALUES (?, ?, ?, ?)",
            (run_id, event_type, json.dumps(data), now),
        )
        conn.execute("UPDATE runs SET updated_at = ? WHERE id = ?", (now, run_id))


def set_status(run_id: str, status: str, completed_at: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET status = ?, updated_at = ?, completed_at = COALESCE(?, completed_at) WHERE id = ?",
            (status, utc_now(), completed_at, run_id),
        )


def checkpoint(
    run_id: str,
    stage: int,
    status: str,
    *,
    attempts: int = 0,
    duration_ms: int | None = None,
    output: dict[str, Any] | None = None,
    input_context: dict[str, Any] | None = None,
    message: str | None = None,
) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO stage_checkpoints
                (run_id, stage, name, status, duration_ms, attempts, output_json,
                 input_context_json, resilience_policy, message, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, stage) DO UPDATE SET
                status = excluded.status,
                duration_ms = excluded.duration_ms,
                attempts = excluded.attempts,
                output_json = excluded.output_json,
                input_context_json = excluded.input_context_json,
                message = excluded.message,
                updated_at = excluded.updated_at
            """,
            (
                run_id,
                stage,
                STAGES[stage - 1][0],
                status,
                duration_ms,
                attempts,
                json.dumps(output) if output is not None else None,
                json.dumps(input_context) if input_context is not None else None,
                POLICIES[stage - 1],
                message,
                now,
            ),
        )
        if status == "completed" or status == "fallback":
            conn.execute(
                "UPDATE runs SET completed_stages = MAX(completed_stages, ?), updated_at = ? WHERE id = ?",
                (stage, now, run_id),
            )


def read_run_row(run_id: str) -> sqlite3.Row:
    with connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return row


def evidence_for(topic: str, domain: str) -> list[dict[str, Any]]:
    return [
        {
            "source": "Demo fixture · standards archive",
            "type": "specification",
            "title": f"Operational requirements relevant to {domain}",
            "claim": f"Operational limits should be defined and validated for {topic}.",
            "metric": "3 independent evidence classes",
            "confidence": 0.94,
        },
        {
            "source": "Demo fixture · benchmark lab",
            "type": "benchmark",
            "title": f"Controlled evaluation notes for {domain}",
            "claim": "Measure the full request path, including retries and recovery.",
            "metric": "p95 latency and recovery rate",
            "confidence": 0.87,
        },
        {
            "source": "Demo fixture · incident archive",
            "type": "post-mortem",
            "title": f"Failure analysis patterns for {domain}",
            "claim": "Bounded retries and observable fallbacks reduce repeated outages.",
            "metric": "3 evidence classes",
            "confidence": 0.82,
        },
    ]


def infer_domain(topic: str) -> str:
    lowered = topic.lower()
    domains = [
        (("database", "sql", "storage", "sqlite", "postgres"), "data systems"),
        (("model", "llm", "ai", "inference", "token"), "AI infrastructure"),
        (("network", "http", "api", "latency", "service"), "distributed systems"),
        (("security", "auth", "encryption", "crypto"), "security engineering"),
        (("frontend", "browser", "render", "javascript", "web"), "web engineering"),
    ]
    for keywords, domain in domains:
        if any(word in lowered for word in keywords):
            return domain
    return "systems engineering"


async def run_pipeline(run_id: str) -> None:
    start = time.perf_counter()
    try:
        run = read_run_row(run_id)
        topic = run["topic"]
        domain = infer_domain(topic)
        with connect() as conn:
            saved_stages = conn.execute(
                "SELECT * FROM stage_checkpoints WHERE run_id = ? ORDER BY stage",
                (run_id,),
            ).fetchall()
            previous = {row["stage"]: serialize_stage(row) for row in saved_stages}
        first_stage = next(
            (index for index in range(1, 7) if previous.get(index, {}).get("status") not in ("completed", "fallback")),
            7,
        )
        if first_stage > 1:
            save_event(
                run_id,
                "resume",
                {
                    "message": f"Resuming from checkpoint {first_stage}; earlier outputs are preserved.",
                    "resumedFromStage": first_stage,
                    "skippedStages": list(range(1, first_stage)),
                    "skipDurationMs": 0,
                },
            )
        set_status(run_id, "running")
        save_event(run_id, "run_started", {"runId": run_id, "resumedFromStage": first_stage})
        context: dict[str, Any] = {
            "topic": topic,
            "domain": domain,
            "priorOutputs": {
                str(stage): item["output"]
                for stage, item in previous.items()
                if item.get("output") is not None
            },
        }

        for stage_number in range(first_stage, 7):
            # Simulate a process crash after checkpointing stages 1-3. The
            # incomplete fourth stage remains pending so resume re-executes it.
            if (
                stage_number == 4
                and bool(run["crash_at_stage4"])
                and not bool(run["resume_count"])
            ):
                checkpoint(
                    run_id,
                    4,
                    "pending",
                    input_context=context,
                    message="Process stopped at the configured crash point.",
                )
                set_status(run_id, "paused")
                save_event(
                    run_id,
                    "crash_checkpoint",
                    {
                        "stage": 4,
                        "completedStages": 3,
                        "message": "Worker stopped. Stages 1–3 are safely checkpointed in SQLite.",
                    },
                )
                return

            name, description = STAGES[stage_number - 1]
            stage_started = time.perf_counter()
            checkpoint(
                run_id,
                stage_number,
                "running",
                attempts=1,
                input_context=context,
                message=description,
            )
            save_event(
                run_id,
                "stage_transition",
                {
                    "stage": stage_number,
                    "name": name,
                    "status": "running",
                    "attempts": 1,
                    "message": description,
                },
            )
            await asyncio.sleep(0.12 + random.random() * 0.08)
            status = "completed"
            attempts = 1
            message = None

            if stage_number == 1:
                output = {
                    "domain": domain,
                    "normalizedQuestion": topic.strip().rstrip("?") + "?",
                    "searchVectors": [
                        f"Standards and design constraints for {domain}",
                        f"Benchmarks and measurable outcomes for {topic}",
                        f"Operational incidents and recovery patterns for {domain}",
                        f"Trade-offs and implementation guidance for {topic}",
                    ],
                    "intent": "Compare evidence, identify trade-offs, and produce an actionable technical briefing.",
                }
            elif stage_number == 2:
                if bool(run["inject_rate_limit"]):
                    for attempt in range(1, 4):
                        attempts = attempt
                        if attempt < 3:
                            backoff_seconds = 0.12 * (2 ** (attempt - 1)) + random.uniform(0.04, 0.12)
                            checkpoint(
                                run_id,
                                2,
                                "retrying",
                                attempts=attempt,
                                input_context=context,
                                message=f"HTTP 429. Retry {attempt + 1}/3 in {backoff_seconds:.2f}s.",
                            )
                            save_event(
                                run_id,
                                "stage_transition",
                                {
                                    "stage": 2,
                                    "name": name,
                                    "status": "retrying",
                                    "attempts": attempt,
                                    "backoffMs": round(backoff_seconds * 1000),
                                    "message": f"HTTP 429 rate limit. Retry {attempt + 1}/3 after bounded backoff.",
                                },
                            )
                            await asyncio.sleep(backoff_seconds)
                    message = "Recovered after bounded exponential backoff with jitter."
                sources = evidence_for(topic, domain)
                if bool(run["inject_outage"]):
                    status = "fallback"
                    message = "Primary provider unavailable (503); circuit breaker routed to the cached archive."
                output = {
                    "sources": sources,
                    "sourceCount": len(sources),
                    "provider": "cached archive" if status == "fallback" else "parallel source pool",
                    "circuitBreaker": "open → fallback → healthy" if status == "fallback" else "closed",
                }
            elif stage_number == 3:
                sources = context.get("priorOutputs", {}).get("2", {}).get("sources", evidence_for(topic, domain))
                output = {
                    "documentsProcessed": len(sources),
                    "boilerplateRemoved": 38,
                    "numericSignals": [
                        {"metric": "source classes", "value": len(sources), "unit": "classes"},
                        {"metric": "confidence range", "value": "0.82–0.94", "unit": "score"},
                    ],
                    "normalizedEvidence": sources,
                    "semanticDensity": 0.81,
                }
            elif stage_number == 4:
                output = {
                    "claimsChecked": 3,
                    "consensusScore": 0.88,
                    "corroborated": [
                        "Operational constraints should be explicitly validated.",
                        "End-to-end p95 latency is more useful than isolated component timing.",
                    ],
                    "singleSourceCaveats": [
                        "Published benchmark values vary with workload and environment; reproduce before committing to an SLO."
                    ],
                }
            elif stage_number == 5:
                output = {
                    "executiveSummary": f"Evidence for {topic.rstrip('?')} points to a measured, failure-aware implementation: validate the operating envelope, compare complete request paths, and make recovery behavior observable.",
                    "findings": [
                        {"title": "Define the operating envelope", "detail": "Turn standards and workload assumptions into explicit acceptance criteria.", "metric": "3 evidence classes", "confidence": "High"},
                        {"title": "Benchmark the full path", "detail": "Measure p50/p95 latency, throughput, and recovery under representative load.", "metric": "p95 + recovery", "confidence": "High"},
                        {"title": "Keep recovery bounded", "detail": "Use capped retries, jitter, and a fallback that is safe to serve.", "metric": "3 attempts", "confidence": "Medium"},
                    ],
                    "actionPlan": [
                        {"period": "Days 1–7", "priority": "P1", "action": "Write a representative workload and baseline the complete request path."},
                        {"period": "30-Day", "priority": "P1", "action": "Add bounded retries, circuit-breaker thresholds, and recovery telemetry."},
                        {"period": "Quarterly", "priority": "P2", "action": "Re-run the benchmark against current dependencies and review stale assumptions."},
                    ],
                }
            else:
                dossier = context.get("priorOutputs", {}).get("5")
                if not dossier:
                    dossier = {
                        "executiveSummary": f"Evidence for {topic.rstrip('?')} supports validating the operating envelope, benchmarking the full path, and making recovery observable.",
                        "findings": [
                            {"title": "Define the operating envelope", "detail": "Document constraints and acceptance criteria from current evidence.", "metric": "3 source classes", "confidence": "High"},
                            {"title": "Benchmark the full path", "detail": "Measure end-to-end latency and recovery under representative load.", "metric": "p95 + recovery", "confidence": "High"},
                            {"title": "Make fallback behavior explicit", "detail": "Keep retries bounded and use a validated cached alternative.", "metric": "3 attempts", "confidence": "Medium"},
                        ],
                        "actionPlan": [
                            {"period": "Days 1–7", "priority": "P1", "action": "Establish the workload and current performance baseline."},
                            {"period": "30-Day", "priority": "P1", "action": "Implement bounded recovery and alert on fallback use."},
                            {"period": "Quarterly", "priority": "P2", "action": "Repeat benchmarks and revalidate operational assumptions."},
                        ],
                    }
                else:
                    dossier = dict(dossier)
                sources = context.get("priorOutputs", {}).get("2", {}).get("sources", evidence_for(topic, domain))
                markdown = [
                    f"# DeepBrief: {topic}",
                    "",
                    "## Executive summary",
                    dossier["executiveSummary"],
                    "",
                    "## Architectural findings",
                ]
                for item in dossier["findings"]:
                    markdown.extend([f"### {item['title']}", item["detail"], f"**Signal:** {item['metric']} · **Confidence:** {item['confidence']}", ""])
                markdown.extend(["## Immediate action plan", "| Horizon | Priority | Action |", "|---|---|---|"])
                for item in dossier["actionPlan"]:
                    markdown.append(f"| {item['period']} | {item['priority']} | {item['action']} |")
                markdown.extend(["", "## Evidence sources"])
                for source in sources:
                    markdown.append(f"- **{source['source']}** — {source['title']} ({source['confidence']:.0%} confidence)")
                markdown.extend(
                    [
                        "",
                        "> This challenge build uses deterministic demo fixtures; it is not live external research.",
                        "",
                        "---",
                        "Generated by DeepBrief. Evidence should be independently validated before production decisions.",
                    ]
                )
                markdown_text = "\n".join(markdown) + "\n"
                dossier["sources"] = sources
                dossier["evidenceDisclosure"] = (
                    "This challenge build uses deterministic demo source fixtures; "
                    "claims and benchmark figures are illustrative, not live external research."
                )
                dossier["markdown"] = markdown_text
                dossier["teamCard"] = {
                    "title": topic,
                    "summary": dossier["executiveSummary"],
                    "findings": [item["title"] for item in dossier["findings"]],
                    "hash": hashlib.sha256(markdown_text.encode("utf-8")).hexdigest(),
                }
                output = dossier
                digest = hashlib.sha256(markdown_text.encode("utf-8")).hexdigest()
                with connect() as conn:
                    conn.execute(
                        "UPDATE runs SET dossier_json = ?, verification_hash = ? WHERE id = ?",
                        (json.dumps(dossier), digest, run_id),
                    )

            duration_ms = max(1, round((time.perf_counter() - stage_started) * 1000))
            checkpoint(
                run_id,
                stage_number,
                status,
                attempts=attempts,
                duration_ms=duration_ms,
                output=output,
                input_context=context,
                message=message,
            )
            context["priorOutputs"][str(stage_number)] = output
            save_event(
                run_id,
                "stage_transition",
                {
                    "stage": stage_number,
                    "name": name,
                    "status": status,
                    "durationMs": duration_ms,
                    "attempts": attempts,
                    "message": message,
                    "output": output,
                    "completedStages": stage_number,
                },
            )

        total_ms = max(1, round((time.perf_counter() - start) * 1000))
        finished = utc_now()
        with connect() as conn:
            conn.execute(
                "UPDATE runs SET status = 'completed', completed_at = ?, updated_at = ?, duration_ms = ? WHERE id = ?",
                (finished, finished, total_ms, run_id),
            )
        save_event(run_id, "run_completed", {"runId": run_id, "durationMs": total_ms})
    except Exception as exc:
        set_status(run_id, "failed")
        save_event(run_id, "run_failed", {"runId": run_id, "message": str(exc)})
    finally:
        async with ACTIVE_LOCK:
            ACTIVE_RUNS.discard(run_id)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="DeepBrief API", version="1.0.0", lifespan=lifespan)


@app.get("/api/healthz")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/runs")
def list_runs() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT 50").fetchall()
    return [serialize_run(row) for row in rows]


@app.post("/api/runs", status_code=202)
async def create_run(body: RunInput) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO runs
                (id, topic, status, created_at, updated_at, inject_rate_limit, inject_outage, crash_at_stage4)
            VALUES (?, ?, 'queued', ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                body.topic.strip(),
                now,
                now,
                int(body.injectRateLimit),
                int(body.injectOutage),
                int(body.crashAtStage4),
            ),
        )
        for number, (name, _) in enumerate(STAGES, start=1):
            conn.execute(
                """
                INSERT INTO stage_checkpoints
                    (run_id, stage, name, status, attempts, resilience_policy, updated_at)
                VALUES (?, ?, ?, 'pending', 0, ?, ?)
                """,
                (run_id, number, name, POLICIES[number - 1], now),
            )
    save_event(run_id, "run_created", {"runId": run_id, "topic": body.topic.strip()})
    async with ACTIVE_LOCK:
        ACTIVE_RUNS.add(run_id)
    asyncio.create_task(run_pipeline(run_id))
    return serialize_run(read_run_row(run_id))


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    return get_run_detail(run_id)


@app.post("/api/runs/{run_id}/resume", status_code=202)
async def resume_run(run_id: str) -> dict[str, Any]:
    run = read_run_row(run_id)
    if run["status"] != "paused":
        raise HTTPException(status_code=409, detail="This run has no paused checkpoint to resume.")
    async with ACTIVE_LOCK:
        if run_id in ACTIVE_RUNS:
            raise HTTPException(status_code=409, detail="This run is already active.")
        ACTIVE_RUNS.add(run_id)
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET resume_count = resume_count + 1, status = 'queued', updated_at = ? WHERE id = ?",
            (utc_now(), run_id),
        )
    asyncio.create_task(run_pipeline(run_id))
    return serialize_run(read_run_row(run_id))


@app.get("/api/runs/{run_id}/events/{after_id}")
async def stream_run_events(
    run_id: str,
    after_id: int = RoutePath(ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    read_run_row(run_id)
    try:
        cursor = max(after_id, int(last_event_id or 0))
    except ValueError:
        cursor = 0

    async def event_stream() -> AsyncIterator[str]:
        nonlocal cursor
        while True:
            with connect() as conn:
                rows = conn.execute(
                    "SELECT id, event_type, data_json FROM run_events WHERE run_id = ? AND id > ? ORDER BY id LIMIT 100",
                    (run_id, cursor),
                ).fetchall()
                run = conn.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
            for row in rows:
                cursor = row["id"]
                yield f"id: {row['id']}\nevent: {row['event_type']}\ndata: {row['data_json']}\n\n"
            if not rows and run and run["status"] in ("completed", "failed", "paused"):
                break
            if not rows:
                yield ": keep-alive\n\n"
                await asyncio.sleep(0.25)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn

    initialize_database()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
