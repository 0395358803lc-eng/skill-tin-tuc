---
name: ai-news-video
version: 1.0.0-rc.2
description: AI Agent nghiên cứu tin tức theo nguồn, hai cổng phê duyệt, Remotion/Piper/FFmpeg 9:16/16:9, QA tự động, khôi phục SRT và bàn giao cho người dùng tự đăng.
---

# AI News Video Skill — nghiên cứu, biên tập, video đa tỷ lệ và QA v1.0.0-rc.2

## Mục tiêu & phạm vi
Khi người dùng yêu cầu tạo video tin tức, ChatGPT đóng vai **tổng biên tập và người điều phối**. Máy Windows local (qua Remote Desktop Commander khi được kết nối) thực thi các chương trình RSS, trích xuất nguồn, kiểm tra bằng chứng, Piper và renderer FFmpeg.

- Giữ kiểm tra độc lập: tin phát hiện ≠ tin đã kiểm chứng ≠ tin được người dùng lựa chọn ≠ kịch bản được người dùng duyệt.
- Phát biểu có tranh cãi phải được dẫn nguồn và trình bày cân bằng. Không sử dụng tiêu đề RSS làm bằng chứng sự kiện.
- **Không đăng video tự động**, không kết nối OAuth/TikTok/YouTube; người dùng tự đăng.
- Renderer v0.4 hỗ trợ **9:16, 16:9 hoặc cả hai** bằng hai bố cục Remotion độc lập. Media phải có quyền sử dụng; chọn tệp theo chính sách bản quyền.

**QUY TẮC PORTABLE (BẮT BUỘC):** Đọc `references/PORTABILITY_CONTRACT.md` trước khi chạy lệnh. Tìm đúng `$skill` chứa `SKILL.md`, xác định `$runtime` ngoài thư mục mã nguồn và `$py` từ venv của runtime. Không giả định ổ D:, ADMIN-PC-02, model, job hay video cũ tồn tại trên máy mới. Báo cáo nghiệm thu lịch sử không thuộc bộ não phát hành.

## Bắt đầu: hiểu yêu cầu tự nhiên
Đọc `references/PORTABILITY_CONTRACT.md`, `references/AGENT_ORCHESTRATION.md`, `references/AGENT_RUNBOOK.md`, `references/STAGE16_17_OPERATIONS.md`, `references/QA_AUTOREPAIR.md`, `references/EDITORIAL_WORKFLOW.md`, `references/NEWS_GATHERING.md`, `references/EVIDENCE_SCHEMA.md` và `references/VIDEO_PRODUCTION.md` trước khi vận hành.

Nếu chưa rõ mới hỏi các tham số: quốc gia/khu vực sự kiện (US, VN, WORLD,...); chuyên mục (general/politics/economy/technology/science/entertainment/sports/environment/health); 6/24/72/168 giờ; ngôn ngữ (vi-VN/en-US); thời lượng 30/60/90/180; định dạng 9:16/16:9/both; phong cách trung tính/nhanh/chuyên sâu. Không hỏi lại những gì người dùng đã nói. Nếu thiếu thông số không quan trọng có thể dùng mặc định nhưng thông báo.

## Quy trình P0–P7 không được bỏ bước

### P0 — Phạm vi nguồn và job
- Xác nhận máy và thư mục chứa SKILL.md thực tế; không ép đường dẫn của máy ADMIN-PC-02 sang máy khác.
- Khởi tạo job bằng `scripts/workflow.py init --country ... --category ... --hours ... --language ... --seconds ... --aspect ...`. Lấy `job_directory` do lệnh trả về. Mỗi job cách ly dữ liệu và có khóa `.stage4.lock` chống hai agent sửa cùng một lúc. Không ghi đè.
- Phân biệt **quốc gia phát sinh sự kiện** và **edition nguồn RSS**; chọn timezone có thể kiểm chứng, ghi ISO8601 offset.

### P1 — Phát hiện RSS/web (chưa xác minh)
- Dùng web tìm nguồn thời sự phù hợp, xem ngày đăng và sự kiện.
- Có thể chạy:
  `& $py -B (Join-Path $skill 'scripts\news_rss.py') --country US --category technology --hours 24 --limit 30 --out (Join-Path $runtime 'output\news-CUSTOMID.json')`
