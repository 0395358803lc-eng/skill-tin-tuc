#!/usr/bin/env python3
"""Search Wikimedia Commons for candidate media and license metadata (never auto-approve)."""
import argparse
import datetime as dt
import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

API='https://commons.wikimedia.org/w/api.php'
AGENT='AI-News-Video-Skill/0.4 research (media licensing requires human check)'
def clean(v):
    return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',str(v or '')))).strip()
def field(meta,name):
    obj=meta.get(name)
    return clean(obj.get('value','')) if isinstance(obj,dict) else ''
def search(query: str,limit: int=12) -> dict:
    if not isinstance(query,str) or not query.strip() or len(query)>180:
        raise ValueError('query must be 1..180 characters')
    if not 1 <= limit <= 25:raise ValueError('limit 1..25')
    url=API+'?'+urllib.parse.urlencode({
        'action':'query','format':'json','generator':'search','gsrsearch':query,
        'gsrnamespace':6,'gsrlimit':limit,'prop':'imageinfo',
        'iiprop':'url|extmetadata|mime','iiurlwidth':800})
    request=urllib.request.Request(url,headers={'User-Agent':AGENT})
    with urllib.request.urlopen(request,timeout=20) as response:
        raw=response.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError('metadata response too large')
    data=json.loads(raw)
    assets=[]
    for page in data.get('query',{}).get('pages',{}).values():
        info=(page.get('imageinfo') or [{}])[0]
        meta=info.get('extmetadata') or {}
        lic=field(meta,'LicenseShortName')
        mime=info.get('mime','')
        if not (mime.startswith('image/') or mime.startswith('video/')):continue
        link=info.get('url','')
        if not link.startswith('https://'):continue
        license_url=field(meta,'LicenseUrl')
        notes=[]
        if not lic:notes.append('Missing readable license, do not use')
        if any(x in lic.lower() for x in ('non-commercial','noncommercial','nc','no derivatives','nd')):
            notes.append('License may prohibit commercial use/derivatives; review')
        assets.append({'id':str(page['pageid']),'title':page.get('title',''),
          'mime':mime,'url':link,'description_page_url':info.get('descriptionurl',''),
          'thumbnail_url':info.get('thumburl',''),'license_short_name':lic,
          'license_url':license_url,'author':field(meta,'Artist'),
          'attribution_required':field(meta,'AttributionRequired'),
          'credit':field(meta,'Credit'),'description':field(meta,'ImageDescription')[:300],
          'permission_status':'REQUIRES_HUMAN_LICENSE_CHECK','warnings':notes})
    assets.sort(key=lambda x:(not bool(x['license_url']),x['title']))
    return {'source':'Wikimedia Commons public API','query':query,
            'searched_at':dt.datetime.now(dt.timezone.utc).isoformat(),
            'candidates':assets,'verification':'LICENSE NOT YET APPROVED',
            'disclaimer':'Every file has different terms; do not download or publish until reviewing file page, restrictions, attribution and commercial use.'}
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--query',required=True)
    ap.add_argument('--limit',type=int,default=12)
    ap.add_argument('--out',type=Path,required=True)
    opts=ap.parse_args()
    if opts.out.exists():
        ap.error('output exists; will not overwrite')
    try:result=search(opts.query,opts.limit)
    except Exception as e:ap.exit(2,'SEARCH_ERROR: '+str(e)+'\n')
    opts.out.parent.mkdir(parents=True,exist_ok=True)
    with opts.out.open('x',encoding='utf-8') as dest:json.dump(result,dest,ensure_ascii=False,indent=2)
    print(json.dumps({'candidates':len(result['candidates']),'out':str(opts.out),
                      'status':result['verification']},ensure_ascii=False))
if __name__=='__main__':main()
