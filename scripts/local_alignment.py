#!/usr/bin/env python3
"""Optional external OFFLINE aligner adapter. Strict transcript/time validation.

The skill does not bundle or download speech models. When no approved local
aligner is installed, the renderer explicitly retains estimated word timing.
The aligner outputs must still be checked by a human listening to the audio.
"""
from __future__ import annotations
import json
import math
import os
import subprocess
import sys
import wave
from pathlib import Path

SCHEMA="LOCAL_WORD_ALIGNMENT_V1"

def validate(cues:list[dict], output:dict, wav:Path)->list[dict]:
    if not isinstance(output,dict) or output.get("schema")!=SCHEMA:
        raise ValueError("local aligner must emit versioned alignment JSON")
    aligned=output.get("cues")
    if not isinstance(aligned,list) or len(aligned)!=len(cues):
        raise ValueError("word alignment cue count differs from narration")
    with wave.open(str(wav),"rb") as handle:
        duration=handle.getnframes()/handle.getframerate()
    result=[]
    for cue,row in zip(cues,aligned):
        words=cue["text"].split()
        proposed=row.get("words") if isinstance(row,dict) else None
        if not isinstance(proposed,list) or len(proposed)!=len(words):
            raise ValueError("word alignment must include each approved subtitle token")
        mapped=[]
        previous=float(cue["start"])-.025
        for written,word in zip(words,proposed):
            if not isinstance(word,dict) or word.get("text")!=written:
                raise ValueError("word aligner changed approved narration text")
            start,end=word.get("start"),word.get("end")
            if (type(start) not in (float,int) or type(end) not in (float,int)
                    or not math.isfinite(start) or not math.isfinite(end)
                    or start<previous-.005 or end<=start
                    or start<float(cue["start"])-.025
                    or end>float(cue["end"])+.035 or end>duration+.05):
                raise ValueError("word aligner times outside measured audio cue")
            mapped.append({"text":written,"start":round(float(start),3),
                           "end":round(float(end),3),
                           "alignment":"LOCAL_OFFLINE_FORCED_ALIGNMENT_VALIDATED"})
            previous=end
        result.append({**cue,"words":mapped})
    return result

def run_if_configured(cues:list[dict],wav:Path,work:Path,runtime:Path)->tuple[list[dict]|None,str]:
    executable=os.environ.get("NEWS_LOCAL_ALIGNER","").strip()
    if not executable:
        return None,"CHUNK_REAL_WAV_WORD_ESTIMATED"
    script=Path(executable).resolve()
    local_runtime=runtime.resolve()
    if not script.is_relative_to(local_runtime) or script.suffix.lower()!=".py" or not script.is_file():
        raise ValueError("local aligner must be a Python script in the private runtime")
    work.mkdir(parents=True,exist_ok=True)
    input_file=work/"alignment_input.json"
    output_file=work/"alignment_output.json"
    if input_file.exists() or output_file.exists():
        raise FileExistsError("alignment input/output already exists")
    input_file.write_text(json.dumps({"schema":SCHEMA,"cues":cues},ensure_ascii=False),encoding="utf-8")
    env=dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
             HF_DATASETS_OFFLINE="1", PYTHONDONTWRITEBYTECODE="1",
             HTTP_PROXY="", HTTPS_PROXY="", ALL_PROXY="", http_proxy="",
             https_proxy="", all_proxy="")
    # No shell; model and script are supplied and audited by the local operator.
    p=subprocess.run([sys.executable,str(script),"--audio",str(wav),
                      "--cues",str(input_file),"--output",str(output_file)],
                     capture_output=True,text=True,timeout=420,env=env)
    if p.returncode!=0 or not output_file.is_file():
        raise RuntimeError("optional local forced aligner failed: "+p.stderr[-500:])
    aligned=validate(cues,json.loads(output_file.read_text(encoding="utf-8-sig")),wav)
    return aligned,"LOCAL_OFFLINE_FORCED_ALIGNMENT_VALIDATED"
