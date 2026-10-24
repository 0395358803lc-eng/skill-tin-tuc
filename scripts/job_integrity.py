#!/usr/bin/env python3
"""Crash-aware local job files, checkpoint ledger and human-safe stale-lock recovery.

Only the approved job workspace is changed. No autonomous editorial decisions.
"""
from __future__ import annotations
import contextlib
import datetime as dt
import hashlib
import json
import os
import pathlib
import tempfile
import uuid

def sha256(path:pathlib.Path)->str:
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as handle:
        for part in iter(lambda:handle.read(1024*1024),b''):
            h.update(part)
    return h.hexdigest()

def utcnow()->str:
    return dt.datetime.now(dt.timezone.utc).isoformat()

def atomic_new(path:pathlib.Path,blob:bytes)->None:
    """Stage and flush before publishing a new immutable artifact; no overwrite."""
    path=pathlib.Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.pending',dir=str(path.parent))
    tmp=pathlib.Path(name)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard link creates the final name atomically only when it does not exist.
        # Same NTFS volume, so no partially-written final file is visible.
        os.link(str(tmp),str(path))
    finally:
        tmp.unlink(missing_ok=True)

def json_new(path:pathlib.Path,obj)->None:
    atomic_new(path,(json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))

def append_event(path:pathlib.Path,record:dict)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    body=(json.dumps(record,ensure_ascii=False)+'\n').encode('utf-8')
    # One writer per job is enforced by lock_job for all state-changing operations.
    with path.open('ab') as f:
        f.write(body)
        f.flush()
        os.fsync(f.fileno())

def process_identity(pid:int):
    try:
        import psutil
        p=psutil.Process(pid)
        if not p.is_running() or p.status()==psutil.STATUS_ZOMBIE:
            return None
        return round(p.create_time(),3)
    except ImportError:
        # No uncertain/stale recovery without positive evidence about process death.
        return 'unknown'
    except Exception as exc:
        if exc.__class__.__name__ == 'NoSuchProcess':
            return None
        return 'unknown'

def lock_owner(lock:pathlib.Path)->dict:
    try:
        obj=json.loads(lock.read_text(encoding='utf-8-sig'))
        if not isinstance(obj,dict):return {'invalid':True}
        return obj
    except (OSError,ValueError,TypeError):
        return {'invalid':True}

def inspect_lock(job:pathlib.Path)->dict:
    p=pathlib.Path(job)/'.stage4.lock'
    if not p.is_file():return {'status':'UNLOCKED'}
    owner=lock_owner(p)
    pid=owner.get('pid')
    if type(pid)!=int or pid<=0:return {'status':'UNKNOWN','reason':'invalid lock owner','owner':owner}
    live=process_identity(pid)
    if live is None:
        return {'status':'STALE','owner':owner,'reason':'process no longer exists'}
    if live=='unknown':return {'status':'UNKNOWN','owner':owner,'reason':'process status uncertain'}
    expected=owner.get('process_created_epoch')
    if expected is not None and abs(float(expected)-live)>2:
        return {'status':'STALE','owner':owner,'reason':'PID now belongs to another process'}
    return {'status':'ACTIVE','owner':owner,'reason':'matching process still running'}

def recover_stale_lock(job:pathlib.Path)->dict:
    """Explicit manual recovery only, never silently steal active/uncertain locks."""
    j=pathlib.Path(job)
    p=j/'.stage4.lock'
    state=inspect_lock(j)
    if state['status']!='STALE':
        raise ValueError('cannot recover active or unknown lock: '+state['status'])
    previous=p.read_bytes()
    ledger=j/'stale_lock_recovery.jsonl'
    # A failed kill cannot be guessed into being stale; verify again just before unlink.
    if inspect_lock(j)['status']!='STALE' or p.read_bytes()!=previous:
        raise ValueError('lock changed while inspecting; refuse recovery')
    record={'at':utcnow(),'reason':state['reason'],'owner':state['owner'],
            'old_lock_sha256':hashlib.sha256(previous).hexdigest(),
            'recovered_by_pid':os.getpid()}
    append_event(ledger,record)
    if p.read_bytes()!=previous:raise ValueError('lock changed during recovery')
    p.unlink()
    return {'status':'RECOVERED','recovered_lock_sha256':record['old_lock_sha256']}

