#!/usr/bin/env python3
"""Editorial command-line gates. AI drafts and humans decide; software cannot know truth."""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from pathlib import Path
import editorial_core as core

def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8-sig'))

def preview_candidates(data: dict, limit: int = 12) -> tuple[dict, str]:
    now = core.timestamp(data['collected_at'], 'collected_at')
    total = max(1, data.get('hours', 24))
    entries = []
    for i, obj in enumerate(data.get('candidates', [])):
        try:
            pub = core.timestamp(obj['published_at'], 'published_at')
        except (KeyError, ValueError):
            continue
        hours = max(0, (now - pub).total_seconds() / 3600)
        freshness = max(0, 1 - hours / total)
        # Editorial importance requires contextual judgment. Do not invent it from RSS.
        score = round(freshness * 20, 2)
        entries.append({'id': obj['id'], 'headline': obj['headline'],
                        'published_at': obj['published_at'], 'rss_link': obj['rss_link'],
                        'source': obj.get('source', ''), 'candidate_count': obj.get('candidate_count', 1),
                        'discovery_freshness_points': score,
                        'discovery_priority_score': data.get('stage17_priority',{}).get(obj['id'],score),
                        'verification': 'UNVERIFIED',
                        'event_at': None, 'event_country': None,
                        'impact_score': None, 'video_fit_score': None, 'confidence': 'unknown'})
    entries.sort(key=lambda x: (-x['discovery_priority_score'],x['id']))
    chosen = entries[:limit]
    queue = {'status': 'UNVERIFIED_EDITORIAL_QUEUE', 'as_of': data['collected_at'],
             'country': data['country'], 'category': data['category'],
             'ranking_method': 'RSS publication age plus tentative publisher diversity; NOT verified truth or independent news reporting',
             'stories': chosen}
    lines = ['# Ứng viên tin — CHƯA KIỂM CHỨNG', '',
             'Các tiêu đề RSS dưới đây chỉ để khám phá sự kiện. Không suy luận nội dung từ tiêu đề, không đưa lên video khi chưa đọc và đối chiếu bài gốc.',
             '', 'Khu vực nguồn tin: ' + data['country'] + '; chuyên mục: ' + data['category'],
             'Thời điểm thu thập: ' + data['collected_at'], '']
    for index, item in enumerate(chosen, 1):
        url = item['rss_link']
        lines += [f"## {index:02d} — {item['headline']}", f"ID: {item['id']}",
                  f"Nguồn RSS: {item['source']} | Xuất bản: {item['published_at']}",
                  f"Phát hiện: {item['candidate_count']} tiêu đề tương tự | Tin: CHƯA XÁC MINH",
                  f"Điểm khám phá (không phải xác suất đúng): {item['discovery_priority_score']} / 100",
                  f"Link tham chiếu: {url}", '']
    return queue, '\n'.join(lines)

def preview_evidence(bundle: dict, report: dict) -> str:
    indexed = core.story_index(bundle)
    lines = ['# Danh sách thẩm định tin — chưa phải phê duyệt xuất bản', '',
             'Phần mềm chỉ kiểm tra dấu vết bằng chứng; tổng biên tập AI và người dùng cần đọc nguồn, kiểm chứng thông tin và quyết định sử dụng.',
             '', 'Thời điểm hồ sơ: ' + bundle['as_of'], '']
    priority = {x['id']: x['editorial_priority_score'] for x in report.get('editorial_ranking', [])}
    ordered = sorted(report['story_reports'],
                     key=lambda x: (x['eligible_for_human_editorial_review'], priority.get(x['id'], -1)), reverse=True)
    for x in ordered:
        story = indexed.get(x['id'], {})
        status = 'ĐỦ HỒ SƠ ĐỂ NGƯỜI DUYỆT XEM' if x['eligible_for_human_editorial_review'] else 'CHỜ BỔ SUNG / KHÔNG ĐỦ BẰNG CHỨNG'
        score_note = ('Ưu tiên biên tập (ước lượng, không phản ánh xác suất đúng): ' + str(priority[x['id']]) + '/100') if x['id'] in priority else 'Chưa có điểm ưu tiên do thiếu bằng chứng'
        lines += [f"## {x['id']} — {story.get('headline','')}",
                  'Trạng thái: ' + status, score_note,
                  'Tóm tắt: ' + story.get('summary', ''),
                  'Sự kiện: ' + str(story.get('event_at', '')) + ' / ' + str(story.get('event_country', '')),
                  'Độ chính xác thời điểm sự kiện: ' + str(story.get('event_time_precision','not supplied')),
                  'Lưu ý biên tập: ' + str(story.get('editorial_caution','Không có lưu ý bổ sung')),
                  f"Độ tin cậy do biên tập viên khai báo: {story.get('confidence','unknown')}",
                  f"Nguồn đã đọc: {x['reviewed_source_count']}; nguồn độc lập theo hồ sơ: {x['independent_origins']}", '']
        for src in story.get('sources', []):
            lines.append(f"- {src.get('publisher','?')}: {src.get('url','')} ({src.get('published_at','')})")
        if x['errors']:
            lines += ['Lỗi: ' + '; '.join(x['errors'])]
        if x['warnings']:
            lines += ['Cảnh báo: ' + '; '.join(x['warnings'])]
        lines.append('')
    return '\n'.join(lines)