- Có thể bổ sung `--feeds examples/rss_sources.json`. Kiểm tra `feed_results` để không che lỗi nguồn.
- Tạo hàng đợi:
  `python -B scripts/news_editor.py queue --candidates CANDIDATES.json --out QUEUE.json --markdown QUEUE.md --limit 12`.
- Trong Đợt 4, ưu tiên `scripts/workflow.py discover --job <job_directory>` để tự ghi candidates/queue; các tin vẫn **UNVERIFIED**. ChatGPT tiếp tục gom trùng sự kiện có nghĩa tương đương.

### P2 — Đọc nguồn và kiểm chứng claims
- Mở bài gốc bằng web, ưu tiên nguồn sơ cấp, đối chiếu tối thiểu 2 tổ chức/nguồn gốc thực sự độc lập cho mỗi sự kiện.
- Hỗ trợ đọc HTML sơ bộ hợp lệ qua `scripts/source_reader.py` nhưng không coi nội dung trích máy là bằng chứng tuyệt đối; không vượt robots/paywall.
- Mọi tuyên bố có `claims[].source_ids`, lưu `event_at`, `published_at`, `retrieved_at`, `as_of` có múi giờ; ghi `read_confirmed` chỉ khi thực sự đọc.
- Xác định nguồn tổng hợp/copy từ cùng thông cáo. Ghi `origin_id`, `syndicated_copy`; không đánh giá hai URL khác nhau là đã độc lập.
- Đối với chủ đề nhạy cảm tăng kiểm chứng, không đưa cáo buộc thành sự thật.
- Lưu EVIDENCE.json, chạy `news_editor.py check --evidence EVIDENCE.json --report REVIEW.json --markdown REVIEW.md`.
- AI lập EVIDENCE.json từ các nguồn trực tiếp đã đọc; chạy `scripts/workflow.py evidence --job <job_directory> --file <EVIDENCE.json>` để lưu phiên bản bất biến, ghi review.json/md. Máy chỉ kiểm tính đầy đủ nguồn; **AI/người đọc vẫn chịu trách nhiệm xác minh sự kiện**. Tin thiếu căn cứ không được chọn để dựng.

### P3 — Đề xuất để người dùng CHỌN
- Trình **5–12 tin nếu đủ chứng cứ**, hoặc ít hơn, mỗi tin có ID, headline, 1–2 câu mô tả, event_at, địa điểm, ít nhất 2 URL độc lập, confidence, độ phù hợp video và cảnh báo nguồn.
- Ưu tiên độ chính xác, tác động, tính mới, thời lượng và đa dạng; điểm xếp hạng chỉ là gợi ý biên tập, không phải độ chính xác đo đạc hay lượt xem.
- Người dùng có quyền chọn nhiều ID, bỏ/đổi thứ tự, yêu cầu tìm thêm. Không chọn thay người dùng khi họ chưa chọn.
- Khi có thông điệp lựa chọn thực tế, mới ghi SELECTION.json bằng `news_editor.py select --ids ... --user-message ... --confirmed-at ...`.
- Có thể gọi `workflow.py select --job ... --ids ... --user-message <NGUYÊN_VĂN_ĐÚNG_CỦA_NGƯỜI_DÙNG> --confirmed-at <ISO8601>`. SELECTION chỉ ở trạng thái `SELECTED_AWAITING_SCRIPT_APPROVAL`, không tự duyệt script.

### P4 — Soạn kịch bản có claim ID
- Biên tập lời dẫn mới, trung tính, liên kết sự kiện, hook 2–5 giây chính xác, phần thân rõ ai/làm gì/ở đâu/khi nào/tác động.
- Tất cả dữ kiện cần quy chiếu đến claim trong EVIDENCE; không sao chép nguyên văn hàng loạt.
- Lựa chọn `language`, `target_seconds`, `aspect_ratio` giữ nguyên theo yêu cầu. Cả hai tỷ lệ có thể được dựng từ cùng bản ghi đã phê duyệt.
- Ghi SCRIPT.json theo cấu trúc `examples/script_demo.json` nhưng thay **toàn bộ nội dung DEMO bằng tin đã đọc và kiểm chứng**.
- Nếu dùng workflow, gọi `workflow.py draft --job ... --file SCRIPT.json`. Đầu ra draft.json luôn status=draft và approved=false. Media local có giấy phép trong visual_plan bắt buộc có `media_path` tương đối và SHA-256 fingerprint 64 hex; ảnh/video phải tồn tại trong job trước khi phê duyệt.

