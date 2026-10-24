#!/usr/bin/env python3
"""Read-only acceptance gates for Stages 16–17. No approvals or publication."""
import argparse, ast, datetime as dt, json, os, re, subprocess, sys
from pathlib import Path
import editorial_core as core
import job_integrity as safe
import research_enrichment as research

SKILL=Path(__file__).resolve().parents[1]
RUNTIME=Path(os.environ.get('NEWS_SKILL_RUNTIME',str(SKILL.parent/(SKILL.name+'-runtime'))))
BACKUP=SKILL.parent/'skill-tintuc-backups'/'stage16-17-prechange-20261024-1043'
JOB=RUNTIME/'stage16-17-validation-20261024'/'jobs'/'research-test-20261024-02'
OLD=RUNTIME/'jobs'/'stage5-evidence72-20261024'
DELIVERY=RUNTIME/'deliveries'/'Tin-Cong-Nghe-My-20261024-60s'

def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def check(out:Path)->dict:
    if out.exists():raise ValueError('acceptance report already exists')
    manifest=load(BACKUP/'backup_manifest.json')
    assert len(manifest)>=35
    for item in manifest:
        p=(BACKUP/item['relative']).resolve()
        assert p.is_relative_to(BACKUP.resolve()) and safe.sha256(p).lower()==item['sha256'].lower()
    files=list((SKILL/'scripts').glob('*.py'))+list((SKILL/'tests').glob('*.py'))
    for file in files:ast.parse(file.read_text(encoding='utf-8'))
    tests=subprocess.run([sys.executable,'-B','-m','unittest','discover',
        '-s',str(SKILL/'tests'),'-q'],capture_output=True,text=True,timeout=120,
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    if tests.returncode:raise ValueError('unit test failure: '+tests.stderr[-900:])
    total=int(re.search(r'Ran (\d+) tests',tests.stderr+tests.stdout).group(1))
    if total<115:raise ValueError('insufficient tests')
    data=load(JOB/'candidates.json')
    scr=load(JOB/'research_screening.json')
    queue=load(JOB/'queue.json')
    feeds=[x['feed'] for x in data['feed_results'] if x['status']=='OK']
    assert len(feeds)>=3 and not any('NPR' in x for x in feeds)
    assert 5<=len(queue['stories'])<=12 and 5<=scr['shortlist_count']<=12
    assert scr['eligibility_for_factual_publication'] is False
    assert safe.verify_checkpoint(JOB)['status']=='VERIFIED'
    assert safe.inspect_lock(JOB)['status']=='UNLOCKED'
    assert not (JOB/'selection.json').exists() and not (JOB/'approved.json').exists()
    assert safe.verify_checkpoint(OLD)['status']=='LEGACY_NO_CHECKPOINTS'
    old_hash='c616ce6e38dceaf1af0fb364205f9f25efb71813bf88efdc7e7944fe97383d2b'
    assert safe.sha256(OLD/'approved.json')==old_hash
    b=load(OLD/'evidence.json')
    audit=research.research_review(b,core.check_bundle(b),72)
    assert audit['eligible_count']==2
    assert all(x['provenance_audit']['claim_independence_pass'] for x in audit['all_reviews'])
    release=RUNTIME/'releases'/'AI-News-Video-Skill-v0.5.3-20261024.zip'
    assert safe.sha256(release)=='f89f9e0a232d2b317fbf59e36dd0bd8265f3b9eea00c26328dcdb17cbad2bf7e'
    delivered=load(DELIVERY/'handoff_final.json')
    assert all(safe.sha256(DELIVERY/x['filename'])==x['sha256'] for x in delivered['exports'])
    skill_files=[x for x in SKILL.rglob('*') if x.is_file()]
    assert not any(x.suffix.lower() in ('.mp4','.wav','.zip','.pyc','.onnx') for x in skill_files)
    res={'status':'TECHNICAL_ACCEPTANCE_PASS','at':dt.datetime.now(dt.timezone.utc).isoformat(),
         'unit_tests_passed':total,'python_ast_files':len(files),
         'backup_verified_files':len(manifest),'live_feeds':feeds,
         'rss_raw_candidates':data['raw_candidates'],
         'rss_capped_candidates':len(data['candidates']),
         'unverified_shortlist':scr['shortlist_count'],
         'real_previous_events_structurally_eligible':audit['eligible_count'],
         'approved_script_sha256_unchanged':old_hash,
         'delivery_files_sha256_verified':len(delivered['exports']),
         'stage16_checkpoint_verified':True,'legacy_checkpoint_not_forged':True,
         'stage17_sources_not_automatically_truth_verified':True,
         'no_user_selection_or_script_approval_fabricated':True,
         'no_auto_upload':True,'source_files_only':len(skill_files),
         'limitations':['Crash scenarios are simulated, not a physical power-loss test.',
           'Original article reading and actual ownership checks still require human/agent editorial work.',
           'Portability has not been re-tested on a second computer.']}
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return res

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args()
    print(json.dumps(check(a.out),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
