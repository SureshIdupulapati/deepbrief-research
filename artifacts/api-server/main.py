from __future__ import annotations

import asyncio
import hashlib
import html
import json
import os
import random
import re
import sqlite3
import time
import uuid
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import FastAPI, Header, HTTPException, Path as RoutePath
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DEEPBRIEF_DB", str(ROOT / "deepbrief.sqlite3")))

STAGES = [
    ("Input Normalizer & Intent Expansion", "Validates the brief and expands it into orthogonal research vectors."),
    ("Multi-Source Harvester", "Searches selected live publication providers or loads explicitly selected demo fixtures."),
    ("Evidence Normalizer", "Preserves provider records and abstracts without inventing extracted metrics."),
    ("Claim Linkage & Caveat Review", "Links findings to source records and avoids unsupported consensus claims."),
    ("Evidence-Led Summary", "Summarizes retrieved records and states the limits of the evidence."),
    ("Artifact Builder & Cryptographic Signer", "Compiles the dossier, team card, and SHA-256 signature."),
]

POLICIES = [
    "Input validation; bounded expansion",
    "Parallel selected-provider retrieval; no fixture fallback in live mode",
    "Preserve source URL, title, retrieval time, and claim linkage",
    "Link each finding to evidence; do not infer cross-source agreement",
    "Summarize only saved evidence and disclose its limits",
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
                source_mode TEXT NOT NULL DEFAULT 'fixtures',
                source_selection_json TEXT NOT NULL DEFAULT '[]',
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
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(runs)")}
        if "source_mode" not in columns:
            conn.execute("ALTER TABLE runs ADD COLUMN source_mode TEXT NOT NULL DEFAULT 'fixtures'")
        if "source_selection_json" not in columns:
            conn.execute("ALTER TABLE runs ADD COLUMN source_selection_json TEXT NOT NULL DEFAULT '[]'")
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
    sourceMode: Literal["live", "fixtures"] = "live"
    sources: list[Literal["crossref", "arxiv"]] = Field(default_factory=lambda: ["crossref", "arxiv"], max_length=2)
    injectRateLimit: bool = False
    injectOutage: bool = False
    crashAtStage4: bool = False

    @field_validator("sources")
    @classmethod
    def unique_sources(cls, sources: list[str]) -> list[str]:
        if len(sources) != len(set(sources)):
            raise ValueError("Choose each research source only once.")
        return sources

    @model_validator(mode="after")
    def validate_source_mode(self) -> "RunInput":
        if self.sourceMode == "live" and not self.sources:
            raise ValueError("Select at least one live research source.")
        return self


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
        "sourceMode": row["source_mode"],
        "sources": decode_json(row["source_selection_json"]) or [],
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


def fixture_evidence_for(topic: str, domain: str) -> list[dict[str, Any]]:
    retrieved_at = utc_now()
    return [
        {
            "id": "fixture-standards",
            "source": "Demo fixture · standards archive",
            "provider": "fixture",
            "type": "specification",
            "title": f"Operational requirements relevant to {domain}",
            "url": "https://example.invalid/deepbrief-fixtures/standards",
            "retrievedAt": retrieved_at,
            "claimId": "fixture-claim-1",
            "claim": f"Operational limits should be defined and validated for {topic}.",
            "metric": "3 independent evidence classes",
            "confidence": 0.94,
        },
        {
            "id": "fixture-benchmark",
            "source": "Demo fixture · benchmark lab",
            "provider": "fixture",
            "type": "benchmark",
            "title": f"Controlled evaluation notes for {domain}",
            "url": "https://example.invalid/deepbrief-fixtures/benchmark",
            "retrievedAt": retrieved_at,
            "claimId": "fixture-claim-2",
            "claim": "Measure the full request path, including retries and recovery.",
            "metric": "p95 latency and recovery rate",
            "confidence": 0.87,
        },
        {
            "id": "fixture-incident",
            "source": "Demo fixture · incident archive",
            "provider": "fixture",
            "type": "post-mortem",
            "title": f"Failure analysis patterns for {domain}",
            "url": "https://example.invalid/deepbrief-fixtures/incidents",
            "retrievedAt": retrieved_at,
            "claimId": "fixture-claim-3",
            "claim": "Bounded retries and observable fallbacks reduce repeated outages.",
            "metric": "3 evidence classes",
            "confidence": 0.82,
        },
    ]


SOURCE_LABELS = {"crossref": "Crossref", "arxiv": "arXiv"}


def clean_abstract(value: str, limit: int = 1200) -> str:
    text = re.sub(r"<[^>]*>", " ", html.unescape(value))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def fetch_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "DeepBrief/1.0 (research evidence retrieval)",
        },
    )
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_xml(url: str) -> ET.Element:
    request = Request(
        url,
        headers={"User-Agent": "DeepBrief/1.0 (research evidence retrieval)"},
    )
    with urlopen(request, timeout=15) as response:
        return ET.fromstring(response.read())