### P5 — Người dùng DUYỆT kịch bản
- Trình toàn bộ kịch bản và nguồn; kiểm tra sự thay đổi của tin mới và quyền media.
- Chỉ khi người dùng **thực sự chấp thuận** mới lưu APPROVAL.json với tin nhắn duyệt, thời điểm, danh sách story ID và hash chính xác của DRAFT.
- Hash: `news_editor.py hash --draft DRAFT.json`. Phê duyệt: `news_editor.py approve --draft DRAFT.json --confirmation APPROVAL.json --out APPROVED_BRIEF.json`.
- Khi DRAFT đổi, hash cũ không hợp lệ và phải xin phê duyệt lại. **Không tự làm giả tin nhắn của người dùng**.
- Với workflow, gọi `workflow.py approve --job ... --confirmation CONFIRMATION.json` **chỉ sau** khi người dùng duyệt thật. Không tự tạo xác nhận giả. Không duyệt nội dung DEMO. Hai giai đoạn lựa chọn và phê duyệt là hai quyết định khác nhau.

### P6 — Dựng video đã duyệt
- Chạy `python -B scripts/doctor.py` hoặc tài liệu INSTALL_WINDOWS trước khi dựng. Trên Windows mới, đọc `references/WINDOWS_BOOTSTRAP.md` và chạy `scripts/bootstrap_windows.ps1 -CheckOnly` trước khi cài; `doctor.py` phải báo `ready_dual_aspect=true`, encoder NVENC hoặc CPU đã qua phép thử H.264 thật.
- Renderer v0.4 hỗ trợ 9:16, 16:9 và both. Kiểm tra runtime Remotion/Chrome/FFmpeg/Piper trước khi dựng bằng `scripts/setup_remotion.ps1` và `scripts/doctor.py`.
- Với job được người dùng duyệt, ưu tiên `workflow.py render --job <job_directory> --encoder auto --speech-rate 1.0`. Chỉ được retry tối đa một lần sang CPU khi xác nhận lỗi GPU/NVENC; không được tự đổi nội dung/tỷ lệ hay bỏ qua bản quyền. `run_news_video.ps1` vẫn có thể dùng để dựng độc lập theo approved brief.
- Piper TTS ngoại tuyến với model có quyền sử dụng; Remotion dựng đồ họa động/timeline; FFmpeg mã hóa cuối bằng NVENC nếu tương thích, CPU fallback. Hình/B-roll phải gắn `license_evidence` và đường dẫn local an toàn.

### P7 — QA, bàn giao và lưu hồ sơ
- Chạy `workflow.py qa --job <job_directory>`: kiểm codec/FPS/audio, độ dài, SRT, ảnh frame mẫu, nguồn/rights ledger. Chỉ cho phép tự tái tạo SRT từ cues Remotion vào thư mục MỚI rồi chạy QA lại; không chỉnh sửa video gốc hoặc script. Nếu lỗi không thể sửa, dừng.
- Nếu tin thay đổi, quay lại P2 và xin người dùng duyệt lại. Không tự nhận đã kiểm tra khi chưa làm.
- Khi QA kỹ thuật đạt và không phải DEMO, chạy `workflow.py handoff --job <job_directory>` tạo handoff.json với checksum, video MP4, SRT, sources.json, metadata, media_rights.json và báo cáo. Trạng thái `AWAITING_HUMAN_FINAL_REVIEW`: người dùng phải xem/nghe và kiểm nguồn/bản quyền trước khi **tự đăng**.

