#!/usr/bin/env python3
"""Stage18: local narration/caption timing audit and *estimated* word emphasis.
Waveform/phrase times are real; word positions are NOT forced aligned.
"""
from __future__ import annotations
import json, math, re, unicodedata, wave
from pathlib import Path

def word_weight(token:str)->float:
    # Estimated phonetic/syllabic weight, not a measured voice-to-text alignment.
    meaningful=re.sub(r'[^\wÀ-ỹ]+','',token,flags=re.UNICODE)
    return max(0.75,min(2.7,len(meaningful)/5.0))

def word_timing(cue:dict)->list[dict]:
    start,end=float(cue['start']),float(cue['end'])
    if end<=start or not math.isfinite(start+end):
        raise ValueError('invalid caption interval')
    tokens=str(cue['text']).split()
    if not tokens or len(tokens)>65:raise ValueError('caption missing text or overly long')
    weights=[word_weight(t)*(1.15 if t.endswith(('.',':',';','?','!')) else 1.0) for t in tokens]
    total=sum(weights)
    cursor=start
    out=[]
    for i,(token,weight) in enumerate(zip(tokens,weights)):
        final=end if i==len(tokens)-1 else min(end,cursor+(end-start)*weight/total)
        out.append({'text':token,'start':round(cursor,3),'end':round(final,3),
                    'alignment':'ESTIMATED_WITHIN_PIPER_CHUNK'})
        cursor=final
    return out

def enrich_cues(cues:list[dict])->list[dict]:
    return [{**cue,'words':word_timing(cue)} for cue in cues]

def lexicon_review(original:str,lexicon:dict)->dict:
    if not isinstance(lexicon,dict) or len(lexicon)>150:raise ValueError('bad pronunciation lexicon')
    matches=[]
    for written,spoken in lexicon.items():
        if not isinstance(written,str) or not isinstance(spoken,str) or not written.strip() or not spoken.strip() or len(written)>80 or len(spoken)>160:
            raise ValueError('invalid lexicon entry')
        count=len(re.findall(r'(?<!\w)'+re.escape(written)+r'(?!\w)',original))
        if count:matches.append({'written':written,'spoken_for_tts':spoken,'occurrences':count})
    return {'matched':matches,'review_required':bool(matches),
            'subtitle_uses_original_wording':True,
            'note':'Phonetic substitution is a human-reviewed instruction, not proof of correct pronunciation.'}

def audit(cues:list[dict],narration_wav:Path,brief:dict,lexicon:dict|None=None,
          word_alignment:str='CHUNK_REAL_WAV_WORD_ESTIMATED')->dict:
    with wave.open(str(narration_wav),'rb') as w:
        seconds=w.getnframes()/w.getframerate()
        rate=w.getframerate()
    if not cues:raise ValueError('missing speech captions')
    previous=-1.
    count=0
    coverage=0.
    words=0
    largest=0
    for cue in cues:
        a,b=float(cue['start']),float(cue['end'])
        if a<previous-.06 or b<=a or b>seconds+.10:
            raise ValueError('SRT text timing not consistent with actual WAV: '+repr(cue))
        if not str(cue['text']).strip():raise ValueError('empty subtitle')
        count+=1
        words+=len(str(cue['text']).split())
        largest=max(largest,len(str(cue['text'])))
        coverage+=b-a
        previous=b
    original=' '.join(s['narration'] for s in brief.get('stories',[]))
    lexico=lexicon_review(original,lexicon or {})
    if word_alignment not in ('CHUNK_REAL_WAV_WORD_ESTIMATED','LOCAL_OFFLINE_FORCED_ALIGNMENT_VALIDATED'):
        raise ValueError('unsupported word alignment')
    status='REVIEW_REQUIRED'
    warnings=[]
    if coverage/max(.1,seconds)<.60:warnings.append('LOW_SUBTITLE_COVERAGE')
    if largest>84:warnings.append('LONG_CAPTION_TEXT_FOR_SMALL_VERTICAL_FORMAT')
    if any(ch.isdigit() for ch in original):
        warnings.append('NUMBERS_AND_DATES_NEED_HUMAN_PRONUNCIATION_REVIEW')
    if abs(seconds-float(brief['target_seconds']))>float(brief['target_seconds'])*.05:
        warnings.append('VOICE_DURATION_OUTSIDE_5PCT')
    return {'schema':'STAGE18_AUDIO_QA_V1','status':status,
        'voice_real_wav_seconds':round(seconds,3),'audio_sample_rate':rate,
        'target_seconds':brief['target_seconds'],'caption_cues':count,
        'approximate_word_highlights':words,
        'caption_coverage_pct':round(100*coverage/seconds,2),
        'max_caption_characters':largest,'alignment':word_alignment,
        'word_forced_alignment_performed':word_alignment=='LOCAL_OFFLINE_FORCED_ALIGNMENT_VALIDATED','lexicon':lexico,'warnings':warnings,
        'requires_listening_review':True,'no_script_rewrite':True}

def save_audit(cues:list[dict],narration_wav:Path,brief:dict,output:Path,lexicon:dict|None=None,
               word_alignment:str='CHUNK_REAL_WAV_WORD_ESTIMATED')->dict:
    if output.exists():raise FileExistsError('voice QA already exists')
    result=audit(cues,narration_wav,brief,lexicon,word_alignment)
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    return result