def search_crossref(topic: str) -> list[dict[str, Any]]:
    params = urlencode(
        {
            "query.bibliographic": topic,
            "rows": 5,
            "select": "DOI,title,URL,published,author,abstract,container-title,type",
        }
    )
    payload = fetch_json(f"https://api.crossref.org/works?{params}")
    records = payload.get("message", {}).get("items", [])
    evidence = []
    for index, record in enumerate(records, start=1):
        titles = record.get("title") or []
        title = clean_abstract(str(titles[0])) if titles else ""
        if not title:
            continue
        abstract = clean_abstract(str(record.get("abstract") or ""))
        doi = record.get("DOI")
        source_url = record.get("URL") or (f"https://doi.org/{doi}" if doi else None)
        if not source_url:
            continue
        published = record.get("published") or record.get("published-print") or {}
        date_parts = published.get("date-parts") or []
        published_year = date_parts[0][0] if date_parts and date_parts[0] else None
        evidence.append(
            {
                "id": f"crossref-{index}",
                "source": "Crossref",
                "provider": "crossref",
                "type": str(record.get("type", "publication")),
                "title": title,
                "url": source_url,
                "retrievedAt": utc_now(),
                "claimId": f"claim-crossref-{index}",
                "claim": abstract or f"Publication record relevant to the question: {title}",
                "claimKind": "abstract" if abstract else "title metadata",
                "published": published_year,
            }
        )
    return evidence