## Kiểm chứng sản xuất và benchmark (Đợt 5 / Giai đoạn 14–15)
- Trên ADMIN-PC-02 đã chạy kiểm thử ngắn và dài **bằng nội dung DEMO giả lập**; script `scripts/stage5_fixture.py` chỉ tạo DEMO, không tạo tin thật. Dùng `scripts/stage5_benchmark.py` (psutil tùy chọn) để đo tổng thời gian, nhóm tiến trình/RAM, GPU sử dụng, chất lượng/độ dài thực tế.
- Piper được tối ưu cache model ONNX trong một tiến trình Python, tránh nạp lại cho từng cụm. Lựa chọn backend legacy `PIPER_BACKEND=subprocess` chỉ dùng kiểm tra tương thích, mặc định inprocess.
- Để thử nghiệm video dài, `video_pipeline.py --demo-sample-every 5`/`10` được phép **chỉ với demo=true**. Remotion lấy ít frame hơn, FFmpeg lặp frame lên 30 FPS đầu ra; đây là stress-test timeline/audio/SRT và **không tương đương chất lượng hoạt ảnh 30 FPS gốc**. Không được bật chế độ này cho tin thật.
- `qa_engine.py` bổ sung cảnh báo video quá ngắn so với mục tiêu, phần trăm thời lượng có phụ đề thấp, và DEMO lấy mẫu frame. Kết quả QA kỹ thuật không phải phê duyệt nội dung hoặc quyền sử dụng.
- Giai đoạn 14 chỉ hoàn tất bản tin thật sau khi người dùng **chọn ID sự kiện** và **duyệt toàn văn script**; tuyệt đối không lấy lệnh nâng cấp Skill làm hai xác nhận này. Nếu chưa có xác nhận, duy trì job ở `AWAITING_SELECTION`/`AWAITING_APPROVAL` và báo trạng thái trung thực.

## Kiểm thử thời lượng và độ ổn định (Giai đoạn 15)
- Đọc references/STAGE15_OPERATIONS.md khi kiểm thử video dài. Báo cáo nghiệm thu lịch sử nằm ngoài gói phát hành.
- **TRƯỚC P4 draft đóng băng/hash và P5 người dùng phê duyệt**: `scripts/duration_planner.py` ước tính nhanh và `scripts/tts_duration_preflight.py` tổng hợp WAV Piper thực bằng `--input SCRIPT_CANDIDATE.json --out NEW_DIR`; kiểm thời lượng trong ±5%. Không được auto-thay nội dung đã duyệt, không dùng padding im lặng/lặp frame để giả đạt thời gian.
- `scripts/stage15_duration_calibrate.py` điều chỉnh **DEMO-only** 30/60/90/180 bằng Piper trước khi render; dữ liệu đầu ra ở runtime, watermark không được đăng. `scripts/stage5_benchmark.py` đo runtime, RAM cây tiến trình, GPU **toàn thiết bị**. Khi launcher/benchmark treo, kiểm tra PID chỉ của job; không dừng việc khác.
- `scripts/stage15_stability.py` kiểm native QA nhiều lần, SRT/MP4 hỏng/thiếu, SHA-256 không đổi; `scripts/stage15_encoder_benchmark.py` so sánh ngắn CPU/NVENC; `scripts/stage15_acceptance.py` chặn hoàn tất nếu còn hồ sơ native dài sai lệch thời lượng hoặc QA lỗi. Kết quả thực nghiệm không thay thế kiểm nguồn, bản quyền và duyệt người dùng.
- Skill có thể chuyển máy, nhưng benchmark trước đây gắn dataset runtime trên ADMIN-PC-02; ở máy khác cần bootstrap công cụ và tạo dataset thử mới. Không đóng gói môi trường, benchmark logs hoặc DEMO MP4 vào bộ Skill.

## Bảo vệ hệ thống
1. Không dùng dữ liệu ví dụ, URL .example, media không có quyền trong tin thật.
2. Đường dẫn data, output và job phải riêng, không ghi đè.
3. Không lưu token, mật khẩu hay thông tin bí mật trong project.
4. Không đưa ý kiến biên tập/điểm xếp hạng thành sự thật và không dự báo viral.
5. Dựng 9:16 và 16:9 độc lập, không giả chuyển tỷ lệ, không sửa approved manifest sau khi người dùng đã duyệt.
6. Giữ backup Đợt 1, log và intermediate khi chưa nghiệm thu xong.

