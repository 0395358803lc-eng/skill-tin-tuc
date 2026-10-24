#!/usr/bin/env python3
"""Source-auditable news evidence validation. Never treats domain-counting as fact-checking."""
from __future__ import annotations
import datetime as dt
import hashlib
import studio_design
import editorial_quality
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_CATEGORIES = {'general', 'politics', 'economy', 'technology',
                      'science', 'entertainment', 'sports', 'environment', 'health'}
ALLOWED_CONFIDENCE = {'high', 'medium', 'low', 'unknown'}
TWO_LABEL_SUFFIXES = {'co.uk', 'org.uk', 'ac.uk', 'com.au', 'com.br', 'co.jp', 'com.vn',
                      'co.kr', 'com.cn', 'com.mx', 'co.nz', 'com.sg', 'com.my'}
HIGH_RISK = {'politics', 'health', 'economy'}
MAX_VISUAL_SCENES = 20
def timestamp(value: str, name: str) -> dt.datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + ' must be nonempty ISO-8601 datetime')
    result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError(name + ' requires timezone')
    return result.astimezone(dt.timezone.utc)

def host(url: str) -> str:
    if not isinstance(url, str):
        raise ValueError('source URL must be a string')
    obj = urlparse(url)
    if obj.scheme != 'https' or not obj.hostname or obj.username or obj.password:
        raise ValueError('source URL must be public HTTPS')
    name = obj.hostname.lower().removeprefix('www.')
    if name == 'localhost' or name.endswith('.localhost') or name.endswith('.local'):
        raise ValueError('source URL must not be local')
    # The two-level eTLD fallback is deliberately conservative; independence
    # also requires publisher and provenance review, not just different hosts.
    return name

def organization_domain(url: str) -> str:
    h = host(url)
    parts = h.split('.')
    if len(parts) < 2:
        return h
    suffix = '.'.join(parts[-2:])
    if suffix in TWO_LABEL_SUFFIXES and len(parts) >= 3:
        return '.'.join(parts[-3:])
    return suffix

def text(value: object) -> str:
    return ' '.join(value.split()) if isinstance(value, str) else ''

def source_key(src: dict) -> str:
    return text(src.get('origin_id', '')).casefold() or organization_domain(src['url'])

