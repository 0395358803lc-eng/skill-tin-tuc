"""Release candidate source ZIP packaging tests; no Windows video/GA acceptance."""
from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import package_source as pkg
import release_manifest as rel

class Stage6PortablePackageTests(unittest.TestCase):
    def test_zip_roundtrip_and_source_immutability(self):
        with tempfile.TemporaryDirectory() as folder:
            dest=Path(folder)/"news-source.zip"
            mf_before=rel.sha256_file(ROOT/rel.MANIFEST_NAME)
            files_before={x["path"]:x["sha256"] for x in rel.create_manifest(ROOT)["files"]}
            summary=pkg.create(ROOT,dest)
            self.assertEqual(summary["status"],"RC_ZIP_VERIFIED")
            self.assertEqual(summary["release_status"],"RELEASE_CANDIDATE_NOT_GA")
            self.assertFalse(summary["windows_independent_video_acceptance"])
            self.assertFalse(summary["automatic_publication"])
            self.assertTrue(summary["windows_extraction_path_checks_passed"])
            self.assertEqual(summary["zip_entries"],len(files_before)+1)
            self.assertEqual(pkg.verify_zip(dest)["archive_sha256"],summary["archive_sha256"])
            self.assertEqual(rel.sha256_file(ROOT/rel.MANIFEST_NAME),mf_before)
            self.assertEqual({x["path"]:x["sha256"] for x in rel.create_manifest(ROOT)["files"]},files_before)
            with zipfile.ZipFile(dest) as z:
                self.assertIn(pkg.ROOT_NAME+"/.gitignore",z.namelist())
                self.assertFalse(any(p.endswith((".mp4",".wav",".onnx",".env",".sqlite")) for p in z.namelist()))
                self.assertTrue(all(s.startswith(pkg.ROOT_NAME+"/") for s in z.namelist()))

    def test_rejects_overwrite_and_zip_inside_source(self):
        with tempfile.TemporaryDirectory() as folder:
            dest=Path(folder)/"news-source.zip"
            pkg.create(ROOT,dest)
            with self.assertRaises(FileExistsError):
                pkg.create(ROOT,dest)
            with self.assertRaisesRegex(ValueError,"outside Skill"):
                pkg.create(ROOT,ROOT/"bad-source.zip")

    def test_deterministic_zip_sha256(self):
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/"a.zip";b=Path(folder)/"b.zip"
            pkg.create(ROOT,a);pkg.create(ROOT,b)
            self.assertEqual(rel.sha256_file(a),rel.sha256_file(b))

    def test_manifest_hash_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=Path(folder)/"clean.zip"
            pkg.create(ROOT,archive)
            with self.assertRaisesRegex(ValueError,"manifest does not match"):
                pkg.verify_zip(archive,"0"*64)

    def test_extra_member_and_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=Path(folder)/"clean.zip";pkg.create(ROOT,archive)
            hacked=Path(folder)/"hacked.zip"
            with zipfile.ZipFile(archive,"r") as src,zipfile.ZipFile(hacked,"w",compression=zipfile.ZIP_DEFLATED) as target:
                for entry in src.infolist():
                    target.writestr(entry,src.read(entry.filename))
                target.writestr(pkg.ROOT_NAME+"/../../escaped.txt","should never extract")
            with self.assertRaisesRegex(ValueError,"unsafe ZIP"):
                pkg.verify_zip(hacked)

    def test_no_ga_claims_and_manifest_sha_required_when_supplied(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=Path(folder)/"test.zip";pkg.create(ROOT,archive)
            with zipfile.ZipFile(archive) as z:
                row=json.loads(z.read(pkg.ROOT_NAME+"/"+rel.MANIFEST_NAME))
            self.assertEqual(row["windows_independent_acceptance"],"NOT_RUN_USER_RESPONSIBILITY")
            self.assertEqual(row["release_status"],"RELEASE_CANDIDATE_NOT_GA")
            with self.assertRaisesRegex(ValueError,"64 hex"):
                pkg.verify_zip(archive,"not-a-checksum")

if __name__=="__main__":
    unittest.main()
