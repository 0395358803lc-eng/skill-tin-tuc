#!/usr/bin/env python3
"""Deterministic editorial flags; language heuristics NEVER verify facts.

This helper checks approved-script *readiness for human review*. It makes no
claims about correctness, copyright, newsworthiness, or publication rights.
"""
from __future__ import annotations
import re
from collections import Counter

SENSATIONAL = (
    r"you won't believe", r"shocking truth", r"guaranteed viral",
    r"không thể tin nổi", r"sốc toàn tập", r"chắc chắn gây sốc",
    r"100% sự thật", r"ai cũng phải xem",
)
RELATIVE_TIME = re.compile(r"\b(?:today|yesterday|tomorrow|breaking now|hôm nay|hôm qua|ngày mai)\b", re.I)
EXPLICIT_DATE = re.compile(r"\b\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?\b|\b20\d{2}\b")
WORD = re.compile(r"\b[\wÀ-ỹ]+\b",re.UNICODE)

def review(manifest: dict) -> dict:
    stories=manifest.get("stories",[])
    target=manifest.get("target_seconds",60)
    flags=[]
    titles=Counter(str(s.get("headline","")).strip().casefold() for s in stories)
    for index,story in enumerate(stories,1):
        headline=str(story.get("headline",""))
        summary=str(story.get("summary",""))
        narration=str(story.get("narration",""))
        combined=" ".join((headline,summary,narration))
        if titles[headline.strip().casefold()]>1:
            flags.append({"story":index,"code":"REPEATED_HEADLINE_REVIEW"})
        if any(re.search(pattern,combined,re.I) for pattern in SENSATIONAL):
            flags.append({"story":index,"code":"SENSATIONAL_LANGUAGE_REVIEW"})
        if RELATIVE_TIME.search(combined) and not EXPLICIT_DATE.search(narration):
            flags.append({"story":index,"code":"RELATIVE_TIME_NEEDS_EXPLICIT_CONTEXT"})
        if len(narration.strip())<80:
            flags.append({"story":index,"code":"SHORT_NARRATION_EDITORIAL_REVIEW"})
        if not story.get("claim_ids"):
            flags.append({"story":index,"code":"CLAIMS_NOT_LINKED"})
    words=sum(len(WORD.findall(str(s.get("narration","")))) for s in stories)
    pace=round(words/(float(target)/60.0),1) if type(target) in (int,float) and target>0 else None
    if pace is not None and (pace>175 or pace<75):
        flags.append({"story":None,"code":"PACING_ESTIMATE_REVIEW","estimated_wpm":pace})
    return {"status":"HUMAN_EDITORIAL_REVIEW_REQUIRED",
            "flags":flags,"estimated_narration_wpm":pace,
            "claim_ids_are_links_not_proof":True,
            "automatically_verified_news":False,
            "publication_approved":False,
            "note":"Heuristics cannot verify truth, sources, naturalness or spoken timing."}
