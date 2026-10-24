#!/usr/bin/env python3
"""Reproducible Stage-15 DEMO workloads (never factual news)."""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from pathlib import Path

PATTERNS={
'en-US':[
 'This is a fictional news studio test, not a report about an actual event.',
 'The production system is measuring narration, timing, captions, and transitions in a safe local environment.',
 'Every chart value is artificial and exists only to verify how graphics are displayed on screen.',
 'No organization, person, market, or location is being described as part of a real news story.',
 'After testing the video engine, the original result is kept for technical review and comparison.',
],
'vi-VN':[
 'Đây là bài kiểm thử kỹ thuật với nội dung hoàn toàn giả lập, không phản ánh sự kiện có thật.',
 'Hệ thống đang đánh giá giọng đọc, phụ đề, hiệu ứng chuyển cảnh và chất lượng hình ảnh trong môi trường nội bộ.',
 'Các giá trị trên đồ thị đều được tạo ra để kiểm tra cách thể hiện thông tin, không phải số liệu thời sự.',
 'Mỗi đoạn thử nghiệm được đánh dấu rõ ràng để không nhầm với một bản tin đã kiểm chứng nguồn.',
 'Kết quả sản xuất chỉ dùng để đánh giá hiệu năng và phát hiện lỗi kỹ thuật trước khi triển khai thực tế.',
]}
COUNTS={30:1,60:3,90:4,180:5}
def make(duration:int,language:str,aspect:str)->dict:
    if duration not in COUNTS or language not in PATTERNS or aspect not in ('9:16','16:9','both'):
        raise ValueError('unsupported test scenario')
    count=COUNTS[duration]
    story_entries=[]
    # Updated from local Piper timings measured on 2026-10-24 (30/60/90/180s).
    # English ~2.45 words/s, Vietnamese ~4.25 whitespace-delimited syllables/s.
    # Still only a first estimate; verify actual WAV using stage15_duration_calibrate.py.
    total_words=round(duration*(2.45 if language=='en-US' else 4.25))
    for i in range(count):
        allocation=round(total_words/count)
        lines=[]
        index=i
        while len(' '.join(lines).split())<allocation:
            lines.append(PATTERNS[language][index%len(PATTERNS[language])])
            index+=1
        narrative=' '.join(lines)
        scenes=[{'type':'news_card','instruction':'Original illustrative title card, no real event'}]
        if i%2==1:
            scenes+=[{'type':'infographic','instruction':'Fictional percentage chart, no measured data',
                'title':'DEMO - dữ liệu giả','data_points':[{'label':'Minh họa A','value':65},{'label':'Minh họa B','value':35}]}]
        story_entries.append({'headline':f'DEMO {i+1}/{count}: Kiểm tra bản tin dài {duration} giây',
           'summary':'Chỉ để đo hiệu năng. Không được đăng nội dung giả lập.',
           'narration':narrative,'approved':True,'visual_plan':scenes,
           'sources':[{'title':'TEST source A','url':'https://example.com/stage5-'+str(i),'published_at':'2026-10-23T10:00:00Z'},
                      {'title':'TEST source B','url':'https://example.org/stage5-'+str(i),'published_at':'2026-10-23T10:00:00Z'}]})
    return {'project_name':f'STAGE5-DEMO-{duration}', 'country':'US','category':'technology',
        'language':language,'period':'test_only','target_seconds':duration,
        'aspect_ratio':aspect,'as_of':'2026-10-24T00:00:00+07:00',
        'status':'approved','demo':True,
        'video_title':f'DEMO {duration} seconds: DO NOT PUBLISH',
        'video_description':'Synthetic technical content only; not reporting real news.',
        'hashtags':['#DEMO_DO_NOT_PUBLISH'],
        'stories':story_entries}
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--seconds',type=int,choices=COUNTS,required=True)
    p.add_argument('--language',choices=PATTERNS,default='en-US')
    p.add_argument('--aspect',choices=['9:16','16:9','both'],default='both')
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    obj=make(a.seconds,a.language,a.aspect)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2)
    print(json.dumps({'file':str(a.out),'seconds_target':a.seconds,'stories':len(obj['stories']),
          'narration_words':sum(len(x['narration'].split()) for x in obj['stories']),
          'aspect':a.aspect,'demo':True},ensure_ascii=False))
if __name__=='__main__':main()
