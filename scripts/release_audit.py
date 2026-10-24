#!/usr/bin/env python3
"""Portable source audit, no mutations. Stage21 release-check gate.

This file intentionally never downloads media, invokes posting APIs, alters jobs or
uses an account secret. Inputs are a Skill directory and external report destination.
"""
from __future__ import annotations
import argparse,ast,datetime as dt,hashlib,json,re
from pathlib import Path

REQUIRED=[
 'SKILL.md','README.md','references/AGENT_RUNBOOK.md',
 'references/PORTABILITY_CONTRACT.md','references/AGENT_ORCHESTRATION.md','references/WINDOWS_BOOTSTRAP.md','references/TRANSFER_ZIP_WINDOWS.md','references/INSTALL_WINDOWS.md','references/EVIDENCE_SCHEMA.md',
 'references/STAGE20_OPERATIONS.md','scripts/bootstrap_windows.ps1',
 'scripts/workflow.py','scripts/qa_engine.py','scripts/qa_repair.py',
 'scripts/job_integrity.py','scripts/agent_bridge.py','scripts/runtime_tools.py','scripts/release_manifest.py','scripts/narration_quality.py',
 'scripts/smart_media.py','scripts/studio_design.py',
 'remotion-template/src/News.jsx','remotion-template/src/index.jsx',
 'remotion-template/package-lock.json','requirements.txt',
 'requirements-smart-crop.txt','tests/test_stage20.py','tests/test_stage2_bootstrap.py','tests/test_stage3_agent_bridge.py','tests/test_stage5_release_manifest.py'
]
FORBIDDEN_EXT={'.mp4','.mkv','.mov','.mp3','.wav','.onnx','.pyd','.exe','.pyc','.dll','.zip','.sqlite','.db'}
FORBIDDEN_DIR={'node_modules','.venv','__pycache__','_work','.git'}
SIGNATURES=(
 ('PRIVATE_KEY',re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),
 ('GITHUB_CLASSIC_TOKEN',re.compile(r'ghp_[A-Za-z0-9]{25,}')),
 ('POSSIBLE_API_SECRET',re.compile(r'''(?i)(?:api[_-]?key|client[_-]?secret|access[_-]?token|password)\s*[:=]\s*['"][A-Za-z0-9_\-]{24,}['"]'''))
)
def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def audit(root:Path)->dict:
    root=root.resolve()
    if not root.is_dir():raise ValueError('Skill source directory not found')
    files=sorted(x for x in root.rglob('*') if x.is_file())
    issues=[]
    missing=[str(x) for x in REQUIRED if not (root/x).is_file()]
    if missing:issues.append({'code':'MISSING_REQUIRED','items':missing})
    syntax=0
    totals=0
    items=[]
    for f in files:
        relative=f.relative_to(root)
        parts=set(relative.parts)
        if parts&FORBIDDEN_DIR or f.suffix.lower() in FORBIDDEN_EXT:
            issues.append({'code':'NONPORTABLE_ARTIFACT','file':relative.as_posix()})
            continue
        size=f.stat().st_size
        if size>20*1024*1024:
            issues.append({'code':'UNEXPECTED_LARGE_SOURCE','file':relative.as_posix()})
        if f.suffix.lower() in ('.py','.md','.jsx','.ps1','.json','.txt','.gitignore'):
            raw=f.read_text(encoding='utf-8-sig')
            for code,pattern in SIGNATURES:
                if pattern.search(raw):
                    issues.append({'code':code,'file':relative.as_posix()})
            if f.suffix.lower()=='.py':
                try:ast.parse(raw);syntax+=1
                except SyntaxError as e:issues.append({'code':'PYTHON_SYNTAX','file':relative.as_posix(),'line':e.lineno})
        totals+=size
        items.append({'path':relative.as_posix(),'bytes':size,'sha256':sha(f)})
    if (root/'requirements.txt').is_file():
        req=(root/'requirements.txt').read_text(encoding='utf-8')
        for item in ('Pillow','numpy','piper-tts','psutil'):
            if not re.search(r'^'+re.escape(item)+r'\s*[<>=~!]',req,re.I|re.M):
                issues.append({'code':'MISSING_PY_DEPENDENCY','package':item})
    if (root/'SKILL.md').is_file():
        skill=(root/'SKILL.md').read_text(encoding='utf-8')
        if 'tự đăng' not in skill and 'tự đăng' not in (root/'README.md').read_text(encoding='utf-8'):
            issues.append({'code':'MISSING_MANUAL_UPLOAD_NOTICE'})
    return {'schema':'STAGE21_SOURCE_AUDIT_V1',
     'checked_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
     'source_root':str(root),'source_file_count':len(files),
     'python_ast_passed':syntax,'total_source_bytes':totals,
     'all_source_hashes':items,
     'issues':issues,'status':'SOURCE_AUDIT_PASS' if not issues else 'SOURCE_AUDIT_FAIL',
     'no_publication_integration_claimed':True,
     'not_a_runtime_or_factual_verification':True}
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument('--report',type=Path,required=True)
    opt=ap.parse_args()
    if opt.report.exists():ap.error('Audit report already exists; will not overwrite')
    result=audit(opt.source)
    opt.report.parent.mkdir(parents=True,exist_ok=True)
    opt.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('all_source_hashes',)},ensure_ascii=False,indent=2))
    if result['issues']:raise SystemExit(2)
if __name__=='__main__':main()
