#!/usr/bin/env python3
"""Discover NEWS CANDIDATES from RSS. Neither RSS nor ranking constitutes verification."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path
from difflib import SequenceMatcher

COUNTRIES = {
    'US': ('en-US', 'en'), 'GB': ('en-GB', 'en'), 'VN': ('vi', 'vi'),
    'JP': ('ja', 'ja'), 'KR': ('ko', 'ko'), 'FR': ('fr', 'fr'),
    'DE': ('de', 'de'), 'IN': ('en-IN', 'en'), 'AU': ('en-AU', 'en'),
    'CA': ('en-CA', 'en'), 'WORLD': ('en-US', 'en'),
    'CN': ('zh-CN', 'zh-Hans'), 'TW': ('zh-TW', 'zh-Hant'), 'TH': ('th', 'th'),
    'SG': ('en-SG', 'en'), 'MY': ('en-MY', 'en'), 'ID': ('id', 'id'),
    'PH': ('en-PH', 'en'), 'NZ': ('en-NZ', 'en'), 'RU': ('ru', 'ru'),
    'UA': ('uk', 'uk'), 'IT': ('it', 'it'), 'ES': ('es', 'es'),
    'PT': ('pt-PT', 'pt'), 'BR': ('pt-BR', 'pt'), 'MX': ('es-MX', 'es'),
    'AR': ('es-AR', 'es'), 'ZA': ('en-ZA', 'en'), 'NG': ('en-NG', 'en'),
    'EG': ('ar', 'ar'), 'SA': ('ar', 'ar'), 'AE': ('ar', 'ar'),
    'IL': ('he', 'he'), 'TR': ('tr', 'tr'), 'NL': ('nl', 'nl'),
    'BE': ('nl-BE', 'nl'), 'CH': ('de-CH', 'de'), 'SE': ('sv', 'sv'),
    'NO': ('no', 'no'), 'DK': ('da', 'da'), 'FI': ('fi', 'fi'),
    'PL': ('pl', 'pl'), 'CZ': ('cs', 'cs'), 'AT': ('de-AT', 'de'),
}
CATEGORIES = {
    'general': 'latest breaking news', 'politics': 'politics',
    'economy': 'economy business finance', 'technology': 'technology AI',
    'science': 'science discovery', 'entertainment': 'entertainment',
    'sports': 'sports', 'environment': 'climate environment',
    'health': 'health',
}
AGENT = 'AI-News-Video-Skill/0.3 (research candidates; human verification required)'
MAX_BYTES = 2_000_000

def utc(value: str) -> dt.datetime:
    if not value:
        raise ValueError('empty date')
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        when = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if when.tzinfo is None:
        raise ValueError('timestamp must have timezone')
    return when.astimezone(dt.timezone.utc)

def normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', text.casefold())).strip()

def main_title(title: str) -> str:
    # Trim the publisher suffix often appended by syndicated Google News links.
    return re.split(r'\s[-|–]\s', title, maxsplit=1)[0].strip()

def similar(a: str, b: str) -> bool:
    x, y = normalize(main_title(a)), normalize(main_title(b))
    if not x or not y:
        return False
    if x == y:
        return True
    tokx, toky = set(x.split()), set(y.split())
    overlap = len(tokx & toky) / max(1, min(len(tokx), len(toky)))
    return overlap >= 0.82 and SequenceMatcher(None, x, y).ratio() >= 0.62

def rss_url(country: str, category: str, hours: int, query: str = '') -> str:
    if country not in COUNTRIES or category not in CATEGORIES:
        raise ValueError('Unsupported country/category')
    language, short = COUNTRIES[country]
    region = 'US' if country == 'WORLD' else country
    terms = query.strip() or CATEGORIES[category]
    # Google News edition is a DISCOVERY market, not the event's verified location.
    if country != 'WORLD' and not query.strip():
        terms += ' ' + country
    params = {'q': terms + ' when:' + str(max(1, (hours + 23) // 24)) + 'd',
              'hl': language, 'gl': region, 'ceid': region + ':' + short}
    return 'https://news.google.com/rss/search?' + urllib.parse.urlencode(params)

def retrieve(url: str, retries: int = 2) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or not parsed.netloc:
        raise ValueError('RSS requires HTTPS URL')
    last = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': AGENT, 'Accept': 'application/rss+xml, application/xml, text/xml'})
            with urllib.request.urlopen(request, timeout=15) as response:
                data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError('RSS feed too large')
            return data
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            last = exc
            if attempt < retries:
                time.sleep(0.4 * (2 ** attempt))
    raise RuntimeError('RSS inaccessible: ' + str(last))

def parse_feed(raw: bytes, feed_name: str, source_url: str, now: dt.datetime, hours: int):
    root = ET.fromstring(raw)
    is_atom = root.tag.endswith('feed')
    items = root.findall('{http://www.w3.org/2005/Atom}entry') if is_atom else root.findall('./channel/item')
    found = []
    for item in items:
        def txt(name):
            if is_atom:
                el = item.find('{http://www.w3.org/2005/Atom}' + name)
            else:
                el = item.find(name)
            return (el.text or '').strip() if el is not None else ''
        pub_string = txt('published') or txt('updated') if is_atom else txt('pubDate')
        try:
            published = utc(pub_string)
        except (ValueError, TypeError, OverflowError):
            continue
        age = (now - published).total_seconds()
        if age > hours * 3600 or age < -600:
            continue
        href = ''
        if is_atom:
            links = item.findall('{http://www.w3.org/2005/Atom}link')
            href = next((x.attrib.get('href', '') for x in links if x.attrib.get('rel', 'alternate') == 'alternate'), '')
            if not href and links:
                href = links[0].attrib.get('href', '')
        else:
            href = txt('link')
        if not href.startswith(('https://', 'http://')):
            continue
        src = item.find('source') if not is_atom else None
        publisher = (src.text or '').strip() if src is not None else feed_name
        title = re.sub(r'\s+', ' ', txt('title')).strip()
        if not title:
            continue
        stable = hashlib.sha256((normalize(main_title(title)) + '|' + published.date().isoformat()).encode('utf-8')).hexdigest()[:12]
        found.append({'id': 'N-' + stable, 'headline': title, 'source': publisher,
                      'published_at': published.isoformat(), 'rss_link': href,
                      'feed': feed_name, 'feed_url': source_url,
                      'status': 'UNVERIFIED_RSS_CANDIDATE',
                      'warning': 'RSS is a discovery pointer, not checked evidence.'})
    return found

def deduplicate(items: list[dict]) -> list[dict]:
    # This is TITLE-level duplicate grouping, NOT reliable same-event clustering.
    groups = []
    for obj in sorted(items, key=lambda x: x['published_at'], reverse=True):
        existing = next((g for g in groups if similar(g['headline'], obj['headline'])), None)
        if existing is None:
            row = dict(obj)
            row['related_articles'] = [{'headline': obj['headline'], 'source': obj['source'],
                                        'rss_link': obj['rss_link']}]
            row['candidate_count'] = 1
            groups.append(row)
        else:
            if not any(e['rss_link'] == obj['rss_link'] for e in existing['related_articles']):
                existing['related_articles'].append({'headline': obj['headline'], 'source': obj['source'], 'rss_link': obj['rss_link']})
                existing['candidate_count'] += 1
    return groups

def fetch(country: str, category: str, hours: int, limit: int,
          extra_feeds: list[dict] | None = None, query: str = '') -> dict:
    if country not in COUNTRIES or category not in CATEGORIES:
        raise ValueError('unsupported country/category')
    if not (1 <= hours <= 168 and 1 <= limit <= 100):
        raise ValueError('hours must be 1..168 and limit 1..100')
    now = dt.datetime.now(dt.timezone.utc)
    feeds = [{'name': 'Google News ' + country, 'url': rss_url(country, category, hours, query)}] + (extra_feeds or [])
    candidates, logs = [], []
    for feed in feeds:
        name, url = str(feed['name']), str(feed['url'])
        try:
            result = parse_feed(retrieve(url), name, url, now, hours)
            candidates.extend(result)
            logs.append({'feed': name, 'status': 'OK', 'count': len(result), 'url': url})
        except (ValueError, RuntimeError, ET.ParseError, KeyError) as exc:
            logs.append({'feed': name, 'status': 'ERROR', 'error': str(exc), 'url': url})
    unique = deduplicate(candidates)[:limit]
    return {'country': country, 'category': category, 'hours': hours,
            'region_semantics': 'discovery feed edition, NOT confirmed event location',
            'query': query, 'collected_at': now.isoformat(),
            'rss_url': feeds[0]['url'], 'feed_results': logs,
            'candidates': unique, 'raw_candidates': len(candidates),
            'status': 'RESEARCH_ONLY_NOT_APPROVED',
            'warning': 'Sources, claims, and event location must be checked independently.'}

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--country', choices=COUNTRIES, default='US')
    ap.add_argument('--category', choices=CATEGORIES, default='general')
    ap.add_argument('--hours', type=int, default=24)
    ap.add_argument('--limit', type=int, default=20)
    ap.add_argument('--query', default='')
    ap.add_argument('--feeds', type=Path, help='Optional JSON list of HTTPS feeds with name,url and optional country/category filters')
    ap.add_argument('--out', type=Path, default=Path('news_candidates.json'))
    arg = ap.parse_args()
    ap.error('hours 1..168 and limit 1..100') if not (1 <= arg.hours <= 168 and 1 <= arg.limit <= 100) else None
    feeds = []
    if arg.feeds:
        config = json.loads(arg.feeds.read_text(encoding='utf-8-sig'))
        if not isinstance(config, list):
            ap.error('feed config must be a JSON list')
        for feed in config:
            if not isinstance(feed, dict) or 'name' not in feed or 'url' not in feed:
                ap.error('each feed must have name and url')
            # WORLD is a real scope (global edition), not permission to inject
            # world headlines into a specific country's shortlist.
            if feed.get('country', 'WORLD') not in (arg.country, 'ALL'):
                continue
            if feed.get('category', 'general') not in ('general', arg.category):
                continue
            feeds.append({'name': feed['name'], 'url': feed['url']})
    result = fetch(arg.country, arg.category, arg.hours, arg.limit, feeds, arg.query)
    arg.out.parent.mkdir(parents=True, exist_ok=True)
    if arg.out.exists():
        ap.error('output exists; select a new file to avoid overwriting')
    arg.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(arg.out), 'candidates': len(result['candidates']),
                      'feeds': result['feed_results'], 'verification': 'NOT VERIFIED'}, ensure_ascii=False))

if __name__ == '__main__':
    main()
