import asyncio
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main as api


class PipelineResilienceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        api.DB_PATH = Path(self.temp_dir.name) / "test.sqlite3"
        api.initialize_database()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_run(
        self,
        *,
        rate_limit: bool = False,
        outage: bool = False,
        crash: bool = False,
        source_mode: str = "fixtures",
        sources: list[str] | None = None,
    ) -> str:
        import uuid

        run_id = str(uuid.uuid4())
        now = api.utc_now()
        with api.connect() as conn:
            conn.execute(
                """
                INSERT INTO runs
                    (id, topic, status, created_at, updated_at,
                     inject_rate_limit, inject_outage, crash_at_stage4,
                     source_mode, source_selection_json)
                VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    "How should a resilient API handle transient failures?",
                    now,
                    now,
                    int(rate_limit),
                    int(outage),
                    int(crash),
                    source_mode,
                    json.dumps(sources if sources is not None else []),
                ),
            )
            for number, (name, _) in enumerate(api.STAGES, start=1):
                conn.execute(
                    """
                    INSERT INTO stage_checkpoints
                        (run_id, stage, name, status, attempts, resilience_policy, updated_at)
                    VALUES (?, ?, ?, 'pending', 0, ?, ?)
                    """,
                    (run_id, number, name, api.POLICIES[number - 1], now),
                )
        return run_id

    def stages(self, run_id: str) -> list[dict]:
        with api.connect() as conn:
            return [
                api.serialize_stage(row)
                for row in conn.execute(
                    "SELECT * FROM stage_checkpoints WHERE run_id = ? ORDER BY stage",
                    (run_id,),
                ).fetchall()
            ]

    def events(self, run_id: str) -> list[dict]:
        with api.connect() as conn:
            return [
                {
                    "event": row["event_type"],
                    "data": json.loads(row["data_json"]),
                }
                for row in conn.execute(
                    "SELECT event_type, data_json FROM run_events WHERE run_id = ? ORDER BY id",
                    (run_id,),
                ).fetchall()
            ]

    def test_clean_run_completes_and_signs_dossier(self) -> None:
        run_id = self.create_run()
        asyncio.run(api.run_pipeline(run_id))

        run = api.read_run_row(run_id)
        stages = self.stages(run_id)
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["completed_stages"], 6)
        self.assertTrue(run["verification_hash"])
        self.assertEqual(len(stages), 6)
        self.assertTrue(all(stage["status"] in ("completed", "fallback") for stage in stages))

    def test_rate_limit_uses_bounded_backoff_then_recovers(self) -> None:
        run_id = self.create_run(rate_limit=True)
        asyncio.run(api.run_pipeline(run_id))

        stage_two = self.stages(run_id)[1]
        retry_events = [
            event for event in self.events(run_id)
            if event["event"] == "stage_transition"
            and event["data"].get("stage") == 2
            and event["data"].get("status") == "retrying"
        ]
        self.assertEqual(stage_two["status"], "completed")
        self.assertEqual(stage_two["attempts"], 3)
        self.assertEqual(len(retry_events), 2)
        self.assertTrue(all(0 < event["data"]["backoffMs"] < 1000 for event in retry_events))

    def test_provider_outage_uses_cached_fallback(self) -> None:
        run_id = self.create_run(outage=True)
        asyncio.run(api.run_pipeline(run_id))

        stage_two = self.stages(run_id)[1]
        self.assertEqual(stage_two["status"], "fallback")
        self.assertEqual(stage_two["output"]["provider"], "demo fixtures")
        self.assertEqual(stage_two["output"]["sourceMode"], "fixtures")
        self.assertEqual(api.read_run_row(run_id)["status"], "completed")

    def test_live_evidence_provenance_and_claim_linkage_reach_dossier(self) -> None:
        run_id = self.create_run(source_mode="live", sources=["crossref"])
        record = {
            "id": "crossref-1",
            "source": "Crossref",
            "provider": "crossref",
            "type": "journal-article",
            "title": "Reliable distributed systems",
            "url": "https://doi.org/10.1234/example",
            "retrievedAt": api.utc_now(),
            "claimId": "claim-crossref-1",
            "claim": "A publication abstract excerpt.",
            "claimKind": "abstract",
        }
        with patch.dict(api.LIVE_SEARCHERS, {"crossref": lambda _topic: [record]}):
            asyncio.run(api.run_pipeline(run_id))

        detail = api.get_run_detail(run_id)
        self.assertEqual(detail["status"], "completed")
        dossier = detail["dossier"]
        self.assertEqual(dossier["sourceMode"], "live")
        self.assertEqual(dossier["sources"][0]["url"], record["url"])
        self.assertEqual(dossier["sources"][0]["title"], record["title"])
        self.assertEqual(dossier["sources"][0]["retrievedAt"], record["retrievedAt"])
        self.assertEqual(dossier["findings"][0]["claimId"], record["claimId"])
        self.assertIn(record["url"], dossier["markdown"])
        self.assertNotIn("demo fixtures", dossier["evidenceDisclosure"].lower())

    def test_live_provider_failure_fails_without_fixture_fallback(self) -> None:
        run_id = self.create_run(source_mode="live", sources=["crossref"])
        with patch.dict(api.LIVE_SEARCHERS, {"crossref": lambda _topic: (_ for _ in ()).throw(URLError("offline"))}):
            asyncio.run(api.run_pipeline(run_id))

        detail = api.get_run_detail(run_id)
        stage_two = detail["stages"][1]
        self.assertEqual(detail["status"], "failed")
        self.assertEqual(stage_two["status"], "failed")
        self.assertEqual(stage_two["output"]["sources"], [])
        self.assertEqual(stage_two["output"]["providerStatuses"][0]["status"], "failed")
        self.assertIsNone(detail["dossier"])

    def test_crash_resumes_without_losing_saved_stages(self) -> None:
        run_id = self.create_run(crash=True)
        asyncio.run(api.run_pipeline(run_id))

        paused = api.read_run_row(run_id)
        first_pass = self.stages(run_id)
        saved_outputs = [stage["output"] for stage in first_pass[:3]]
        self.assertEqual(paused["status"], "paused")
        self.assertEqual(paused["completed_stages"], 3)
        self.assertTrue(all(first_pass[index]["status"] == "completed" for index in range(3)))

        with api.connect() as conn:
            conn.execute(
                "UPDATE runs SET resume_count = resume_count + 1, status = 'queued' WHERE id = ?",
                (run_id,),
            )
        asyncio.run(api.run_pipeline(run_id))

        resumed = api.read_run_row(run_id)
        final_stages = self.stages(run_id)
        self.assertEqual(resumed["status"], "completed")
        self.assertEqual([stage["output"] for stage in final_stages[:3]], saved_outputs)
        self.assertTrue(all(stage["status"] in ("completed", "fallback") for stage in final_stages))
        resume_event = next(event for event in self.events(run_id) if event["event"] == "resume")
        self.assertEqual(resume_event["data"]["skippedStages"], [1, 2, 3])
        self.assertEqual(resume_event["data"]["skipDurationMs"], 0)


if __name__ == "__main__":
    unittest.main()
