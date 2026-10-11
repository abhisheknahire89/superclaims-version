"""Foundation: wire client, migrations, row-level security, audit hash chain, WORM storage, job queue."""
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from support import PACK, ROOT, DbTestCase

from aw import audit, jobs
from aw.db import Json, PgError
from aw.storage import LocalWormStore, ImmutableObjectError


def seed_min(owner, tenant="T-A"):
    with owner.connection() as c:
        c.execute("INSERT INTO tenant (tenant_id, legal_name, tenant_kind) VALUES ($1, 'Test TPA', 'TPA') ON CONFLICT DO NOTHING", tenant)


class Migrations(unittest.TestCase):
    def test_0001_is_byte_identical_to_pack_schema(self):
        self.assertEqual((ROOT / "migrations" / "0001_schema.sql").read_bytes(), (PACK / "db" / "schema.sql").read_bytes())


class WireClientAndRls(DbTestCase):
    def test_types_roundtrip(self):
        with self.db.tenant_tx("T-A") as c:
            r = c.fetch_one("SELECT $1::jsonb AS j, $2::text[] AS a, $3::date AS d, $4::numeric AS n, $5::bigint AS b, $6::boolean AS t, NULL::text AS z",
                            Json({"k": [1, "x"]}), ["a", 'q"uote', "comma,inside"], date(2026, 7, 1), Decimal("85000.00"), 17245575, True)
        self.assertEqual(r, {"j": {"k": [1, "x"]}, "a": ["a", 'q"uote', "comma,inside"], "d": date(2026, 7, 1),
                             "n": Decimal("85000.00"), "b": 17245575, "t": True, "z": None})

    def test_error_carries_sqlstate_and_constraint(self):
        seed_min(self.owner)
        with self.assertRaises(PgError) as cm:
            with self.db.tenant_tx("T-A") as c:
                c.execute("INSERT INTO hospital (tenant_id, hospital_id, name) VALUES ('T-A','H1','x')")
                c.execute("INSERT INTO hospital (tenant_id, hospital_id, name) VALUES ('T-A','H1','x')")
        self.assertEqual(cm.exception.sqlstate, "23505")
        # the failed transaction rolled back, including the first insert
        with self.db.tenant_tx("T-A") as c:
            self.assertEqual(c.fetch_val("SELECT count(*) FROM hospital"), 0)

    def test_rls_isolates_tenants_and_app_cannot_create_tenants(self):
        seed_min(self.owner, "T-A")
        seed_min(self.owner, "T-B")
        with self.db.tenant_tx("T-A") as c:
            c.execute("INSERT INTO hospital (tenant_id, hospital_id, name) VALUES ('T-A','HA','A hosp')")
        with self.db.tenant_tx("T-B") as c:
            self.assertEqual(c.fetch_val("SELECT count(*) FROM hospital"), 0)
            with self.assertRaises(PgError) as cm:   # writing another tenant's row is refused by WITH CHECK
                c.execute("INSERT INTO hospital (tenant_id, hospital_id, name) VALUES ('T-A','HX','sneaky')")
            self.assertEqual(cm.exception.sqlstate, "42501")
        with self.assertRaises(PgError):
            with self.db.tenant_tx("T-A") as c:
                c.execute("INSERT INTO tenant (tenant_id, legal_name, tenant_kind) VALUES ('T-C','x','TPA')")


