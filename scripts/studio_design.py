#!/usr/bin/env python3
"""Stage 20 approved visual identities and deterministic safe-area/readability preflight.

Design settings come only from the user-approved brief. No external font or media.
"""
from __future__ import annotations
import json
from dataclasses import dataclass

PRESETS={
 'quick':{'display_name':'Tin nhanh / Flash',
    'colors':{'navy':'#071624','panel':'#0B2238','accent':'#43D9E8','hot':'#FD694E','text':'#F7FBFF','muted':'#BED3DE'},
    'intro_frames':9,'outro_frames':12,'transition_frames':9,'pace':'energetic'},
 'roundup':{'display_name':'Bản tin tổng hợp / Roundup',
    'colors':{'navy':'#0A1934','panel':'#132E4E','accent':'#73D8F4','hot':'#EA526F','text':'#F6FAFF','muted':'#BCD1E6'},
    'intro_frames':12,'outro_frames':12,'transition_frames':12,'pace':'balanced'},
 'deep_dive':{'display_name':'Phân tích chuyên sâu / Deep dive',
    'colors':{'navy':'#14212D','panel':'#213344','accent':'#EBC36B','hot':'#69BFBE','text':'#FAF9F6','muted':'#C3D0D9'},
    'intro_frames':15,'outro_frames':15,'transition_frames':15,'pace':'considered'}
}
BRAND={'name':'AI NEWS VIDEO','mark':'AN','copyright_free':'Original vector/CSS layout, no external brand assets'}
SAFE_AREAS={
 '9:16':{'width':1080,'height':1920,'top_guard':136,'bottom_guard':390,
         'left_guard':88,'right_guard':130,'subtitle_bottom':385,
         'title_top':300,'content_max_y':1320},
 '16:9':{'width':1920,'height':1080,'top_guard':90,'bottom_guard':150,
         'left_guard':116,'right_guard':122,'subtitle_bottom':166,
         'title_top':200,'content_max_y':775},
}
MAX_HEADLINE=235
MAX_SUMMARY=460

def validate(brief:dict)->dict:
    if not isinstance(brief,dict):raise ValueError('brief must be JSON object')
    preset=brief.get('visual_style','roundup')
    if preset not in PRESETS:raise ValueError('visual_style must be quick, roundup or deep_dive')
    lang=brief.get('language','vi-VN')
    if not isinstance(lang,str) or lang.split('-')[0] not in ('en','vi'):
        raise ValueError('design supports Vietnamese and English only')
    stories=brief.get('stories',[])
    if not isinstance(stories,list) or not 1<=len(stories)<=15:
        raise ValueError('invalid design story count')
    warnings=[]
    for i,story in enumerate(stories,1):
        for key,limit in (('headline',MAX_HEADLINE),('summary',MAX_SUMMARY)):
            value=story.get(key)
            if not isinstance(value,str) or not value.strip():
                raise ValueError(f'story {i} {key} is missing')
            if len(value)>limit:
                raise ValueError(f'story {i} {key} too long for safe-area; revise BEFORE script approval')
        if len(story['headline'])>115:
            warnings.append({'story':i,'code':'LONG_HEADLINE_NEEDS_VISUAL_QA','characters':len(story['headline'])})
        if len(story['summary'])>260:
            warnings.append({'story':i,'code':'LONG_SUMMARY_NEEDS_VISUAL_QA','characters':len(story['summary'])})
        if any(sc.get('type')=='infographic' for sc in (story.get('visual_plan') or [])):
            if len(story['headline'])>165 or len(story['summary'])>230:
                raise ValueError('Infographic text requires a shorter approved headline/summary for 9:16 safe-area')
        for j,scene in enumerate(story.get('visual_plan') or []):
            if scene.get('type')=='infographic':
                pts=scene.get('data_points',[])
                if not 1<=len(pts)<=5:
                    raise ValueError('Infographic must contain 1..5 approved metrics')
                for point in pts:
                    if (not isinstance(point.get('label'),str) or
                        type(point.get('value')) not in (int,float) or not 0<=point['value']<=100):
                        raise ValueError('Infographic metrics must be preapproved 0..100')
                    if len(point['label'])>45:
                        warnings.append({'story':i,'shot':j,'code':'LONG_CHART_LABEL_REVIEW'})
    styles=PRESETS[preset]
    return {'schema':'STAGE20_DESIGN_V1','visual_style':preset,
        'visual_display_name':styles['display_name'],
        'brand':BRAND,'language':lang,'palette':styles['colors'],
        'intro_frames':styles['intro_frames'],'outro_frames':styles['outro_frames'],
        'transition_frames':styles['transition_frames'],
        'safe_areas':SAFE_AREAS,'warnings':warnings,
        'identity_assets_external':False,'video_content_not_rewritten':True,
        'human_visual_review_required':True}

def render_props(brief:dict)->dict:
    report=validate(brief)
    return {key:report[key] for key in ('visual_style','palette','intro_frames',
        'outro_frames','transition_frames','language','brand','safe_areas')}

def save_preflight(brief:dict,target)->dict:
    import pathlib
    path=pathlib.Path(target)
    if path.exists():raise FileExistsError('stage20 design report already exists')
    report=validate(brief)
    with path.open('x',encoding='utf-8') as f:
        json.dump(report,f,indent=2,ensure_ascii=False)
    return report
