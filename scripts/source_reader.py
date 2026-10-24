#!/usr/bin/env python3
"""Optional first-pass public HTML reader. A web page snapshot is NOT fact verification."""
from __future__ import annotations
import argparse
import datetime as dt
import ipaddress
import json
import re
import socket
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser
from pathlib import Path
import safe_http

MAX_HTTP_BYTES = 1_500_000
AGENT = 'AI-News-Video-Skill/0.3 (editorial-research; respects robots.txt)'

class PublicArticle(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.article_depth = 0
        self.parts = []
        self.headings = []
        self.metadata = {}
        self.tagstack = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tagstack.append(tag)
        if tag in ('script', 'style', 'noscript', 'svg'):
            self.skip += 1
        if tag == 'article':
            self.article_depth += 1
        if tag == 'meta':
            key = attrs.get('property') or attrs.get('name')
            if key in ('og:title', 'article:published_time', 'article:modified_time', 'description'):
                self.metadata[key] = attrs.get('content', '')
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.metadata['canonical'] = attrs.get('href', '')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'svg') and self.skip:
            self.skip -= 1
        if tag == 'article' and self.article_depth:
            self.article_depth -= 1
        if self.tagstack:
            self.tagstack.pop()

    def handle_data(self, data):
        if self.skip:
            return
        value = re.sub(r'\s+', ' ', data).strip()
        if len(value) < 3:
            return
        target = self.article_depth or any(t in ('h1', 'h2', 'p', 'blockquote') for t in self.tagstack)
        if target:
            self.parts.append(value)
        if any(t in ('h1', 'h2') for t in self.tagstack):
            self.headings.append(value)

def public_https(url: str) -> str:
    """Validate syntax early; actual connection enforces pinned public DNS."""
    safe_http.url_parts(url)
    return url

def download(url: str) -> tuple[str, str]:
    public_https(url)
    parsed = urllib.parse.urlsplit(url)
    robots = urllib.parse.urlunsplit(("https", parsed.netloc, "/robots.txt", "", ""))
    # A source remains unreviewed whenever robots cannot be established.
    raw_robots, final_robots, content_type, _ = safe_http.get(robots, 250_000, timeout=10)
    if urllib.parse.urlsplit(final_robots).hostname != parsed.hostname:
        raise ValueError("robots policy redirected to another origin")
    if "text/plain" not in content_type.lower() and "text/" not in content_type.lower():
        raise ValueError("robots policy is not text")
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(raw_robots.decode("utf-8", errors="replace").splitlines())
    if not parser.can_fetch(AGENT, url):
        raise ValueError("robots.txt forbids automated retrieval")
    data, final_url, reply_type, _ = safe_http.get(url, MAX_HTTP_BYTES, timeout=20)
    if "text/html" not in reply_type.lower():
        raise ValueError("source is not HTML")
    # When a redirect changes the path, verify robots against the final URL too.
    if not parser.can_fetch(AGENT, final_url):
        raise ValueError("robots.txt forbids redirected article URL")
    charset = "utf-8"
    marker = re.search(r"charset\\s*=\\s*['\\\"]?([a-zA-Z0-9_-]+)", reply_type, re.I)
    if marker:
        charset = marker.group(1)
    try:
        return data.decode(charset, errors="replace"), final_url
    except LookupError as exc:
        raise ValueError("unsupported article text encoding") from exc

def read(url: str, max_chars: int = 24000) -> dict:
    if not 1000 <= max_chars <= 50000:
        raise ValueError("article text budget must be 1000..50000")
    content, final_url = download(url)
    parser = PublicArticle()
    parser.feed(content)
    combined = '\n'.join(parser.parts)
    combined = re.sub(r'\n{3,}', '\n\n', combined).strip()
    if len(combined) < 250:
        raise ValueError('not enough readable article text; use browser/manual verification')
    return {'url': final_url, 'requested_url': url,
            'retrieved_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'metadata': parser.metadata, 'headings': parser.headings[:15],
            'extracted_text': combined[:max_chars], 'total_extracted_chars': len(combined),
            'extraction_complete': len(combined) <= max_chars,
            'status': 'TEXT_EXTRACTED_NOT_VERIFIED',
            'warning': 'Extraction may omit JS, hide corrections, or include navigation. AI/human must open original and inspect claims and media rights.'}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', required=True)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--max-chars', default=24000, type=int)
    args = ap.parse_args()
    if not (1000 <= args.max_chars <= 50000):
        ap.error('--max-chars must be 1000..50000')
    try:
        result = read(args.url, args.max_chars)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('x', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(json.dumps({'status': result['status'], 'url': result['url'],
                          'total_extracted_chars': result['total_extracted_chars'],
                          'output': str(args.out)}))
    except (OSError, ValueError, UnicodeError) as exc:
        ap.exit(2, 'READ_ERROR: ' + str(exc) + '\n')

if __name__ == '__main__':
    main()
