"""Stage 3: natural-language intake advisory, multi-session isolation, read-only safe recovery."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import agent_bridge as agent
import job_integrity as integrity


class AgentIntakeTests(unittest.TestCase):
    def test_vietnamese_intake_explicit_request(self):
        got = agent.intake("Hãy làm bản tin công nghệ Việt Nam dài 60 giây, khung 9:16, tiếng Việt")
        self.assertTrue(got["ready_for_review"], got["ambiguities_and_missing"])
        self.assertEqual(got["parameters"]["country"], "VN")
        self.assertEqual(got["parameters"]["category"], "technology")
        self.assertEqual(got["parameters"]["target_seconds"], 60)
        self.assertEqual(got["parameters"]["aspect_ratio"], "9:16")
        self.assertEqual(got["parameters"]["language"], "vi-VN")
        self.assertFalse(got["creates_job"])
        self.assertFalse(got["user_selection_received"])
        self.assertFalse(got["user_script_approval_received"])

    def test_missing_country_stops_instead_of_guessing(self):
        got = agent.intake("Tạo video tin tức khoa học hôm nay")
        self.assertFalse(got["ready_for_review"])
        self.assertTrue(any("MISSING_COUNTRY" in x for x in got["ambiguities_and_missing"]))
        self.assertIsNone(got["workflow_init_arguments"])

    def test_unsupported_120_seconds_is_not_silently_clamped(self):
        got = agent.intake("Tin khoa học Mỹ 2 phút, 16:9")
        self.assertFalse(got["ready_for_review"])
        self.assertEqual(got["parameters"]["target_seconds"], 120)
        self.assertTrue(any("UNSUPPORTED_TARGET_SECONDS" in x for x in got["ambiguities_and_missing"]))

    def test_ambiguous_country_is_blocked(self):
        got = agent.intake("Soạn tin khoa học Việt Nam và Hoa Kỳ 60 giây")
        self.assertFalse(got["ready_for_review"])
        self.assertTrue(any("AMBIGUOUS_COUNTRY" in x for x in got["ambiguities_and_missing"]))

    def test_ambiguous_duration_is_blocked(self):
        got = agent.intake("Tin Mỹ 30 giây hoặc 90 giây")
        self.assertFalse(got["ready_for_review"])
        self.assertTrue(any("AMBIGUOUS_TARGET_SECONDS" in x for x in got["ambiguities_and_missing"]))

    def test_both_aspect_when_explicit(self):
        got = agent.intake("Tin công nghệ Mỹ, cả hai tỷ lệ 9:16 và 16:9")
        self.assertTrue(got["ready_for_review"], got["ambiguities_and_missing"])
        self.assertEqual(got["parameters"]["aspect_ratio"], "both")

    def test_tiktok_aspect_suggestion_not_auto_approval(self):
        got = agent.intake("Làm tin khoa học Việt Nam để đăng TikTok bằng tiếng Việt")
        self.assertTrue(got["ready_for_review"], got["ambiguities_and_missing"])
        self.assertEqual(got["parameters"]["aspect_ratio"], "9:16")
        self.assertFalse(got["user_script_approval_received"])

    def test_uppercase_country_code_is_recognized_but_english_us_pronoun_is_not(self):
        country = agent.intake('Create US technology news 60 seconds')
        self.assertTrue(country['ready_for_review'], country['ambiguities_and_missing'])
        self.assertEqual(country['parameters']['country'], 'US')
        pronoun = agent.intake('Give us some technology news 60 seconds')
        self.assertFalse(pronoun['ready_for_review'])

    def test_english_my_does_not_mean_usa(self):
        got = agent.intake("Make my science news video in 60 seconds")
        self.assertFalse(got["ready_for_review"])
        self.assertTrue(any("MISSING_COUNTRY" in x for x in got["ambiguities_and_missing"]))

    def test_explicit_hours_days_and_defaults(self):
        got = agent.intake("Tạo tin thời sự thế giới trong 3 ngày qua, 90 giây")
        self.assertTrue(got["ready_for_review"], got["ambiguities_and_missing"])
        self.assertEqual(got["parameters"]["hours"], 72)
        self.assertEqual(got["parameters"]["target_seconds"], 90)
        self.assertIn("language", got["defaults_applied"])

    def test_empty_and_oversize_requests_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            agent.intake(" \n ")
        with self.assertRaisesRegex(ValueError, "too long"):
            agent.intake("tin " * 4000)

    def test_explicit_job_arguments_do_not_contain_raw_user_text(self):
        got = agent.intake("Bản tin công nghệ Việt Nam 60 giây bí mật ở máy của tôi")
        self.assertTrue(got["ready_for_review"], got["ambiguities_and_missing"])
        args = got["workflow_init_arguments"]
        self.assertEqual(args[args.index("--country") + 1], "VN")
        self.assertNotIn("bí mật", json.dumps(got, ensure_ascii=False))
        self.assertIn("semantic", got["advice"])


class AgentReadOnlyRecoveryTests(unittest.TestCase):
    def new_job(self, root: Path, name: str) -> Path:
        args = SimpleNamespace(jobs_root=root, job_id=name,
                               country="VN", category="technology", hours=24,
                               language="vi-VN", seconds=60, aspect="both", tone="neutral")
        job = root / name
        job.mkdir()
        integrity.json_new(job / 'job.json', {
            'schema_version': 1, 'job_id': name,
            'parameters': {'country':'VN','category':'technology', 'hours':24,
                           'language':'vi-VN','target_seconds':60,
                           'aspect_ratio':'both','tone':'neutral'},
            'human_gates':['SELECT_STORIES','APPROVE_EXACT_SCRIPT','REVIEW_BEFORE_PUBLICATION'],
            'publishing_integration': False})
        integrity.checkpoint(job, 'INIT', {})
        return job

    def test_inspect_created_job_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = self.new_job(root, "news-agent-tab01")
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            result = agent.inspect(job, root)
            after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before, after)
            self.assertEqual(result["stage"], "CREATED")
            self.assertTrue(result["safe_to_mutate"])
            self.assertEqual(result["suggested_workflow_command"], "workflow.py discover")
            self.assertFalse(result["automatic_publication"])

    def test_two_tab_jobs_never_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = self.new_job(root, "news-agent-tab01")
            b = self.new_job(root, "news-agent-tab02")
            self.assertNotEqual(a, b)
            self.assertEqual(agent.inspect(a, root)["job_id"], "news-agent-tab01")
            self.assertEqual(agent.inspect(b, root)["job_id"], "news-agent-tab02")
            catalog = agent.catalog(root)
            self.assertEqual(catalog["listed"], 2)
            self.assertEqual({x["job_id"] for x in catalog["jobs"]}, {a.name, b.name})

    def test_job_not_direct_child_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "jobs"
            root.mkdir()
            alien = self.new_job(base, "news-agent-foreign")
            with self.assertRaisesRegex(ValueError, "direct child"):
                agent.inspect(alien, root)

    def test_uncheckpointed_artifact_blocks_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = self.new_job(root, "news-agent-crash")
            (job / "queue.json").write_text('{"fixture": true}', encoding="utf-8")
            current = agent.inspect(job, root)
            self.assertTrue(current["blocked"])
            self.assertFalse(current["safe_to_mutate"])
            self.assertIsNone(current["suggested_workflow_command"])
            self.assertEqual(current["recovery"]["checkpoint"]["status"], "NEEDS_MANUAL_RECOVERY")

    def test_active_lock_blocks_next_action(self):
        import job_integrity as integrity
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = self.new_job(root, "news-agent-active")
            with integrity.lock_job(job):
                current = agent.inspect(job, root)
                self.assertTrue(current["blocked"])
                self.assertFalse(current["safe_to_mutate"])
                self.assertIsNone(current["suggested_workflow_command"])

    def test_catalog_marks_invalid_job_as_blocked_without_modifying(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "news-agent-invalid"
            folder.mkdir()
            (folder / "job.json").write_text('{"malformed": true}', encoding="utf-8")
            result = agent.catalog(root)
            self.assertEqual(result["jobs"][0]["stage"], "INVALID_OR_UNREADABLE")
            self.assertTrue(result["jobs"][0]["blocked"])

    def test_cli_intake_and_catalog_are_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = ROOT / "scripts/agent_bridge.py"
            run = subprocess.run([sys.executable, "-B", str(script), "intake",
                                  "--text", "Tin công nghệ Việt Nam 60 giây 9:16"],
                                 text=True, capture_output=True, timeout=20)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue(json.loads(run.stdout)["ready_for_review"])
            run = subprocess.run([sys.executable, "-B", str(script), "list",
                                  "--jobs-root", str(root)],
                                 text=True, capture_output=True, timeout=20)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)["total"], 0)
            self.assertEqual(list(root.iterdir()), [])


    def test_mutation_guard_rejects_broken_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = self.new_job(root, "news-agent-tampered")
            integrity.assert_action_allowed(job, "discover")
            (job / "queue.json").write_text('{"unexpected":true}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "recovery blocked"):
                integrity.assert_action_allowed(job, "discover")

    def test_mutation_guard_rejects_locked_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = self.new_job(root, "news-agent-locked")
            with integrity.lock_job(job):
                with self.assertRaisesRegex(ValueError, "recovery blocked"):
                    integrity.assert_action_allowed(job, "render")

    def test_jobs_root_cannot_be_inside_skill_source(self):
        with self.assertRaisesRegex(ValueError, 'inside Skill source'):
            integrity.validate_jobs_root(ROOT / 'jobs', ROOT)
        with self.assertRaisesRegex(ValueError, 'inside Skill source'):
            agent.catalog(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(integrity.validate_jobs_root(root, ROOT), root.resolve())

    def test_reconcile_exception_cannot_apply_to_uninterrupted_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = self.new_job(root, "news-agent-no-attempt")
            with self.assertRaisesRegex(ValueError, "interrupted render attempt"):
                integrity.assert_action_allowed(job, "reconcile-render")
            (job / "attempt-01").mkdir()
            plan = integrity.assert_action_allowed(job, "reconcile-render")
            self.assertEqual(plan["suggested_stage"], "INTERRUPTED_RENDER_INSPECTION")
            self.assertFalse(plan["safe_to_mutate"])
            # The actual workflow.reconcile_render still checks completeness, hash and QA.


if __name__ == "__main__":
    unittest.main()