## Tham chiếu
- `README.md` — trạng thái khả năng thực tế và ví dụ lệnh.
- `references/PORTABILITY_CONTRACT.md` — hợp đồng đường dẫn và runtime trên máy mới.
- `references/STAGE2_WORKFLOW_CONTRACT.md`, `references/STAGE3_RESEARCH_CONTRACT.md`, `references/STAGE4_AV_QUALITY_CONTRACT.md`, `references/STAGE5_QA_ACCEPTANCE.md`, `references/STAGE6_RELEASE_AND_WINDOWS_GATE.md` — giới hạn cảnh chung, nhạc/từ điển SHA-256 được duyệt, checkpoint render, chặn phục hồi không an toàn và tách hai xác nhận người dùng.
- `references/AGENT_ORCHESTRATION.md` — tiếp nhận ngôn ngữ tự nhiên, tách job nhiều phiên, P0–P7 và phục hồi an toàn.
- `references/TRANSFER_ZIP_WINDOWS.md` — đóng ZIP thủ công, danh sách SHA-256 và xác minh sau khi chuyển máy.
- `RELEASE_MANIFEST_SHA256.json` cùng `scripts/release_manifest.py` — bộ kiểm chứng nguyên vẹn nguồn, **không chứng nhận GA**.
- `scripts/agent_bridge.py` — nhận yêu cầu và xem danh sách/trạng thái job (chỉ-đọc, không tự tạo phê duyệt).
- `references/NEWS_GATHERING.md` — nguồn và độ tin cậy.
- `references/EVIDENCE_SCHEMA.md` — dữ liệu và công cụ bảo vệ hai lớp duyệt.
- `references/EDITORIAL_WORKFLOW.md` — trải nghiệm lựa chọn/phê duyệt.
- `references/INSTALL_WINDOWS.md` — runtime máy local.
- `references/VIDEO_PRODUCTION.md` — tiêu chuẩn renderer và media.
- `scripts/news_rss.py`, `scripts/source_reader.py`, `scripts/news_editor.py`, `scripts/editorial_core.py` — công cụ research/editorial.
- `scripts/video_pipeline.py`, `scripts/run_news_video.ps1`, `scripts/setup_remotion.ps1`, `remotion-template/` — dựng động 9:16/16:9/both; `scripts/render_video.py` và `run_local.ps1` là engine legacy 9:16; `scripts/doctor.py` kiểm tra runtime.
- `scripts/media_catalog.py` tìm ứng viên ảnh/clip từ Wikimedia Commons và thông tin giấy phép, **chưa tự phê duyệt quyền sử dụng**.
- `scripts/workflow.py` quản lý job bền vững từ thu thập đến bàn giao, có `status`/`resume`, nhật ký và khóa không ghi đè.
- `scripts/qa_engine.py`, `scripts/qa_repair.py` kiểm tra file MP4/SRT thật và chỉ sửa SRT an toàn vào output mới. `references/AGENT_RUNBOOK.md` và `references/QA_AUTOREPAIR.md` là hướng dẫn điều phối.

## Ưu tiên 2 — Đợt 6, Giai đoạn 16–17 (v0.6.0)
- Đọc references/STAGE16_17_OPERATIONS.md về giới hạn kiểm thử và cơ chế checkpoint; dùng workflow.py status/resume để nhận biết trạng thái và khóa trước khi tiếp tục.
- checkpoint SHA-256 + atomic JSON đã được tích hợp trong workflow.py cho JOB MỚI. Nếu crash xuất hiện attempt-* nhưng thiếu render_result.json, không render ghi đè: dùng reconcile-render CHỈ cho output hoàn chỉnh có đúng approved.json và QA độc lập; còn lại giữ nguyên để điều tra.
- Khóa stale chỉ được phục hồi bằng lệnh recover-lock sau xác minh PID thật sự không còn; tuyệt đối không cướp khóa ACTIVE hoặc UNKNOWN. Khi approved.json thay đổi, dừng và xin phê duyệt lại, không tự suy ra từ trạng thái trước.
- Discover tin qua Google News và feed theo chủ đề US technology, giới hạn tối đa 12 ứng viên; research_screening.json CHỈ LÀ RSS UNVERIFIED. Bước evidence kiểm từng claim theo hai nguồn độc lập đã đọc, origin/ownership_group/syndication, event_at và nguồn published/retrieved. stage17_evidence_review.json/md chứa báo cáo.
- Trình đúng những tin thực sự đủ chứng cứ để người dùng chọn; nếu dưới 5 không tạo tin thêm. Người dùng vẫn chọn ID, duyệt chính xác draft hash, xem/nghe trước khi tự đăng. Không gọi RSS hoặc metadata là xác nhận chân lý.