def write_markdown(path: Path, md: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        f.write(md + '\n')

def main() -> None:
    ap = argparse.ArgumentParser(description='News evidence workflow (AI + human approval required)')
    sub = ap.add_subparsers(dest='command', required=True)
    queue = sub.add_parser('queue', help='Convert RSS candidates into UNVERIFIED ranked shortlist')
    queue.add_argument('--candidates', type=Path, required=True)
    queue.add_argument('--out', type=Path, required=True)
    queue.add_argument('--markdown', type=Path, required=True)
    queue.add_argument('--limit', type=int, default=12)
    check = sub.add_parser('check', help='Check source provenance and claim evidence, NOT truth')
    check.add_argument('--evidence', type=Path, required=True)
    check.add_argument('--report', type=Path, required=True)
    check.add_argument('--markdown', type=Path, required=True)
    select = sub.add_parser('select', help='Persist exact human choices after a user message')
    select.add_argument('--evidence', type=Path, required=True)
    select.add_argument('--ids', required=True, help='comma-separated story IDs')
    select.add_argument('--user-message', required=True)
    select.add_argument('--confirmed-at', required=True)
    select.add_argument('--out', type=Path, required=True)
    draft = sub.add_parser('draft', help='Assemble unapproved script from AI-authored, claim-linked words')
    draft.add_argument('--evidence', type=Path, required=True)
    draft.add_argument('--selection', type=Path, required=True)
    draft.add_argument('--scripts', type=Path, required=True)
    draft.add_argument('--out', type=Path, required=True)
    digest = sub.add_parser('hash', help='Hash exact draft manifest for approval')
    digest.add_argument('--draft', type=Path, required=True)
    approve = sub.add_parser('approve', help='Finalize only with exact external human confirmation')
    approve.add_argument('--draft', type=Path, required=True)
    approve.add_argument('--confirmation', type=Path, required=True)
    approve.add_argument('--out', type=Path, required=True)
    opts = ap.parse_args()
    try:
        if opts.command == 'queue':
            if not 1 <= opts.limit <= 12:
                raise ValueError('limit must be 1..12')
            data, markdown = preview_candidates(read(opts.candidates), opts.limit)
            core.write_new(opts.out, data)
            write_markdown(opts.markdown, markdown)
            summary = {'status': data['status'], 'count': len(data['stories'])}
        elif opts.command == 'check':
            data = read(opts.evidence)
            result = core.check_bundle(data)
            core.write_new(opts.report, result)
            write_markdown(opts.markdown, preview_evidence(data, result))
            summary = {'status': result['status'], 'eligible_count': result['eligible_count'],
                       'story_count': result['story_count']}
        elif opts.command == 'select':
            data = read(opts.evidence)
            report = core.check_bundle(data)
            ids = [x.strip() for x in opts.ids.split(',') if x.strip()]
            chosen = core.choose(data, report, ids, opts.user_message, opts.confirmed_at)
            core.write_new(opts.out, chosen)
            summary = {'status': chosen['status'], 'selected': chosen['story_ids']}
        elif opts.command == 'draft':
            data = read(opts.evidence)
            report = core.check_bundle(data)
            selected = read(opts.selection)
            for sid in selected['story_ids']:
                entry = next((x for x in report['story_reports'] if x['id'] == sid), None)
                if not entry or not entry['eligible_for_human_editorial_review']:
                    raise ValueError('evidence changed or no longer eligible: ' + sid)
            new = core.draft_manifest(data, selected, read(opts.scripts))
            core.write_new(opts.out, new)
            summary = {'status': new['status'], 'stories': len(new['stories']),
                       'script_sha256_for_approval': core.canonical_hash(new),
                       'note': 'A human must review exact script and confirm before approve command.'}
        elif opts.command == 'hash':
            summary = {'script_sha256': core.canonical_hash(read(opts.draft))}
        elif opts.command == 'approve':
            approved = core.approve_draft(read(opts.draft), read(opts.confirmation))
            core.write_new(opts.out, approved)
            summary = {'status': approved['status'], 'stories': len(approved['stories']),
                       'aspect_ratio': approved['aspect_ratio'],
                       'note': 'Only 9:16 renderer exists in v0.3; 16:9 waits for Stage 10.'}
        print(json.dumps(summary, ensure_ascii=False))
    except (ValueError, KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
        ap.exit(2, 'EDITORIAL_ERROR: ' + str(exc) + '\n')

if __name__ == '__main__':
    main()