def evidence_check(story: dict) -> dict:
    errors, warnings = [], []
    sid = story.get('id')
    if not isinstance(sid, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{1,63}', sid):
        errors.append('story.id invalid')
    if not text(story.get('headline')):
        errors.append('story headline missing')
    if not text(story.get('summary')):
        errors.append('story summary missing')
    if story.get('category') not in ALLOWED_CATEGORIES:
        errors.append('unsupported category')
    if not text(story.get('event_country')):
        errors.append('event_country missing; RSS market is not the event location')
    try:
        timestamp(story.get('event_at'), 'event_at')
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
    confidence = story.get('confidence', 'unknown')
    if confidence not in ALLOWED_CONFIDENCE:
        errors.append('confidence invalid')
    if confidence == 'high' and not text(story.get('confidence_rationale')):
        errors.append('high confidence must explain why')
    if story.get('contradictions_unresolved'):
        errors.append('unresolved contradictions: must not become verified news')
    for score_name in ('impact_score', 'video_fit_score'):
        score = story.get(score_name)
        if score is not None and (type(score) not in (int, float) or not 0 <= score <= 5):
            errors.append(score_name + ' must be editorial estimate 0..5')
    sources = story.get('sources')
    if not isinstance(sources, list) or not sources:
        sources = []
        errors.append('missing source records')
    ids = set()
    checked = []
    for n, obj in enumerate(sources):
        if not isinstance(obj, dict):
            errors.append(f'source[{n}] not object')
            continue
        scid = obj.get('id')
        if not isinstance(scid, str) or not scid.strip() or scid in ids:
            errors.append(f'source[{n}] missing/duplicate id')
            continue
        ids.add(scid)
        try:
            domain = organization_domain(obj.get('url'))
            timestamp(obj.get('published_at'), 'published_at')
            timestamp(obj.get('retrieved_at'), 'retrieved_at')
        except (ValueError, TypeError) as exc:
            errors.append(f'source[{n}] {exc}')
            continue
        if not text(obj.get('publisher')) or not text(obj.get('evidence_note')):
            errors.append(f'source[{n}] needs publisher and direct evidence_note')
        if obj.get('read_confirmed') is not True:
            warnings.append(f'source[{n}] not marked full-text reviewed')
            continue
        if obj.get('syndicated_copy') is True:
            warnings.append(f'source[{n}] syndicated copy does not add independence')
            continue
        checked.append({'id': scid, 'domain': domain, 'origin': source_key(obj),
                        'publisher': text(obj.get('publisher')).casefold(),
                        'url': obj.get('url')})
    claims = story.get('claims')
    if not isinstance(claims, list) or len(claims) == 0:
        claims = []
        errors.append('explicit claim ledger required')
    seen_claim_ids = set()
    supported = []
    for i, claim in enumerate(claims):
        if not isinstance(claim, dict):
            errors.append(f'claim[{i}] not object')
            continue
        claim_id = claim.get('id')
        if not isinstance(claim_id, str) or not claim_id or claim_id in seen_claim_ids:
            errors.append(f'claim[{i}] missing/duplicate id')
            continue
        seen_claim_ids.add(claim_id)
        if not text(claim.get('text')):
            errors.append(f'claim[{i}] missing text')
        cites = claim.get('source_ids', [])
        if not isinstance(cites, list) or not cites or any(not isinstance(c, str) or c not in ids for c in cites):
            errors.append(f'claim[{i}] invalid source_ids')
        independent = {c['origin'] for c in checked if c['id'] in cites}
        independent_publishers = {c['publisher'] for c in checked if c['id'] in cites}
        supported.append({'id': claim_id, 'independent_origins': len(independent),
                          'independent_publishers': len(independent_publishers)})
        if not independent:
            errors.append(f'claim[{i}] has no full-text-reviewed independent source')
        elif confidence == 'high' and (len(independent) < 2 or len(independent_publishers) < 2):
            errors.append(f'claim[{i}] high confidence needs two independent reviewed origins')
    independent_orgs = {c['origin'] for c in checked}
    independent_publishers = {c['publisher'] for c in checked}
    independent_domains = {c['domain'] for c in checked}
    if len(independent_orgs) < 2 or len(independent_publishers) < 2 or len(independent_domains) < 2:
        errors.append('minimum two independent, independently reviewed organizations required')
    if story.get('category') in HIGH_RISK and not any(x.get('source_type') == 'primary'
                                                       for x in sources if isinstance(x, dict) and x.get('read_confirmed') is True):
        warnings.append('sensitive subject: primary source strongly recommended')
    if confidence in ('low', 'unknown'):
        errors.append('low/unknown confidence is not eligible for selection as verified reporting')
    if warnings and confidence == 'high':
        warnings.append('review warnings before asserting high confidence')
    return {'id': sid, 'eligible_for_human_editorial_review': not errors,
            'factually_verified_by_software': False,
            'independent_origins': len(independent_orgs),
            'independent_domains': len(independent_domains),
            'source_count': len(sources), 'reviewed_source_count': len(checked),
            'claims': supported, 'errors': errors, 'warnings': warnings}

def rank_evidence(bundle: dict, results: list[dict]) -> list[dict]:
    """Editorial priority heuristic, NEVER proof of claim accuracy or traffic potential."""
    as_of = timestamp(bundle['as_of'], 'as_of')
    valid = {x['id']: x for x in results if x['eligible_for_human_editorial_review']}
    category_counts = {}
    for s in bundle['stories']:
        if isinstance(s, dict) and s.get('id') in valid:
            key = s.get('category', 'general')
            category_counts[key] = category_counts.get(key, 0) + 1
    out = []
    for s in bundle['stories']:
        if not isinstance(s, dict) or s.get('id') not in valid:
            continue
        ev = valid[s['id']]
        age = max(0.0, (as_of - timestamp(s['event_at'], 'event_at')).total_seconds() / 3600)
        evidence = min(1., ev['independent_origins'] / 3.) * (1. if s.get('confidence') == 'high' else .7)
        impact = float(s.get('impact_score', 0) or 0)
        fit = float(s.get('video_fit_score', 0) or 0)
        if not 0 <= impact <= 5 or not 0 <= fit <= 5:
            raise ValueError('impact_score/video_fit_score must be in 0..5')
        freshness = max(0., 1. - age / 72.)
        diversity = 1. / category_counts.get(s['category'], 1)
        score = round(100 * (.30 * evidence + .25 * impact/5 + .20 * freshness
                             + .15 * fit/5 + .10 * diversity), 2)
        out.append({'id': s['id'], 'editorial_priority_score': score,
                    'impact_score_is_editor_estimate': impact,
                    'video_fit_score_is_editor_estimate': fit,
                    'method': '30% evidence, 25% impact, 20% recency, 15% short-video fit, 10% category diversity'})
    return sorted(out, key=lambda x: x['editorial_priority_score'], reverse=True)


def check_bundle(bundle: dict) -> dict:
    if not isinstance(bundle, dict) or not isinstance(bundle.get('stories'), list):
        raise ValueError('bundle must contain stories list')
    as_of = bundle.get('as_of')
    timestamp(as_of, 'as_of')
    results, ids = [], set()
    for story in bundle['stories']:
        result = evidence_check(story if isinstance(story, dict) else {})
        if bundle.get('demo') is True:
            result['errors'].append('DEMO evidence cannot qualify as a real verified news event')
            result['eligible_for_human_editorial_review'] = False
        if result['id'] in ids:
            result['errors'].append('duplicate story id')
            result['eligible_for_human_editorial_review'] = False
        ids.add(result['id'])
        results.append(result)
    ranking = rank_evidence(bundle, results)
    return {'as_of': as_of, 'status': 'EVIDENCE_GATE_ONLY_NOT_AUTOMATIC_FACT_CHECK',
            'editorial_ranking': ranking, 'ranking_is_editor_estimate': True,
            'story_reports': results, 'eligible_count': sum(x['eligible_for_human_editorial_review'] for x in results),
            'story_count': len(results),
            'warning': 'Human/AI must read full articles, reconcile facts, and approve sources. Software cannot independently verify truth.'}

def story_index(bundle: dict) -> dict:
    return {x['id']: x for x in bundle['stories'] if isinstance(x, dict) and 'id' in x}

def choose(bundle: dict, report: dict, ids: list[str], user_message: str, confirmed_at: str) -> dict:
    if bundle.get('demo') is True:
        raise ValueError('DEMO cannot enter the real news selection gate')
    timestamp(confirmed_at, 'confirmed_at')
    if not text(user_message) or not ids or len(ids) != len(set(ids)):
        raise ValueError('user-selected IDs and explicit user message required')
    stories, reports = story_index(bundle), {x['id']: x for x in report['story_reports']}
    selected = []
    for sid in ids:
        if sid not in stories or sid not in reports or not reports[sid]['eligible_for_human_editorial_review']:
            raise ValueError('not eligible/unknown story id: ' + sid)
        selected.append(sid)
    return {'status': 'SELECTED_AWAITING_SCRIPT_APPROVAL', 'story_ids': selected,
            'user_selection_message': user_message, 'selected_at': confirmed_at,
            'as_of': bundle['as_of']}

def draft_manifest(bundle: dict, selection: dict, scripts: dict) -> dict:
    if bundle.get('demo') is True:
        raise ValueError('DEMO cannot become a production script')
    if selection.get('status') != 'SELECTED_AWAITING_SCRIPT_APPROVAL':
        raise ValueError('selection gate missing')
    if selection.get('as_of') != bundle.get('as_of'):
        raise ValueError('stale selection against changed evidence bundle')
    entries = story_index(bundle)
    supplied = {s.get('id'): s for s in scripts.get('stories', []) if isinstance(s, dict)}
    chosen = selection['story_ids']
    if set(chosen) != set(supplied):
        raise ValueError('script IDs must exactly match chosen stories')
    if scripts.get('country') is None or scripts.get('category') is None:
        raise ValueError('script country/category missing')
    if scripts.get('target_seconds') not in (30, 60, 90, 180):
        raise ValueError('target_seconds must be 30/60/90/180')
    if scripts.get('language') not in ('vi-VN', 'en-US', 'en-GB'):
        raise ValueError('unsupported narration language')
    if scripts.get('aspect_ratio') not in ('9:16', '16:9', 'both'):
        raise ValueError('aspect_ratio must be 9:16, 16:9, or both')
    prepared = []
    for sid in chosen:
        sc = supplied[sid]
        base = entries[sid]
        if not all(text(sc.get(k)) for k in ('headline', 'summary', 'narration')):
            raise ValueError('story script incomplete: ' + sid)
        if len(sc['narration']) > 4000:
            raise ValueError('narration exceeds limit: ' + sid)
        evidence_claims = {c['id'] for c in base['claims']}
        used = sc.get('claim_ids', [])
        if not isinstance(used, list) or not used or any(x not in evidence_claims for x in used):
            raise ValueError('script needs mapped evidenced claim_ids: ' + sid)
        visual_plan = sc.get('visual_plan') or [{
            'type': 'news_card', 'instruction': 'Original news card; do not invent documentary footage',
            'claim_ids': used, 'media_status': 'original_graphics'
        }]
        if not isinstance(visual_plan, list) or not 1 <= len(visual_plan) <= MAX_VISUAL_SCENES:
            raise ValueError(f'visual_plan must have 1..{MAX_VISUAL_SCENES} scenes: ' + sid)
        for scene in visual_plan:
            if not isinstance(scene, dict) or scene.get('type') not in (
                'news_card', 'licensed_image', 'licensed_broll', 'infographic'):
                raise ValueError('invalid visual_plan scene type: ' + sid)
            if not text(scene.get('instruction')):
                raise ValueError('visual_plan instruction required: ' + sid)
            if scene.get('type') in ('licensed_image', 'licensed_broll') and not text(scene.get('license_evidence')):
                raise ValueError('licensed media requires rights evidence: ' + sid)
            if scene.get('type') in ('licensed_image', 'licensed_broll') and not text(scene.get('media_path')):
                raise ValueError('licensed media requires approved local media_path: ' + sid)
            if scene.get('type') in ('licensed_image', 'licensed_broll') and not re.fullmatch(r'[0-9a-fA-F]{64}', str(scene.get('media_sha256',''))):
                raise ValueError('licensed media requires SHA-256 content fingerprint: ' + sid)
            refs = scene.get('claim_ids', [])
            if not isinstance(refs, list) or not refs or any(x not in evidence_claims for x in refs):
                raise ValueError('visual_plan claim_ids invalid: ' + sid)
        prepared.append({'id': sid, 'headline': sc['headline'],
                         'summary': sc['summary'], 'narration': sc['narration'],
                         'claim_ids': used, 'visual_plan': visual_plan, 'approved': False,
                         'sources': [{'title': s['publisher'], 'url': s['url'],
                                      'published_at': s['published_at']} for s in base['sources']
                                     if s.get('read_confirmed') is True and s.get('syndicated_copy') is not True]})
    manifest={'project_name': text(scripts.get('project_name')) or 'ai-news-episode',
            'visual_style':scripts.get('visual_style','roundup'),
            'country': scripts['country'], 'category': scripts['category'],
            'language': scripts['language'], 'period': scripts.get('period', 'last_24h'),
            'aspect_ratio': scripts['aspect_ratio'], 'target_seconds': scripts['target_seconds'],
            'as_of': bundle['as_of'], 'status': 'draft',
            'video_title': scripts.get('video_title', ''), 'video_description': scripts.get('video_description', ''),
            'hashtags': scripts.get('hashtags', []),
            'stories': prepared,
            'user_selection_message': selection['user_selection_message'],
            'editorial_review_required': True}
    # Local audio assets are bound to the exact user-approved draft fingerprint.
    for prefix in ('music', 'pronunciation_lexicon'):
        path_key, hash_key = prefix + '_path', prefix + '_sha256'
        path_value, sha_value = scripts.get(path_key), scripts.get(hash_key)
        if path_value is not None or sha_value is not None:
            if (not isinstance(path_value, str) or not path_value.strip()
                    or not isinstance(sha_value, str)
                    or not re.fullmatch(r'[0-9a-fA-F]{64}', sha_value)):
                raise ValueError(prefix + ' needs a relative path and SHA-256 before approval')
            asset = Path(path_value)
            if asset.is_absolute() or '..' in asset.parts or asset == Path('.'):
                raise ValueError(prefix + ' must use a safe relative file path')
            if prefix == 'pronunciation_lexicon' and asset.suffix.lower() != '.json':
                raise ValueError('pronunciation lexicon must be JSON')
            manifest[path_key] = path_value
            manifest[hash_key] = sha_value.lower()
    if 'music_path' in manifest:
        if not text(scripts.get('music_license')):
            raise ValueError('background music requires explicit license evidence')
        manifest['music_license'] = scripts['music_license']
    elif scripts.get('music_license'):
        raise ValueError('music_license without approved music file')
    manifest['editorial_quality'] = editorial_quality.review(manifest)
    studio_design.validate(manifest) # Preset is included in the user's SHA256 approved script.
    return manifest

def canonical_hash(doc: dict) -> str:
    return hashlib.sha256(json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()

def approve_draft(draft: dict, confirmation: dict) -> dict:
    if draft.get('status') != 'draft' or draft.get('demo'):
        raise ValueError('only real draft can be approved')
    if not isinstance(confirmation, dict):
        raise ValueError('explicit approval artifact required')
    timestamp(confirmation.get('confirmed_at'), 'confirmed_at')
    if not text(confirmation.get('user_confirmation')):
        raise ValueError('human approval message required')
    if text(confirmation.get('user_confirmation')) == text(draft.get('user_selection_message')):
        raise ValueError('script approval must be a distinct user decision from story selection')
    if confirmation.get('script_sha256') != canonical_hash(draft):
        raise ValueError('script changed since review; approval no longer valid')
    story_ids = [s['id'] for s in draft['stories']]
    if confirmation.get('approved_story_ids') != story_ids:
        raise ValueError('approval must match exact story order')
    result = json.loads(json.dumps(draft, ensure_ascii=False))
    result['status'] = 'approved'
    result['stories'] = [dict(s, approved=True) for s in result['stories']]
    result['approval_record'] = {'confirmed_at': confirmation['confirmed_at'],
                                 'user_confirmation': confirmation['user_confirmation'],
                                 'approved_script_sha256': confirmation['script_sha256']}
    return result

def write_new(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
