"""Portable source and agent handoff consistency (dependency-free)."""
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
class Stage1PortabilityTests(unittest.TestCase):
    def test_version_consistent(self):
        skill=(ROOT/'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('version: 1.0.0-rc.2',skill)
        for p in ('package.json','package-lock.json'):
            data=json.loads((ROOT/'remotion-template'/p).read_text(encoding='utf-8'))
            self.assertEqual(data['version'],'1.0.0-rc.2')
        lock=json.loads((ROOT/'remotion-template/package-lock.json').read_text(encoding='utf-8'))
        self.assertEqual(lock['packages']['']['version'],'1.0.0-rc.2')
    def test_agent_entrypoints_reference_portability_contract(self):
        self.assertTrue((ROOT/'references/PORTABILITY_CONTRACT.md').is_file())
        for name in ('SKILL.md','README.md','references/AGENT_RUNBOOK.md'):
            self.assertIn('PORTABILITY_CONTRACT.md',(ROOT/name).read_text(encoding='utf-8'))
    def test_runbook_does_not_run_development_path(self):
        s=(ROOT/'references/AGENT_RUNBOOK.md').read_text(encoding='utf-8')
        self.assertNotIn('python -B D:\\skill-tintuc\\scripts\\',s)
        self.assertIn('$env:NEWS_SKILL_RUNTIME',s)
        self.assertIn('$py',s)
    def test_release_remains_candidate(self):
        self.assertIn('CHƯA PHẢI v1.0.0 GA',(ROOT/'README.md').read_text(encoding='utf-8'))
        self.assertIn('v1.0.0-rc.2',(ROOT/'references/PORTABILITY_CONTRACT.md').read_text(encoding='utf-8'))

if __name__=='__main__': unittest.main()
