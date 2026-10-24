"""Stage 5 source-freeze tests (source only; no real video/render or independent Windows acceptance)."""
from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import release_manifest as rel


class Stage5ReleaseManifestTests(unittest.TestCase):
    def test_release_metadata_cannot_claim_ga(self):
        report = rel.create_manifest(ROOT)
        self.assertEqual(report["version"], "1.0.0-rc.2")
        self.assertEqual(report["release_status"], "RELEASE_CANDIDATE_NOT_GA")
        self.assertEqual(report["windows_independent_acceptance"], "NOT_RUN_USER_RESPONSIBILITY")
        self.assertFalse(report["automatic_publication"])
        self.assertNotIn(rel.MANIFEST_NAME, {x["path"] for x in report["files"]})

    def test_deterministic_source_inventory(self):
        a = rel.create_manifest(ROOT)
        b = rel.create_manifest(ROOT)
        self.assertEqual(a, b)
        self.assertEqual(a["total_files"], len(a["files"]))
        self.assertEqual(a["total_bytes"], sum(row["bytes"] for row in a["files"]))
        self.assertEqual(len(a["content_set_sha256"]), 64)

    def test_case_insensitive_windows_manifest_paths(self):
        items = rel.scan(ROOT)
        paths = [item["path"].casefold() for item in items]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(all("\\" not in item["path"] for item in items))

    def test_readonly_scan_rejects_runtime_and_secret_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text("safe", encoding="utf-8")
            self.assertEqual(rel.scan(root)[0]["path"], "SKILL.md")
            for filename in ("video.mp4", ".env", "credential.pfx", "agent.log", "data.sqlite", "unexpected.bin"):
                p = root / filename
                p.write_bytes(b"fixture")
                with self.subTest(filename=filename):
                    with self.assertRaises(ValueError):
                        rel.scan(root)
                p.unlink()
            (root / "node_modules").mkdir()
            with self.assertRaises(ValueError):
                rel.scan(root)

    def test_rejects_hidden_and_unsafe_windows_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text(".venv/\n", encoding="utf-8")
            self.assertEqual(len(rel.scan(root)), 1)
            path = root / ".unexpected"
            path.write_text("hidden", encoding="utf-8")
            with self.assertRaises(ValueError):
                rel.scan(root)
            path.unlink()
            # Windows disallows reserved filenames natively; inspect the regexp rather than writing.
            self.assertTrue(rel.WINDOWS_RESERVED.fullmatch("CON.txt"))

    def test_create_verify_tamper_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "release"
            shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns(rel.MANIFEST_NAME))
            saved = rel.save(dest)
            self.assertEqual(saved["status"], "MANIFEST_CREATED")
            good = rel.verify(dest)
            self.assertEqual(good["status"], "RELEASE_MANIFEST_PASS")
            self.assertEqual(saved["manifest_sha256"], good["manifest_sha256"])
            with self.assertRaises(FileExistsError):
                rel.save(dest)
            readme = dest / "README.md"
            readme.write_bytes(readme.read_bytes() + b"\n# Changed after signing\n")
            with self.assertRaisesRegex(ValueError, "content mismatch"):
                rel.verify(dest)

    def test_modified_manifest_status_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "release"
            shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns(rel.MANIFEST_NAME))
            rel.save(dest)
            mf = dest / rel.MANIFEST_NAME
            row = json.loads(mf.read_text(encoding="utf-8"))
            row["release_status"] = "GENERAL_AVAILABILITY"
            mf.write_text(json.dumps(row), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "content mismatch"):
                rel.verify(dest)

    def test_symlink_is_rejected_where_host_permits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file = root / "file.md"
            file.write_text("fixture", encoding="utf-8")
            link = root / "alias.md"
            try:
                link.symlink_to(file)
            except (OSError, NotImplementedError):
                self.skipTest("Windows permissions do not permit symlink fixtures")
            with self.assertRaisesRegex(ValueError, "Symlink"):
                rel.scan(root)


if __name__ == "__main__":
    unittest.main()