class AuditChain(DbTestCase):
    def setUp(self):
        seed_min(self.owner)
        with self.owner.connection() as c:
            c.script("""
            INSERT INTO app_user VALUES ('U1','T-A','sub-u1','User One',true) ON CONFLICT DO NOTHING;
            INSERT INTO config_artifact (artifact_id, version, tenant_id, artifact_kind, status, effective_from, body, body_sha256, authored_by, approved_by)
              VALUES ('P','1','T-A','POLICY_CONFIG','DRAFT','2026-01-01','{}','x',NULL,NULL) ON CONFLICT DO NOTHING;
            INSERT INTO policy VALUES ('T-A','POL1','Prod',NULL,'2026-01-01','2026-12-31','P','1') ON CONFLICT DO NOTHING;
            INSERT INTO member VALUES ('T-A','M1','A B','A B','F','1990-01-01',NULL) ON CONFLICT DO NOTHING;
            INSERT INTO policy_member VALUES ('T-A','POL1','M1','2024-01-01',30000000,0,'[]') ON CONFLICT DO NOTHING;
            INSERT INTO claim (tenant_id, claim_id, workflow, policy_no, member_id) VALUES ('T-A','C1','IPD_REIMBURSEMENT','POL1','M1') ON CONFLICT DO NOTHING;
            """)

    def test_chain_appends_verifies_and_detects_tampering(self):
        with self.db.tenant_tx("T-A") as c:
            for i in range(3):
                audit.append(c, "T-A", "C1", "USER:U1", "REVIEWER_VIEWED_RECOMMENDATION", {"i": i})
            v = audit.verify_chain(c, "T-A", "C1")
        self.assertTrue(v["verified"])
        self.assertEqual(v["events"], 3)
        with self.assertRaises(PgError):           # append-only trigger
            with self.db.tenant_tx("T-A") as c:
                c.execute("UPDATE audit_event SET payload = '{}'::jsonb WHERE claim_id = 'C1'")
        # tamper as owner with the trigger disabled, then verification must fail
        with self.owner.connection() as c:
            c.script("ALTER TABLE audit_event DISABLE TRIGGER audit_event_append_only;"
                     "UPDATE audit_event SET payload = '{\"i\": 99}'::jsonb WHERE claim_id = 'C1' AND seq = 2;"
                     "ALTER TABLE audit_event ENABLE TRIGGER audit_event_append_only;")
        with self.db.tenant_tx("T-A") as c:
            v = audit.verify_chain(c, "T-A", "C1")
        self.assertFalse(v["verified"])
        self.assertEqual(v["broken_at_seq"], 2)

    def test_unknown_event_type_rejected(self):
        with self.db.tenant_tx("T-A") as c:
            with self.assertRaises(ValueError):
                audit.append(c, "T-A", "C1", "SYSTEM", "SOMETHING_MADE_UP", {})


class JobQueue(DbTestCase):
    def test_enqueue_is_idempotent_and_worker_runs_in_tenant_scope(self):
        seed_min(self.owner, "T-A")
        with self.db.tenant_tx("T-A") as c:
            a = jobs.enqueue(c, "T-A", "EVALUATE", "C1", "k1", {"trigger": "INITIAL"})
            b = jobs.enqueue(c, "T-A", "EVALUATE", "C1", "k1", {"trigger": "INITIAL"})
        self.assertIsNotNone(a)
        self.assertIsNone(b)
        seen = []

        def handler(conn, job):
            seen.append((job["tenant_id"], conn.fetch_val("SELECT current_setting('app.tenant_id', true)"), job["payload"]))

        w = jobs.Worker(self.worker_db, self.db, {"EVALUATE": handler})
        self.assertEqual(w.drain(), 1)
        self.assertEqual(seen, [("T-A", "T-A", {"trigger": "INITIAL"})])
        with self.db.tenant_tx("T-A") as c:
            self.assertEqual(c.fetch_val("SELECT state FROM processing_job WHERE job_id = $1", a), "SUCCEEDED")

    def test_failure_is_retried_with_backoff_and_error_code_only(self):
        seed_min(self.owner, "T-A")
        with self.db.tenant_tx("T-A") as c:
            jid = jobs.enqueue(c, "T-A", "EXTRACT", "D1", "k-fail", {})

        def boom(conn, job):
            raise ValueError("patient name Sunita leaked?")  # message must not be stored

        w = jobs.Worker(self.worker_db, self.db, {"EXTRACT": boom})
        w.run_once()
        with self.db.tenant_tx("T-A") as c:
            row = c.fetch_one("SELECT state, last_error_code, attempts, run_after > now() AS later FROM processing_job WHERE job_id = $1", jid)
        self.assertEqual(row["state"], "FAILED_RETRYABLE")
        self.assertEqual(row["last_error_code"], "ValueError")
        self.assertTrue(row["later"])


class WormStore(unittest.TestCase):
    def test_write_once(self):
        with tempfile.TemporaryDirectory() as d:
            s = LocalWormStore(Path(d))
            s.put_once("t/c/d/abc", b"one")
            s.put_once("t/c/d/abc", b"one")          # identical bytes: idempotent
            with self.assertRaises(ImmutableObjectError):
                s.put_once("t/c/d/abc", b"two")
            self.assertEqual(s.get("t/c/d/abc"), b"one")
            with self.assertRaises(ValueError):
                s.put_once("../escape", b"x")


if __name__ == "__main__":
    unittest.main()
