#!/usr/bin/env python3
"""Editorial-only narration duration guidance from measured local Piper benchmarks.
This file cannot alter approved scripts, media, narration or user approvals.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path

# Estimated spoken tokens/s, fitted from measured DEMO clips at Piper rate 1.0.
# Each sample includes scene pauses and is approximate, never a promise.
BENCHMARK_BASELINE={
    'en':{'words_per_sec':2.45,'basis':'Stage5 DEMO: 61 words/25s; 184/74.2s; 380/154.77s'},
    'vi':{'words_per_sec':4.24,'basis':'Stage5 DEMO: 202 whitespace-separated syllables/47.63s'},
}
def language_key(value:str)->str:
    if not isinstance(value,str) or value.split('-')[0] not in BENCHMARK_BASELINE:
        raise ValueError('unsupported language (vi/en)')
    return value.split('-')[0]

def predict(narrations:list[str],language:str,target_seconds:int,speech_rate:float=1.0)->dict:
    key=language_key(language)
    if not narrations or any(not isinstance(s,str) or not s.strip() for s in narrations):
        raise ValueError('narrations must be nonempty list of strings')
    if not isinstance(target_seconds,int) or not 15<=target_seconds<=180:
        raise ValueError('target seconds out of bounds')
    if not isinstance(speech_rate,(int,float)) or not .75<=speech_rate<=1.35:
        raise ValueError('speech rate out of bounds')
    observed_tokens=sum(len(s.split()) for s in narrations)
    baseline=BENCHMARK_BASELINE[key]
    spoken_per_second=baseline['words_per_sec']*speech_rate
    estimate=round(observed_tokens/spoken_per_second,1)
    suggested=round(target_seconds*spoken_per_second)
    drift=estimate-target_seconds
    return {'language':language,'target_seconds':target_seconds,'speech_rate':speech_rate,
            'story_count':len(narrations),'observed_whitespace_tokens':observed_tokens,
            'estimated_seconds':estimate,'delta_seconds':round(drift,1),
            'suggested_total_tokens':suggested,'recommended_token_difference':suggested-observed_tokens,
            'within_15_percent':abs(drift)<=target_seconds*.15,
            'caution':'Advisory only. Piper duration depends on names, punctuation, pronunciation map, pacing, and the individual voice. Measure WAV after approval; do not rewrite a user-approved script automatically.',
            'benchmark_basis':baseline['basis']}
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--brief',required=True,type=Path)
    ap.add_argument('--rate',type=float,default=1.)
    ap.add_argument('--out',required=True,type=Path)
    a=ap.parse_args()
    if a.out.exists():ap.error('output already exists')
    brief=json.loads(a.brief.read_text(encoding='utf-8-sig'))
    data=predict([s['narration'] for s in brief['stories']],brief['language'],
                 brief['target_seconds'],a.rate)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
    print(json.dumps(data,ensure_ascii=False))
if __name__=='__main__':main()
