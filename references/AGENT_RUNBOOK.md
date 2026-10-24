# AGENT RUNBOOK — ChatGPT điều phối AI News Video Skill v1.0.0-rc.2

**HỢP ĐỒNG PORTABLE:** Trước mọi lệnh trên máy mới, đọc `references/PORTABILITY_CONTRACT.md` và `references/AGENT_ORCHESTRATION.md`. Các lệnh dưới đây dùng `$skill`, `$runtime`, `$py` thay cho đường dẫn máy phát triển.

## Trách nhiệm và giới hạn
ChatGPT là người điều phối tin tức, đọc nguồn, biên tập, trình người dùng lựa chọn và phê duyệt. Remote Desktop Commander chỉ thực thi trên máy đã được cấp quyền; workflow không tự xác minh sự thật, không giả phê duyệt, và **không tự đăng**.

- Skill: thư mục hiện có `SKILL.md`.
- Runtime: `$env:NEWS_SKILL_RUNTIME` hoặc thư mục sibling `"$skill-runtime"`.
- Python: `$runtime\.venv\Scripts\python.exe`.
- Workflow: `$skill\scripts\workflow.py`.
- Jobs: `$runtime\jobs\<job_id>`; mỗi job tách biệt.

## Chuẩn bị mỗi phiên Agent
Mở PowerShell tại thư mục chứa `SKILL.md`, khai báo:

```powershell
$skill = (Resolve-Path .).Path
if (-not (Test-Path (Join-Path $skill 'SKILL.md'))) { throw 'Not a Skill root' }
$runtime = if ($env:NEWS_SKILL_RUNTIME) { $env:NEWS_SKILL_RUNTIME } else { "$skill-runtime" }
$py = Join-Path $runtime '.venv\Scripts\python.exe'
$env:NEWS_SKILL_RUNTIME = $runtime
if (-not (Test-Path $py)) { throw 'Missing isolated runtime: follow INSTALL_WINDOWS.md' }
```

Khi vận hành trên máy mới, đọc thêm `references/WINDOWS_BOOTSTRAP.md` và chạy `bootstrap_windows.ps1 -CheckOnly` trước cài đặt. Nếu doctor chưa PASS thì không khởi tạo job. Các chuỗi `<...>` chỉ là placeholder; lấy đường dẫn `job_directory` do lệnh init trả về cho đúng tab Agent.

## P0 — tiếp nhận yêu cầu
Trích quốc gia nơi xảy ra tin (US/VN/WORLD...), chuyên mục, 6/24/72/168 giờ, ngôn ngữ vi-VN/en-US/en-GB, thời lượng 30/60/90/180, tỷ lệ 9:16/16:9/both, phong cách. Nếu người dùng đã nói, không hỏi lại. Khi các thông số không quan trọng còn thiếu có thể dùng mặc định và phải thông báo.

Tạo job bằng công cụ trên máy:
  & $py -B "$skill\scripts\workflow.py" init --country US --category technology --hours 24 --language vi-VN --seconds 60 --aspect both

Đọc đường dẫn job_directory mà chương trình trả về, không tự đoán mã. Khi có nhiều tab ChatGPT, chỉ chạy trên đúng job_directory của tab hiện tại. .stage4.lock ngăn hai tiến trình sửa cùng một job đồng thời.

## P1 — tin ứng viên
  & $py -B "$skill\scripts\workflow.py" discover --job <job_directory>

Đọc queue.md + candidates.json + feed_results. Đây là tin CHƯA KIỂM CHỨNG, không trình tiêu đề RSS như dữ kiện thực. Dùng công cụ web và nguồn chính thức để mở bài gốc; phân biệt quốc gia xuất bản RSS với quốc gia sự kiện. Đối chiếu nguồn sơ cấp và tối thiểu hai tổ chức thực sự độc lập, không lấy tin đăng lại làm bằng chứng thứ hai.