## Ưu tiên 3 — Đợt 7 / Giai đoạn 18–19 (v0.7.0)
- Đọc `references/STAGE18_19_OPERATIONS.md` trước khi thực hiện. Trước khi người dùng duyệt kịch bản thật phải đo WAV Piper (preflight), kiểm thuật ngữ, từ điển cách đọc nếu có, và trình bản nháp đúng hash. Không sửa bản đã duyệt.
- Stage18: `narration_quality.py` kiểm các cue dựa vào thời gian WAV thật, `voice_qa.json` chứa cảnh báo số/tên riêng; Remotion có word-highlight theo **ước lượng trong từng chunk** (không forced alignment). QA giọng cần con người nghe lại; SRT vẫn giữ nguyên lời dẫn đã phê duyệt. Nhạc chỉ dùng khi có giấy phép, loudnorm và ducking.
- Stage19: `smart_media.py` và OpenCV/Pillow trên máy local. Chỉ bật `smart_crop:true` ở visual_plan trước khi user duyệt. Cần local media được duyệt, hash SHA-256, license_evidence, author, source_url, license_name, attribution. Tọa độ focal_x/y được biên tập viên chọn có ưu tiên cao hơn Smart Crop tự động. Trường hợp độ tin cậy thấp phải xem lại cả 9:16 và 16:9, tuyệt đối không ghép hình sai tin hay tự cấp quyền thương mại.
- Khi xuất xong, xem `voice_qa.json`, `smart_crop_report.json`, SRT, MP4, `qa_report.json` và chạy QA độc lập. Nội dung DEMO không được đăng và không kết nối API TikTok/YouTube.

## Đợt 8 — Giai đoạn 20, phong cách Remotion v0.8.0
- Trước khi xin người dùng DUYỆT exact script SHA256, cho người dùng chọn visual_style: quick, roundup hoặc deep_dive. Giá trị preset nằm trong draft, không sửa sau duyệt.
- Đọc references/STAGE20_OPERATIONS.md. Màu sắc, intro/outro, chuyển cảnh và safe-area riêng 9:16/16:9 được kiểm trước render. Không cắt tiêu đề để che lỗi bố cục.
- Sau render kiểm visual_design.json, qa_report.json, hai MP4/SRT và các frame có infographic. Các cảnh báo long-copy yêu cầu kiểm mắt. DEMO không được đăng.
- Audio/claim/media approval workflow cũ phải giữ nguyên. Giai đoạn 21 chưa được nghiệm thu; không tự công bố v1.0.0.

## Release Candidate v1.0.0-rc.2 — Giai đoạn 21
- Đọc references/STAGE21_RELEASE_CHECKLIST.md; RC chưa phải GA vì chưa có kiểm thử thành công trên Windows độc lập.
- Source audit bằng scripts/release_audit.py; cài lại dùng scripts/bootstrap_windows.ps1 trong runtime riêng, không động chạm các job khác.
- QA tin THẬT lỗi nếu MP4 lệch thời lượng trên ±5%; không nới ngưỡng để che lỗi. Có thể dựng lại với nhịp đọc Piper đã đo mà giữ nguyên từng chữ approved.json, vào output folder mới.
- Ưu tiên sự kiện có nguồn mới đã đọc, người dùng chọn tin và duyệt exact SHA-256 kịch bản gồm cả visual_style. Chỉ chuyển video cho người dùng để họ xem/nghe/xác minh và TỰ ĐĂNG; không auto-publish hoặc tự cấp quyền bản quyền.
