#!/usr/bin/env python3
"""Stage17: provenance-aware discovery and independent claim screening.
RSS discovery is NOT fact verification; human editors must read complete articles.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
import re
from collections import Counter,defaultdict
from urllib.parse import urlparse,urlunparse,parse_qsl,urlencode
import editorial_core as core
import news_rss as rss

STOPWORDS={'the','a','an','of','with','and','for','in','to','on','at','after','as','by',
           'says','said','latest','breaking','update','news','from','amid','over','its'}
TRACKING_PREFIX=('utm_','fbclid','gclid','mc_')

def canonical_url(value:str)->str:
    parsed=urlparse(value)
    if parsed.scheme not in ('http','https') or not parsed.hostname:
        raise ValueError('invalid public source URL')
    if parsed.username or parsed.password:raise ValueError('source URL credentials not allowed')
    query=urlencode(sorted((k,v) for k,v in parse_qsl(parsed.query)
            if not k.lower().startswith(TRACKING_PREFIX)))
    return urlunparse((parsed.scheme.lower(),parsed.netloc.lower(),parsed.path.rstrip('/'),
                       '',query,''))

def norm_title(value:str)->str:
    return rss.normalize(rss.main_title(value))

def tokens(value:str)->set[str]:
    return {s for s in norm_title(value).split() if (len(s)>=3 or s.isdigit()) and s not in STOPWORDS}

def title_relation(a:str,b:str)->float:
    # Do not conflate distinct numbered events (CPI 2.1% vs CPI 2.2%).
    numbers_a=set(re.findall(r'\d+(?:[.,]\d+)?%?',norm_title(a)))
    numbers_b=set(re.findall(r'\d+(?:[.,]\d+)?%?',norm_title(b)))
    if numbers_a != numbers_b:return 0.0
    ta,tb=tokens(a),tokens(b)
    if not ta or not tb:return 0.0
    return round(len(ta&tb)/max(len(ta),len(tb)),3)

def origin_hint(item:dict)->str:
    """Publisher hint is not a proven original publisher or independent reporting."""
    return re.sub(r'\s+',' ',str(item.get('source','')).casefold()).strip()

def group_rss(data:dict,limit:int=12)->dict:
    if not 5<=limit<=12:raise ValueError('shortlist limit 5..12')
    items=data.get('candidates',[])
    if not isinstance(items,list):raise ValueError('candidates should be a list')
    gathered=core.timestamp(data['collected_at'],'collected_at')
    hours=int(data.get('hours',24))
    candidates=[]
    for item in items:
        if not isinstance(item,dict):continue
        try:
            published=core.timestamp(item['published_at'],'published_at')
            url=canonical_url(item['rss_link'])
            age=(gathered-published).total_seconds()/3600
        except (ValueError,TypeError,KeyError):continue
        if not -.17<=age<=hours:continue
        related=item.get('related_articles') or [item]
        if not isinstance(related,list):continue
        links=[]
        for part in related[:30]:
            if not isinstance(part,dict):continue
            try:link=canonical_url(part['rss_link'])
            except (ValueError,KeyError):continue
            if link not in [x['url'] for x in links]:
                links.append({'url':link,'publisher_hint':part.get('source',''),
                    'headline':part.get('headline','')})
        if not links:links=[{'url':url,'publisher_hint':item.get('source',''),
                             'headline':item.get('headline','')}]
        hints={x['publisher_hint'].strip().casefold() for x in links
               if isinstance(x['publisher_hint'],str) and x['publisher_hint'].strip()}
        # Heuristic never treats distinct RSS URL counts as independent sources.
        score=round(100*(.78*max(0,1-age/hours)+.22*min(1,(len(hints)-1)/4)),2)
        candidates.append({'id':item['id'],'headline':item['headline'],
            'rss_link':item['rss_link'],'publisher_hint':item.get('source',''),
            'published_at':item['published_at'],'age_hours':round(age,2),
            'discovery_priority_score':score,'related_headlines':links,
            'potential_distinct_publishers':len(hints),'sources_are_independent':False,
            'article_fulltext_read':False,'claims_verified':False,
            'actual_event_time_checked':False,
            'publisher_origins_confirmed':False,
            'warning':'RSS title similarity and source hints are NOT confirmation or independent corroboration.'})
    candidates.sort(key=lambda e:(-e['discovery_priority_score'],e['id']))
    groups=[]
    for entry in candidates:
        # Near-exact overlap only, never merge merely sharing a topic or company.
        group=next((x for x in groups if title_relation(x['headlines'][0],entry['headline'])>=.86
                    and abs(x['earliest_age_hours']-entry['age_hours'])<=24),None)
        if group:
            group['member_ids'].append(entry['id'])
            group['headlines'].append(entry['headline'])
            group['discovery_count']+=1
            group['possible_same_event_not_proven']=True
        else:
            groups.append({'member_ids':[entry['id']],'headlines':[entry['headline']],
                'earliest_age_hours':entry['age_hours'],'discovery_count':1,
                'possible_same_event_not_proven':False})
    # Show a diverse set of potential events, not twelve copies of one headline.
    shown=set()
    selected=[]
    for entry in candidates:
        grp=next((i for i,g in enumerate(groups) if entry['id'] in g['member_ids']),None)
        if grp is None or grp in shown:continue
        shown.add(grp)
        selected.append(entry)
        if len(selected)>=limit:break
    return {'status':'UNVERIFIED_DISCOVERY_SCREENING',
        'collected_at':data['collected_at'],'country':data.get('country'),
        'category':data.get('category'),'window_hours':hours,
        'total_candidates':len(candidates),'shortlist_count':len(selected),
        'shortlist':selected,'possible_event_groups':groups,
        'eligibility_for_factual_publication':False,'human_selection_required':True,
        'warning':'Sources and claimed event identities remain unverified until original articles are read.'}

def audited_sources(story:dict)->dict:
    """Validate provenance independence per claim rather than counting URLs."""
    source_by_id={}
    concern=[]
    for src in story.get('sources',[]):
        if not isinstance(src,dict):continue
        sid=src.get('id')
        if not sid:continue
        try:canonical=canonical_url(src['url'])
        except (ValueError,KeyError):continue
        publisher=str(src.get('publisher','')).strip().casefold()
        origin=str(src.get('origin_id') or core.organization_domain(canonical)).strip().casefold()
        family=str(src.get('ownership_group') or publisher).strip().casefold()
        direct=src.get('read_confirmed') is True and src.get('syndicated_copy') is not True
        if src.get('syndicated_copy') is True:concern.append('SYNDICATED_NOT_INDEPENDENT:'+sid)
        source_by_id[sid]={'url':canonical,'origin':origin,'publisher':publisher,'family':family,
                           'read_confirmed':direct,'evidence_note':src.get('evidence_note','')}
    claims=[]
    for claim in story.get('claims',[]):
        if not isinstance(claim,dict):continue
        ids=claim.get('source_ids',[])
        sources=[source_by_id[s] for s in ids if s in source_by_id and source_by_id[s]['read_confirmed']]
        families={s['family'] for s in sources if s['family']}
        origins={s['origin'] for s in sources if s['origin']}
        publishers={s['publisher'] for s in sources if s['publisher']}
        urls={s['url'] for s in sources}
        independent=len(families)>=2 and len(origins)>=2 and len(publishers)>=2 and len(urls)>=2
        if not independent:concern.append('CLAIM_NEEDS_TWO_INDEPENDENT_ORIGINS:'+str(claim.get('id')))
        claims.append({'id':claim.get('id'),'reviewed_urls':len(urls),
                       'distinct_owners':len(families),'distinct_origins':len(origins),
                       'distinct_publishers':len(publishers),
                       'independent_support':independent})
    return {'id':story.get('id'),'claims':claims,'issues':concern,
            'claim_independence_pass':bool(claims) and all(c['independent_support'] for c in claims),
            'human_source_review_required':True}

def research_review(bundle:dict,baseline:dict,window_hours:int,requested_country:str|None=None)->dict:
    if window_hours not in (6,24,72,168):raise ValueError('unsupported news window')
    if requested_country is not None and (not isinstance(requested_country,str) or
                                           not requested_country.strip()):
        raise ValueError('invalid requested event country')
    base={x['id']:x for x in baseline['story_reports']}
    ranks={x['id']:x['editorial_priority_score'] for x in baseline.get('editorial_ranking',[])}
    as_of=core.timestamp(bundle['as_of'],'as_of')
    audited=[]
    for story in bundle.get('stories',[]):
        if not isinstance(story,dict) or story.get('id') not in base:continue
        sid=story['id']
        provenance=audited_sources(story)
        events=[]
        age=None
        try:
            age=(as_of-core.timestamp(story['event_at'],'event_at')).total_seconds()/3600
            if age>window_hours:events.append('EVENT_OUTSIDE_REQUESTED_WINDOW')
            if age<-.17:events.append('EVENT_TIME_IN_FUTURE')
        except (TypeError,ValueError,KeyError):events.append('EVENT_TIME_UNVERIFIED')
        for source in story.get('sources',[]):
            if not isinstance(source,dict):continue
            try:
                published=core.timestamp(source.get('published_at'),'published_at')
                retrieved=core.timestamp(source.get('retrieved_at'),'retrieved_at')
                if (published-as_of).total_seconds()>600:
                    events.append('SOURCE_PUBLISHED_AFTER_EVIDENCE_SNAPSHOT:'+str(source.get('id')))
                if (retrieved-as_of).total_seconds()>600:
                    events.append('SOURCE_READ_AFTER_EVIDENCE_SNAPSHOT:'+str(source.get('id')))
                if (published-retrieved).total_seconds()>600:
                    events.append('SOURCE_RETRIEVED_BEFORE_PUBLICATION:'+str(source.get('id')))
            except (TypeError,ValueError):
                events.append('SOURCE_TIMESTAMP_UNVERIFIED:'+str(source.get('id')))
        # RSS edition is not the event location; inspect human-entered evidence.
        event_country=str(story.get('event_country','')).strip().upper()
        if requested_country and requested_country.upper()!='WORLD':
            if event_country!=requested_country.upper():
                events.append('EVENT_COUNTRY_MISMATCH')
        # Never infer event location from Google News region or URL.
        eligible=base[sid]['eligible_for_human_editorial_review'] and provenance['claim_independence_pass'] and not events
        audited.append({'id':sid,'headline':story.get('headline'),
                        'event_age_hours':round(age,2) if age is not None else None,
                        'evidence_gate_pass':base[sid]['eligible_for_human_editorial_review'],
                        'provenance_audit':provenance,'freshness_flags':events,
                        'eligible_for_human_editorial_review':eligible,
                        'editorial_priority_score':ranks.get(sid),
                        'may_auto_approve':False})
        # Reset on every iteration: no stale timestamp from another story.
    ranked=sorted([x for x in audited if x['eligible_for_human_editorial_review']],
                  key=lambda x:(-(x['editorial_priority_score'] or 0),str(x['id'])))
    return {'status':'INDEPENDENT_EVIDENCE_AND_FRESHNESS_SCREEN_ONLY',
        'eligible_count':len(ranked),'checked_count':len(audited),
        'shortlist':ranked[:12],'all_reviews':audited,
        'requested_window_hours':window_hours,'requested_event_country':requested_country,
        'auto_verified_truth':False,
        'user_selection_and_exact_script_approval_required':True}

def markdown(report:dict)->str:
    lines=['# Đề xuất tin để người dùng chọn — yêu cầu kiểm chứng nguồn gốc',
        '', 'Đây chỉ là đánh giá dấu vết nguồn và mức độ mới của sự kiện; KHÔNG xác nhận tính đúng của tin.',
        '',f"Tin đủ hồ sơ đánh giá: {report['eligible_count']}; hiển thị tối đa 12. Chỉ có thể trình tối đa số tin thực đạt cổng kiểm chứng.",
        '']
    for i,entry in enumerate(report['shortlist'],1):
        lines.extend([f"## {i:02d}. {entry['headline']}",'ID: '+str(entry['id']),
            'Điểm ưu tiên biên tập (ước lượng): '+str(entry['editorial_priority_score']),
            'Kiểm độc lập từng claim: '+('ĐẠT hồ sơ' if entry['provenance_audit']['claim_independence_pass'] else 'THIẾU'),
            'Vẫn chờ người dùng chọn sự kiện và duyệt toàn bộ kịch bản.',''])
    return '\n'.join(lines)