## P2 — nghiên cứu bằng chứng
AI viết EVIDENCE.json từ nội dung THỰC SỰ đã đọc, theo references/EVIDENCE_SCHEMA.md; từng tuyên bố có ID và source_ids, thời gian sự kiện/đăng/đọc có timezone. Không tự đánh dấu read_confirmed=true khi chỉ xem tiêu đề/snippet. Nêu rõ mâu thuẫn, thiếu dữ kiện và quyền ảnh nếu có.
  & $py -B "$skill\scripts\workflow.py" evidence --job <job_directory> --file <EVIDENCE.json>

Đọc review.md, review.json. Nếu NEEDS_EVIDENCE, không tiến tới chọn. Dữ liệu evidence đã ghi bất biến; khi phải sửa nội dung sau ghi, tạo job mới với thời điểm kiểm chứng lại, không ghi đè file cũ.

## P3 — người dùng CHỌN sự kiện
Trình danh sách ID, headline, mô tả ngắn, nguồn gốc, event_at và hai link độc lập đã đọc, cảnh báo và mức độ chắc chắn. Người dùng được chọn nhiều ID, thay thứ tự, bỏ hoặc yêu cầu tìm thêm. Chờ người dùng thực sự chọn. Tuyệt đối không tạo lời lựa chọn giả trong test.
  & $py -B "$skill\scripts\workflow.py" select --job <job_directory> --ids EVENT-A,EVENT-B --user-message '<NGUYÊN VĂN LỰA CHỌN THẬT CỦA NGƯỜI DÙNG>' --confirmed-at '<ISO8601 có timezone>'

## P4 — kịch bản
AI viết SCRIPT.json mới dựa vào đúng sự kiện đã chọn và nguồn đã đọc, giữ country/category/language/target_seconds/aspect_ratio của job. **Trước khi chạy `workflow.py draft` đóng băng script**, bắt buộc ước tính nhanh bằng `scripts/duration_planner.py --brief SCRIPT.json --out DURATION_ADVISORY_UNIQUE.json`; nếu model Piper đã có, chạy thêm **đo giọng đọc thực tế** `scripts/tts_duration_preflight.py --input SCRIPT.json --out <NEW_RUNTIME_PREFLIGHT_DIR>` (không phải approved.json). Nếu lệch quá 5%, hãy CHỈNH SCRIPT.json còn chưa duyệt rồi chạy preflight lại trong thư mục MỚI; không bù giọng đọc bằng cách lặp frame hay đệm khoảng im lặng. Chỉ sau khi độ dài hợp lý mới gọi `workflow.py draft`; bước này ghi `duration_advisory.json` và trả `script_sha256`. Một bản draft đã đóng băng muốn thay đổi cần lập bản nháp/job mới, không sửa nội dung đã duyệt. Khi thiếu Piper hoặc model khác nhau, cảnh báo độ dài thực chưa kiểm chứng, không được tự nhận PASS. Không tự bịa con số và nội dung tuyên bố. Trong mỗi story, visual_plan có claim_ids, từng media phải có license_evidence, đường dẫn tương đối trong thư mục job, fingerprint SHA-256 64 hex do AI đọc từ file đã cấp phép. Trước khi cho phép ảnh/B-roll cần xác nhận nguồn/copyright.
  & $py -B "$skill\scripts\workflow.py" draft --job <job_directory> --file <SCRIPT.json>

Đọc draft.json, lấy script_sha256. Trình toàn văn, chỉ rõ tỷ lệ, độ dài, tên riêng và mọi nguồn cho người dùng xem.

## P5 — người dùng DUYỆT kịch bản
Đây là bước khác với chọn tin ở P3. Chỉ sau khi người dùng chấp thuận toàn văn mới tạo CONFIRMATION.json gồm confirmed_at, user_confirmation là tin nhắn người dùng thật, approved_story_ids đúng thứ tự, script_sha256 từ draft đã xem. Nếu sửa một từ/phụ đề/claim/tỷ lệ hoặc media, phải tạo job mới hoặc xin phê duyệt lại bản draft/hash phù hợp.
  & $py -B "$skill\scripts\workflow.py" approve --job <job_directory> --confirmation <CONFIRMATION.json>