def search_arxiv(topic: str) -> list[dict[str, Any]]:
    params = urlencode(
        {
            "search_query": f'all:"{topic}"',
            "start": 0,
            "max_results": 5,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    root = fetch_xml(f"https://export.arxiv.org/api/query?{params}")
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    evidence = []
    for index, entry in enumerate(root.findall("atom:entry", ns), start=1):
        title = clean_abstract(entry.findtext("atom:title", "", ns))
        abstract = clean_abstract(entry.findtext("atom:summary", "", ns))
        source_url = entry.findtext("atom:id", "", ns).strip()
        if not title or not source_url:
            continue
        evidence.append(
            {
                "id": f"arxiv-{index}",
                "source": "arXiv",
                "provider": "arxiv",
                "type": "preprint",
                "title": title,
                "url": source_url,
                "retrievedAt": utc_now(),
                "claimId": f"claim-arxiv-{index}",
                "claim": abstract or f"Publication record relevant to the question: {title}",
                "claimKind": "abstract" if abstract else "title metadata",
                "published": entry.findtext("atom:published", "", ns)[:10] or None,
            }
        )
    return evidence


LIVE_SEARCHERS = {"crossref": search_crossref, "arxiv": search_arxiv}


async def harvest_live(topic: str, selected_sources: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    loop = asyncio.get_running_loop()
    results = await asyncio.gather(
        *(
            loop.run_in_executor(None, LIVE_SEARCHERS[source], topic)
            for source in selected_sources
        ),
        return_exceptions=True,
    )
    evidence: list[dict[str, Any]] = []
    provider_statuses: list[dict[str, str]] = []
    for source, result in zip(selected_sources, results):
        if isinstance(result, BaseException):
            if isinstance(result, HTTPError):
                reason = f"HTTP {result.code}"
            elif isinstance(result, (TimeoutError, URLError)):
                reason = "Request timed out or could not connect"
            else:
                reason = "The provider response could not be read"
            provider_statuses.append(
                {"provider": source, "label": SOURCE_LABELS[source], "status": "failed", "message": reason}
            )
            continue
        evidence.extend(result)
        provider_statuses.append(
            {
                "provider": source,
                "label": SOURCE_LABELS[source],
                "status": "completed" if result else "no_results",
                "message": f"{len(result)} records retrieved" if result else "No matching records were returned",
            }
        )
    return evidence, provider_statuses


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
        source_mode = run["source_mode"]
        selected_sources = decode_json(run["source_selection_json"]) or []
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
            "sourceMode": source_mode,
            "selectedSources": selected_sources,
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
                if source_mode == "fixtures":
                    sources = fixture_evidence_for(topic, domain)
                    provider_statuses = [
                        {"provider": "fixture", "label": "Demo fixtures", "status": "completed", "message": "3 illustrative records loaded"}
                    ]
                    if bool(run["inject_outage"]):
                        status = "fallback"
                        message = "Simulated provider outage; explicitly selected demo fixtures remain in use."
                elif bool(run["inject_outage"]):
                    sources = []
                    provider_statuses = [
                        {"provider": provider, "label": SOURCE_LABELS[provider], "status": "failed", "message": "Simulated provider outage"}
                        for provider in selected_sources
                    ]
                    status = "failed"
                    message = "Simulated provider outage; no fixture substitution was made."
                else:
                    sources, provider_statuses = await harvest_live(topic, selected_sources)
                    if not sources:
                        status = "failed"
                        failures = "; ".join(
                            f"{provider['label']}: {provider['message']}"
                            for provider in provider_statuses
                        )
                        message = f"No live evidence was retrieved. {failures}"
                    elif any(provider["status"] != "completed" for provider in provider_statuses):
                        message = "Some selected providers did not return evidence; saved evidence is from successful providers only."
                output = {
                    "sources": sources,
                    "sourceCount": len(sources),
                    "sourceMode": source_mode,
                    "providerStatuses": provider_statuses,
                    "provider": "demo fixtures" if source_mode == "fixtures" else "selected live sources",
                    "circuitBreaker": "open → fallback → healthy" if status == "fallback" else "closed",
                }
            elif stage_number == 3:
                sources = context.get("priorOutputs", {}).get("2", {}).get("sources", [])
                output = {
                    "documentsProcessed": len(sources),
                    "claimsExtracted": sum(bool(source.get("claim")) for source in sources),
                    "normalizedEvidence": sources,
                    "note": "Source text is stored as retrieved metadata or abstract excerpts; no unsupported metric extraction is inferred.",
                }
            elif stage_number == 4:
                sources = context.get("priorOutputs", {}).get("2", {}).get("sources", [])
                output = {
                    "claimsChecked": len(sources),
                    "corroborated": [],
                    "singleSourceCaveats": [
                        {
                            "claimId": source["claimId"],
                            "message": "This record is a research lead, not independent corroboration of the claim.",
                        }
                        for source in sources
                    ],
                    "note": "No cross-source consensus is claimed because independent claim alignment is not performed.",
                }
            elif stage_number == 5:
                sources = context.get("priorOutputs", {}).get("2", {}).get("sources", [])
                output = {
                    "executiveSummary": (
                        f"Retrieved {len(sources)} research records for “{topic}”. "
                        "The cited titles and abstract excerpts are evidence leads; assess the linked publications "
                        "and verify their methods before applying them to a technical decision."
                    ),
                    "findings": [
                        {
                            "title": source["title"],
                            "detail": source["claim"],
                            "metric": f"{source['source']} · {source.get('claimKind', source['type'])}",
                            "evidenceLabel": source.get("claimKind", "Source record"),
                            "claimId": source["claimId"],
                        }
                        for source in sources
                    ],
                    "actionPlan": [
                        {"period": "Before deciding", "priority": "P1", "action": "Open each cited source and check its methods, date, and fit to the question."},
                        {"period": "For implementation", "priority": "P1", "action": "Validate relevant findings against your own workload and constraints."},
                    ],
                }
            else:
                dossier = context.get("priorOutputs", {}).get("5")
                sources = context.get("priorOutputs", {}).get("2", {}).get("sources", [])
                if not dossier:
                    dossier = {
                        "executiveSummary": (
                            f"Retrieved {len(sources)} research records for “{topic}”. "
                            "Review the linked sources and validate their methods before applying them."
                        ),
                        "findings": [
                            {
                                "title": source["title"],
                                "detail": source["claim"],
                                "metric": f"{source['source']} · {source.get('claimKind', source['type'])}",
                                "evidenceLabel": source.get("claimKind", "Source record"),
                                "claimId": source["claimId"],
                            }
                            for source in sources
                        ],
                        "actionPlan": [
                            {"period": "Before deciding", "priority": "P1", "action": "Check the methods, publication date, and fit of each linked source."},
                            {"period": "For implementation", "priority": "P1", "action": "Validate relevant findings against your own workload and constraints."},
                        ],
                    }
                else:
                    dossier = dict(dossier)
                source_mode = context.get("sourceMode", "fixtures")
                markdown = [
                    f"# DeepBrief: {topic}",
                    "",
                    "## Executive summary",
                    dossier["executiveSummary"],
                    "",
                    "## Architectural findings",
                ]
                for item in dossier["findings"]:
                    markdown.extend([f"### {item['title']}", item["detail"], f"**Signal:** {item['metric']} · **Evidence label:** {item['evidenceLabel']}", ""])
                markdown.extend(["## Immediate action plan", "| Horizon | Priority | Action |", "|---|---|---|"])
                for item in dossier["actionPlan"]:
                    markdown.append(f"| {item['period']} | {item['priority']} | {item['action']} |")
                markdown.extend(["", "## Evidence sources"])
                for source in sources:
                    markdown.append(
                        f"- **{source['source']}** — [{source['title']}]({source['url']}) "
                        f"(retrieved {source['retrievedAt']}; linked claim `{source['claimId']}`)"
                    )
                    markdown.append(f"  - {source['claim']}")
                disclosure = (
                    "This run uses explicitly selected deterministic demo fixtures. "
                    "They are illustrative and are not live research results."
                    if source_mode == "fixtures"
                    else "Live search results are publication metadata and abstract excerpts. "
                    "They are not independently verified or a substitute for reviewing the linked sources."
                )
                markdown.extend(["", f"> {disclosure}", "", "---", "Generated by DeepBrief."])
                markdown_text = "\n".join(markdown) + "\n"
                dossier["sources"] = sources
                dossier["sourceMode"] = source_mode
                dossier["providerStatuses"] = context.get("priorOutputs", {}).get("2", {}).get("providerStatuses", [])
                dossier["evidenceDisclosure"] = disclosure
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
            if stage_number == 2 and status == "failed":
                set_status(run_id, "failed")
                save_event(
                    run_id,
                    "run_failed",
                    {"runId": run_id, "message": message or "No live evidence was retrieved."},
                )
                return

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
                (id, topic, status, created_at, updated_at, inject_rate_limit, inject_outage,
                 crash_at_stage4, source_mode, source_selection_json)
            VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                body.topic.strip(),
                now,
                now,
                int(body.injectRateLimit),
                int(body.injectOutage),
                int(body.crashAtStage4),
                body.sourceMode,
                json.dumps(body.sources),
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