@contextlib.contextmanager
def lock_job(job:pathlib.Path):
    j=pathlib.Path(job)
    p=j/'.stage4.lock'
    token=uuid.uuid4().hex
    own={'pid':os.getpid(),'created_at':utcnow(),'token':token,
         'process_created_epoch':process_identity(os.getpid())}
    try:
        with p.open('x',encoding='utf-8') as f:
            json.dump(own,f,ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
    except FileExistsError:
        raise ValueError('job locked: '+json.dumps(inspect_lock(j),ensure_ascii=False))
    try:
        yield
    finally:
        if p.is_file() and lock_owner(p).get('token')==token:
            p.unlink()

# Only human-gate documents and lightweight process metadata are hashed as checkpoints.
TRACKED=('job.json','candidates.json','queue.json','research_screening.json',
         'stage17_evidence_review.json','evidence.json','review.json',
         'selection.json','script.json','draft.json','duration_advisory.json',
         'confirmation.json','approved.json','render_result.json','technical_qa.json',
         'technical_qa_recheck.json','technical_qa_recheck_02.json',
         'delivery_pointer.json','delivery_pointer_recheck.json',
         'delivery_pointer_recheck_02.json','handoff.json','handoff_visual_revision.json')

def checkpoint(job:pathlib.Path,event_name:str,details:dict|None=None)->dict:
    j=pathlib.Path(job)
    refs={}
    for name in TRACKED:
        p=j/name
        if p.exists():
            if not p.is_file():raise ValueError('checkpoint artifact not a regular file: '+name)
            refs[name]=sha256(p)
    row={'at':utcnow(),'event':event_name,'artifacts_sha256':refs,
         'details':details or {},'human_gate':'DO_NOT_INFER_APPROVAL'}
    append_event(j/'checkpoints.jsonl',row)
    return row

def verify_checkpoint(job:pathlib.Path)->dict:
    j=pathlib.Path(job)
    ledger=j/'checkpoints.jsonl'
    if not ledger.is_file():
        return {'status':'LEGACY_NO_CHECKPOINTS','verified':False,
                'warning':'Legacy job does not carry Stage16 checkpoint ledger; inspect manually.'}
    lines=ledger.read_bytes().splitlines(keepends=True)
    if not lines:return {'status':'EMPTY_LEDGER','verified':False}
    complete=[]
    truncated=False
    for i,line in enumerate(lines):
        if not line.endswith(b'\n'):
            if i==len(lines)-1:truncated=True;break
            raise ValueError('checkpoint line is incomplete mid-ledger')
        try:complete.append(json.loads(line))
        except (ValueError,UnicodeDecodeError):
            raise ValueError('checkpoint ledger contains malformed complete entry')
    if not complete:return {'status':'NO_COMPLETE_CHECKPOINT','verified':False}
    previous=complete[-1]
    actual={}
    issues=[]
    for name,expected in previous.get('artifacts_sha256',{}).items():
        if name not in TRACKED:
            issues.append('unknown checkpoint artifact: '+name)
            continue
        p=j/name
        if not p.is_file():issues.append('missing: '+name)
        elif sha256(p)!=expected:issues.append('modified: '+name)
        else:actual[name]=expected
    # A crash between atomic commit and checkpoint append can leave a NEW artifact.
    # Treat it as pending inspection, not implicit completion nor permission to redo.
    untracked=[name for name in TRACKED if (j/name).is_file() and name not in previous.get('artifacts_sha256',{})]
    if untracked:issues.append('artifacts created since last checkpoint: '+','.join(untracked))
    return {'status':'NEEDS_MANUAL_RECOVERY' if issues or truncated else 'VERIFIED',
            'verified':not issues and not truncated,'checkpoint_event':previous.get('event'),
            'checked_artifacts':len(actual),'issues':issues,'truncated_tail':truncated,
            'human_approval_not_inferred':True,'checkpoint_count':len(complete)}

def recovery_plan(job:pathlib.Path)->dict:
    j=pathlib.Path(job)
    ck=verify_checkpoint(j)
    lock=inspect_lock(j)
    exists=lambda name:(j/name).is_file()
    attempts=sorted(x.name for x in j.glob('attempt-*') if x.is_dir())
    # A process may fail before creating attempt-01; the checkpoint still records
    # the render attempt. Never silently replay this possibly side-effectful action.
    attempt_recorded=ck.get('checkpoint_event')=='RENDER_ATTEMPT'
    interrupted=bool(not exists('render_result.json') and (attempts or attempt_recorded))
    if interrupted:stage='INTERRUPTED_RENDER_INSPECTION'
    elif exists('handoff.json'):stage='AWAITING_HUMAN_FINAL_REVIEW'
    elif exists('technical_qa.json'):stage='INSPECT_QA'
    elif exists('render_result.json'):stage='INSPECT_RENDER_THEN_QA'
    elif exists('approved.json'):stage='APPROVED_RENDER_ONLY'
    elif exists('draft.json'):stage='AWAITING_USER_SCRIPT_APPROVAL'
    elif exists('selection.json'):stage='AWAITING_AGENT_SCRIPT'
    elif exists('review.json'):stage='AWAITING_USER_SELECTION'
    elif exists('queue.json'):stage='AWAITING_AGENT_EVIDENCE'
    else:stage='DISCOVER'
    return {'job':str(j),'checkpoint':ck,'lock':lock,'suggested_stage':stage,
        'pending_render_attempt_directories':attempts if interrupted else [],
        'render_attempt_recorded_without_output':bool(attempt_recorded and not attempts and interrupted),
        'safe_to_mutate':ck['status']=='VERIFIED' and lock['status']=='UNLOCKED' and not interrupted,
        'requires_human_approval':stage=='AWAITING_USER_SCRIPT_APPROVAL',
        'never_auto_approve_or_republish':True}

def validate_jobs_root(jobs_root:pathlib.Path,skill_root:pathlib.Path)->pathlib.Path:
    """Never put mutable jobs/checkpoints/media inside the portable Skill source."""
    root=pathlib.Path(jobs_root).resolve()
    source=pathlib.Path(skill_root).resolve()
    if root==source or root.is_relative_to(source):
        raise ValueError('jobs root cannot be inside Skill source')
    return root


def assert_action_allowed(job:pathlib.Path,command:str)->dict:
    """Fail closed before any workflow mutation; no process termination or repair.

    The only special case is EXPLICIT reconcile-render, for a completed,
    interrupted attempt that will be independently validated by workflow.
    """
    plan=recovery_plan(job)
    if command=='reconcile-render':
        if (plan['checkpoint']['status']!='VERIFIED' or
            plan['lock']['status']!='UNLOCKED' or
            plan['suggested_stage']!='INTERRUPTED_RENDER_INSPECTION'):
            raise ValueError(
                'render reconciliation requires a verified checkpoint, unlocked job and interrupted render attempt'
            )
    elif not plan['safe_to_mutate']:
        raise ValueError('job recovery blocked: inspect checkpoint/lock/attempts before any mutation')
    return plan