approved.json có approval_record SHA-256. Không dùng xác nhận nhân tạo, dữ liệu DEMO hoặc URL ví dụ để phát hành.

## P6 — tạo hai định dạng
  & $py -B "$skill\scripts\doctor.py"
  & $py -B "$skill\scripts\workflow.py" render --job <job_directory> --encoder auto --speech-rate 1.0

Engine dùng Remotion + Piper + FFmpeg; auto chọn NVENC nếu chạy được, CPU fallback nếu NVENC lỗi kỹ thuật. Chỉ tự thử lại tối đa một lần khi lỗi định danh là GPU/NVENC. Hai attempt nằm riêng để giữ log và file hỏng. Các lỗi nguồn/bản quyền/phê duyệt/script không được tự thử lại để lách.

## P7 — QA, sửa lỗi an toàn và bàn giao
  & $py -B "$skill\scripts\workflow.py" qa --job <job_directory>
  & $py -B "$skill\scripts\workflow.py" status --job <job_directory>

QA máy: ffprobe H264/AAC, 30FPS, 1080x1920/1920x1080, audio/silence, duration, SRT timeline, ảnh frame giữa mỗi sự kiện và một số điểm timeline, hồ sơ quyền, hash. Với tin thật, sai lệch thời lượng quá ±5% mục tiêu là QA FAIL; cảnh báo biên tập không thay thế xác nhận được đăng. Chỉ nghiệm thu native30 nếu renderer không dùng `--demo-sample-every` và `remotion_frame_sampling_step=1`. Auto-repair chỉ tái tạo SRT từ props/Remotion cues, ghi sang thư mục mới và QA lại. Không sửa lời dẫn hoặc nguồn. Khi lỗi không được phép sửa, dừng và thông báo.
Sau khi QA kỹ thuật đạt và không phải DEMO:
  & $py -B "$skill\scripts\workflow.py" handoff --job <job_directory>

Trả handoff.json và đường dẫn video, SRT, sources.json, publishing_metadata.json, media_rights.json, báo cáo QA và checksum. Trạng thái bàn giao: AWAITING_HUMAN_FINAL_REVIEW. Trước khi tự đăng, người dùng phải xem/nghe video, kiểm chứng tin mới cập nhật, quyền media/giọng/nhạc và tuân thủ nền tảng. Không thực hiện auto-upload.

## Khi gián đoạn, mất mạng hoặc mất điện
- Chạy workflow.py status trên đúng job để khôi phục ngữ cảnh và đọc các artifact bất biến.
- Nếu .stage4.lock tồn tại, KHÔNG tự xóa khi có thể còn tiến trình chạy. Kiểm tra danh sách process/log trên Remote Desktop Commander; chỉ can thiệp thủ công khi chắc chắn tiến trình dừng.
- Các file intermediate/log từ lần thất bại không bị tự xóa; đầu ra phải dùng attempt mới, tránh ghi đè.
- Nếu RSS đã quá cũ hoặc bài gốc cập nhật: job mới và kiểm tra/phê duyệt lại. Không tự sửa approved.json.
- Không có khả năng chạy tác vụ khi ChatGPT chưa được người dùng gọi hoặc công cụ Remote Desktop Commander không kết nối. Workflow duy trì trạng thái trên ổ đĩa; việc tiếp tục do AI Agent điều phối.

## Những gì hệ thống KHÔNG được khẳng định
- Vượt QA kỹ thuật ≠ tin tức đã đúng, quyền media đã được cấp, video đã được xem/nghe toàn bộ hoặc được phép đăng.
- Remotion không phải công cụ duy nhất dùng GPU; NVENC chỉ tăng tốc mã hóa MP4 cuối nếu thiết bị tương thích.
- Công cụ sửa SRT không phải tự sửa mọi lỗi; video hỏng, claim sai và mất phê duyệt phải chuyển ngược quy trình.

