"""Stage 3 regression tests: offline fixtures only; no live news or private networks."""
from __future__ import annotations
import copy
import datetime as dt
import ipaddress
import json
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import safe_http
import news_rss as rss
import research_enrichment as research
import source_reader as reader
import editorial_core as core
import editorial_quality as quality
from test_editorial import bundle,script,NOW

class SafeNewsResearchTests(unittest.TestCase):
    def test_13_country_category_time_window_in_rss_url(self):
        from urllib.parse import parse_qs,urlsplit
        us=urlsplit(rss.rss_url("US","technology",24))
        global_feed=urlsplit(rss.rss_url("WORLD","science",72))
        self.assertEqual(parse_qs(us.query)["gl"],["US"])
        self.assertIn("technology",parse_qs(us.query)["q"][0])
        self.assertEqual(parse_qs(global_feed.query)["ceid"],["US:en"])
        with self.assertRaisesRegex(ValueError,"Unsupported"):
            rss.rss_url("XX","technology",24)
        with self.assertRaises(ValueError):
            rss.rss_url("US","technology",24,"keyword "*100)

    def test_13_rss_time_filter_and_explicit_query(self):
        sample=b'<rss><channel><item><title>Unit Test</title><link>https://example.org/unit</link><pubDate>Fri, 23 Oct 2026 12:00:00 GMT</pubDate></item></channel></rss>'
        now=dt.datetime(2026,10,23,18,tzinfo=dt.timezone.utc)
        self.assertEqual(len(rss.parse_feed(sample,"fixture","https://example.org/feed",now,6)),1)
        self.assertEqual(len(rss.parse_feed(sample,"fixture","https://example.org/feed",now,5)),0)
        with self.assertRaises(ValueError):
            rss.fetch("US","technology",0,10)

    def test_13_feed_network_and_byte_limits(self):
        with patch.object(rss.safe_http,"get",return_value=(b"<rss/>","https://example.org/rss","application/rss+xml",200)) as op:
            self.assertEqual(rss.retrieve("https://example.org/rss"),b"<rss/>")
            self.assertEqual(op.call_args.args[1],rss.MAX_BYTES)
        with self.assertRaisesRegex(ValueError,"public HTTPS"):
            rss.retrieve("http://localhost/rss")
        with self.assertRaisesRegex(ValueError,"unsafe XML"):
            rss.parse_feed(b'<!DOCTYPE rss [<!ENTITY x "oops">]><rss/>',
                           "fixture","https://example.org/rss",
                           dt.datetime.now(dt.timezone.utc),24)

    def test_14_numeric_events_are_never_merged(self):
        a="Annual index increases 2.1 percent after review - Publisher"
        b="Annual index increases 2.2 percent after review - Publisher"
        self.assertFalse(rss.similar(a,b))
        self.assertEqual(research.title_relation(a,b),0)
        self.assertTrue(rss.similar(a,a))

    def test_14_grouping_same_event_with_identical_headline(self):
        a={"id":"N-1","headline":"Research team reports a synthetic launch - Publisher A",
           "published_at":NOW,"source":"A","rss_link":"https://example.com/a"}
        b={**a,"id":"N-2","source":"B","rss_link":"https://example.org/b"}
        grouped=rss.deduplicate([a,b])
        self.assertEqual(len(grouped),1)
        self.assertEqual(grouped[0]["candidate_count"],2)
        self.assertNotIn("verified",grouped[0]["status"].lower()) if "status" in grouped[0] else None

    def test_14_old_same_headline_is_distinct_event(self):
        a={"id":"N-a","headline":"Synthetic election tally announced",
           "published_at":NOW,"source":"A","rss_link":"https://example.org/a"}
        b={**a,"id":"N-b","published_at":"2026-10-20T11:00:00Z",
           "rss_link":"https://example.org/b"}
        self.assertEqual(len(rss.deduplicate([a,b])),2)

    def test_15_evidence_country_scope_is_not_rss_edition(self):
        b=bundle()
        valid=core.check_bundle(b)
        self.assertEqual(research.research_review(b,valid,24,"US")["eligible_count"],1)
        invalid=research.research_review(b,valid,24,"VN")
        self.assertEqual(invalid["eligible_count"],0)
        self.assertIn("EVENT_COUNTRY_MISMATCH",invalid["all_reviews"][0]["freshness_flags"])
        self.assertEqual(research.research_review(b,valid,24,"WORLD")["eligible_count"],1)

    def test_15_reposted_same_owner_does_not_count_as_independent(self):
        b=bundle()
        s=b["stories"][0]
        s["sources"][0]["ownership_group"]="common-owner"
        s["sources"][1]["ownership_group"]="common-owner"
        self.assertFalse(research.audited_sources(s)["claim_independence_pass"])
        self.assertFalse(research.research_review(b,core.check_bundle(b),24)["auto_verified_truth"])

    def test_16_bad_source_urls_and_dns_rebinding_are_rejected(self):
        for url in ("http://example.org","https://localhost/a","https://127.0.0.1/file",
                    "https://good.org:8443/","https://alice:secret@good.org/x","file:///tmp/data"):
            with self.subTest(url=url),self.assertRaises(ValueError):
                safe_http.url_parts(url) if "127.0.0.1" not in url else safe_http.resolved_public_addrs("localhost")
        with patch.object(safe_http.socket,"getaddrinfo",return_value=[
            (socket.AF_INET,socket.SOCK_STREAM,6,"",("127.0.0.1",443))]):
            with self.assertRaisesRegex(ValueError,"non-public"):
                safe_http.resolved_public_addrs("news.example")
        with patch.object(safe_http.socket,"getaddrinfo",return_value=[
            (socket.AF_INET,socket.SOCK_STREAM,6,"",("8.8.8.8",443)),
            (socket.AF_INET,socket.SOCK_STREAM,6,"",("10.0.0.7",443))]):
            with self.assertRaisesRegex(ValueError,"non-public"):
                safe_http.resolved_public_addrs("mixed.example")

    def test_16_reader_enforces_robots_before_article(self):
        denial=b"User-agent: *\nDisallow: /forbidden\n"
        with patch.object(reader.safe_http,"get",return_value=(denial,"https://example.org/robots.txt","text/plain",200)) as fetch:
            with self.assertRaisesRegex(ValueError,"robots.txt forbids"):
                reader.download("https://example.org/forbidden")
            self.assertEqual(fetch.call_count,1)

    def test_16_reader_requires_bounded_html(self):
        with self.assertRaisesRegex(ValueError,"budget"):
            reader.read("https://example.org/article",max_chars=999)
        long="<article><h1>Fixture</h1><p>" + "Test article. "*40 + "</p></article>"
        robots=b"User-agent: *\nAllow: /\n"
        with patch.object(reader.safe_http,"get",side_effect=[
            (robots,"https://example.org/robots.txt","text/plain",200),
            (long.encode("utf-8"),"https://example.org/article","text/html; charset=utf-8",200)]):
            out=reader.read("https://example.org/article",max_chars=1000)
        self.assertEqual(out["status"],"TEXT_EXTRACTED_NOT_VERIFIED")
        self.assertGreater(out["total_extracted_chars"],250)

    def test_17_editorial_flags_preserved_under_hash(self):
        b=bundle()
        sel=core.choose(b,core.check_bundle(b),["EVENT-01"],"Select test",NOW)
        sc=script()
        sc["stories"][0]["headline"]="Shocking truth - this is a synthetic news test"
        sc["stories"][0]["narration"]="Today the fictional team reported a fictional event."
        draft=core.draft_manifest(b,sel,sc)
        flags={x["code"] for x in draft["editorial_quality"]["flags"]}
        self.assertIn("SENSATIONAL_LANGUAGE_REVIEW",flags)
        self.assertIn("RELATIVE_TIME_NEEDS_EXPLICIT_CONTEXT",flags)
        self.assertFalse(draft["editorial_quality"]["automatically_verified_news"])
        signed=core.approve_draft(draft,{"confirmed_at":NOW,
          "user_confirmation":"New approval in isolated test only",
          "script_sha256":core.canonical_hash(draft),"approved_story_ids":["EVENT-01"]})
        self.assertEqual(signed["approval_record"]["approved_script_sha256"],core.canonical_hash(draft))
        changed=copy.deepcopy(draft)
        changed["editorial_quality"]["flags"].clear()
        self.assertNotEqual(core.canonical_hash(changed),core.canonical_hash(draft))

    def test_17_quality_is_warning_not_generated_evidence(self):
        out=quality.review({"target_seconds":60,"stories":[
            {"headline":"Test","summary":"Yesterday update","narration":"Test short","claim_ids":["C1"]}]})
        self.assertFalse(out["publication_approved"])
        self.assertFalse(out["automatically_verified_news"])
        self.assertIn("SHORT_NARRATION_EDITORIAL_REVIEW",{x["code"] for x in out["flags"]})

if __name__=="__main__":
    unittest.main()
