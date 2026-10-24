# Dữ liệu chuẩn: bằng chứng → chọn tin → kịch bản → phê duyệt

Lệnh mẫu cần biến $skill, $runtime, $py đã khởi tạo theo references/PORTABILITY_CONTRACT.md; ví dụ dữ liệu là giả lập, không dùng làm phê duyệt thật.

Bộ công cụ đang dùng: `scripts/news_rss.py`, `scripts/source_reader.py`, `scripts/editorial_core.py` và `scripts/news_editor.py`.

## 1. Evidence bundle (EVIDENCE.json)

Ví dụ **giả lập và bị hệ thống chặn trong quy trình sản xuất thật**: `examples/evidence_demo.json`. Dùng nó để kiểm tra quy tắc bảo vệ, KHÔNG dùng làm bản tin.

Mỗi hồ sơ phải gồm:
- `as_of`: ISO-8601 datetime có offset/Z.
- `stories`: list; mỗi story có `id`, `headline`, `summary`, `event_country`, `event_at`, `category`, `confidence`, `confidence_rationale`, `contradictions_unresolved`, `impact_score` (0–5) và `video_fit_score` (0–5).
- `sources`: list các object với `id`, `url` công khai HTTPS, `publisher`, `origin_id`, `source_type` (primary/secondary), `read_confirmed`, `published_at`, `retrieved_at`, `evidence_note`, `syndicated_copy` nếu là bài đăng lại.
- `claims`: list các tuyên bố cụ thể `id`, `text`, `source_ids`; ID nguồn phải tồn tại trong story.
- `confidence`: high, medium, low, unknown. High yêu cầu 2 nguồn đã đọc độc lập cho mỗi claim; low/unknown không đủ điều kiện đề xuất như tin đã xác minh.

Chú ý quan trọng: một bản tin đủ hồ sơ qua kiểm tra máy không đồng nghĩa thông tin đúng ngoài thực tế. Việc xác minh nguồn gốc thực sự và đối chiếu sự kiện phải do AI/người kiểm duyệt đọc bài gốc và ghi căn cứ.

## 2. Kiểm tra evidence

```powershell
& $py -B (Join-Path $skill "scripts\news_editor.py") check --evidence EVIDENCE.json --report REVIEW.json --markdown REVIEW.md
```

- REVIEW.json trả `eligible_for_human_editorial_review`, `factually_verified_by_software=false`, lỗi/khuyến nghị, số nguồn độc lập, claim đã đối chiếu và `editorial_ranking`.
- REVIEW.md để ChatGPT trình người dùng danh sách chọn tin.
- Một tin bị cảnh báo mâu thuẫn, nguồn cùng tổ chức hoặc không đủ chứng cứ phải loại/chờ xác minh.

## 3. Người dùng chọn tin (SELECTION.json)

Sau khi người dùng viết rõ 'Chọn EVENT-A và EVENT-B', AI/Agent gọi:

```powershell
& $py -B (Join-Path $skill "scripts\news_editor.py") select --evidence EVIDENCE.json --ids EVENT-A,EVENT-B --user-message "Tôi chọn EVENT-A và EVENT-B" --confirmed-at "2026-10-23T21:00:00+07:00" --out SELECTION.json
```

- SELECTION.json ở trạng thái `SELECTED_AWAITING_SCRIPT_APPROVAL`.
- KHÔNG tự tạo user-message giả để bỏ qua bước chọn tin.
- Chọn tin chưa có nghĩa đã duyệt lời dẫn và quyền sử dụng media.

## 4. Kịch bản (SCRIPT.json, DRAFT.json)

SCRIPT.json do ChatGPT biên tập **từ những tuyên bố đã kiểm chứng**, cấu trúc như `examples/script_demo.json`; thay toàn bộ demo bằng tin thật. Những trường bắt buộc: `country`, `category`, `language`, `target_seconds`, `aspect_ratio`, `stories[].id`, `headline`, `summary`, `narration`, `claim_ids`.
- target_seconds: 30, 60, 90 hoặc 180.
- aspect_ratio: 9:16 / 16:9 / both. Engine v0.4 sử dụng Remotion để dựng từng tỷ lệ độc lập.
- Mỗi `claim_id` phải tồn tại trong evidence tương ứng.
- Có thể thêm `stories[].visual_plan` với `type` (news_card/infographic/licensed_image/licensed_broll), `instruction`, `claim_ids`. Media ngoài bắt buộc có `license_evidence`, `media_path` tương đối trong thư mục job và `media_sha256` (64 ký tự hex, SHA-256 của đúng file local). AI Agent tính hash sau khi tải media có quyền, kiểm tra lại trước khi tạo draft và trước khi render; thay media phải duyệt lại. Nếu chưa khai, fallback news_card thiết kế nguyên bản, không giả mạo cảnh quay sự kiện.

```powershell
& $py -B (Join-Path $skill "scripts\news_editor.py") draft --evidence EVIDENCE.json --selection SELECTION.json --scripts SCRIPT.json --out DRAFT.json
& $py -B (Join-Path $skill "scripts\news_editor.py") hash --draft DRAFT.json
```

Kết quả DRAFT luôn `status=draft`, `stories[].approved=false`, kể cả khi người dùng đã chọn tin.

## 5. Người dùng duyệt kịch bản (APPROVAL.json)

**Chỉ được tạo file sau khi người dùng thực sự xác nhận toàn văn kịch bản đã trình**, có ghi lại nội dung xác nhận.

Mẫu trường phải có (không đưa file mẫu này vào bước duyệt nếu chưa có xác nhận):

```json
{
  "confirmed_at": "2026-10-23T21:05:00+07:00",
  "user_confirmation": "Nội dung tin nhắn xác nhận thật của người dùng",
  "approved_story_ids": ["EVENT-A", "EVENT-B"],
  "script_sha256": "HASH của DRAFT.json trả về bởi lệnh hash"
}
```

```powershell
& $py -B (Join-Path $skill "scripts\news_editor.py") approve --draft DRAFT.json --confirmation APPROVAL.json --out APPROVED_BRIEF.json
```

- Hệ thống kiểm tra script hash, ID và thứ tự tin. Hash không khớp nghĩa là kịch bản đã thay đổi, phải duyệt lại.
- Chỉ APPROVED_BRIEF.json thật mới có `status=approved` và `stories[].approved=true`.
- Dữ liệu `demo=true` không thể đi qua lệnh select/draft.
- Ngoài quyền duyệt script, media còn cần quyền sử dụng riêng; không được hiểu hai nguồn tin đã cho phép dùng lại ảnh/video.

## 6. Giao cho render
- Khi aspect_ratio=9:16, 16:9 hoặc both, dựng bằng scripts/run_news_video.ps1 sau khi kiểm nguồn, media rights và phê duyệt hash SHA-256. Không thay tỷ lệ của brief đã duyệt.
- Kết quả cuối cùng người dùng tự đăng lên nền tảng, không kết nối API TikTok/YouTube.

## 7. Chống mất dữ liệu
Tất cả lệnh ghi tệp qua chế độ tạo mới, thất bại nếu đích đã tồn tại. Mỗi job một mã và đường dẫn khác nhau; chỉ dọn dữ liệu trung gian khi có quyết định riêng.