## Stage 16–17 (v0.6.0) — Chống gián đoạn và nghiên cứu nguồn nâng cao
Đọc references/STAGE16_17_OPERATIONS.md trước khi khởi chạy công việc mới. workflow.py status/resume hiển thị kiểm tra checkpoint và khóa. Khi checkpoint báo NEEDS_MANUAL_RECOVERY, approved.json bị đổi hoặc attempt render chưa hoàn chỉnh, DỪNG: không tự dựng lại/ghi đè. Chỉ dùng recover-lock khi xác minh tiến trình chủ đã chết; chỉ dùng reconcile-render khi video đã hoàn tất và qua QA độc lập. Job cũ LEGACY_NO_CHECKPOINTS chưa có hồ sơ checkpoint, không được gán bằng chứng giả.

Khi discover, đọc candidates.json, research_screening.json và queue.md; RSS chỉ cung cấp nguồn gợi ý. Trước evidence phải mở nội dung thật, ghi claim source_ids và provenance, xác minh ít nhất hai tổ chức độc lập mỗi claim, phân biệt syndicated, xác nhận event_at và publication timestamps trong khoảng yêu cầu. Sau evidence, đọc stage17_evidence_review.json/md; nếu có ít hơn 5 tin đạt yêu cầu thì báo đúng số lượng. Chỉ chuyển sang select/draft/approve khi có thông điệp lựa chọn và phê duyệt riêng của người dùng. Không tự đăng.

## Giai đoạn 18–19 — Checklist tác nghiệp Agent
Trước khi khóa kịch bản ở P4/P5: rà phát âm tên riêng, thuật ngữ, số liệu, ngày tháng; đo Piper WAV thật. Nếu dùng từ điển chỉnh phát âm, đưa dấu vân tay SHA-256 vào bản nháp trước khi người dùng duyệt. Không sửa lời dẫn đã phê duyệt.
Trước P6: chỉ bật smart_crop:true với ảnh/B-roll đã có quyền sử dụng, media_sha256, license_evidence, source_url, author, license_name và attribution trong visual_plan. Nếu có focal_x/y do người dùng chỉ định, giữ tọa độ đó. Nếu thiếu model/OpenCV cho B-roll Smart Crop, báo lỗi rõ ràng.
Sau P6/P7: đọc voice_qa.json, smart_crop_report.json, QA MP4/H264/AAC/30fps, âm lượng, phụ đề SRT và preview hai tỷ lệ. Word highlights là ước lượng, cần nghe thật để kiểm phát âm; crop thiếu tự tin cần xem mắt. Người dùng chọn tin, phê duyệt hash và tự đăng.

## Giai đoạn 20 — Giao diện được người dùng phê duyệt
Khi soạn draft, đề xuất quick/roundup/deep_dive và ghi visual_style vào JSON, để người dùng duyệt đúng hash. Nếu quá nhiều chữ hoặc infographic vượt safe-area, rút gọn ở bản nháp chưa được duyệt. Sau duyệt không thay preset để né kiểm duyệt. Xem trực tiếp video 9:16/16:9, rà vùng phụ đề và logo, chữ Anh/Việt, bar chart và watermark DEMO; kiểm báo cáo visual_design.json. Giai đoạn 21 vẫn còn.

## Hướng dẫn phát hành v1.0.0-rc.2
Khi người dùng yêu cầu chuyển Skill sang máy Windows khác, đọc references/STAGE21_RELEASE_CHECKLIST.md; chạy scripts/bootstrap_windows.ps1 với runtime sạch riêng, model và FFmpeg do user cung cấp đúng giấy phép; doctor và bài test trên máy mới. Chạy một DEMO đã gắn watermark ở cả hai tỷ lệ và kiểm QA/MP4/SRT/giọng/nguồn/hình. Không gộp môi trường gốc vào ZIP, không công bố bản 1.0.0 GA khi chưa có biên bản máy Windows thứ hai. Tin đã duyệt không được tự đổi nội dung; QA thời lượng 5% bắt buộc với video thật.
