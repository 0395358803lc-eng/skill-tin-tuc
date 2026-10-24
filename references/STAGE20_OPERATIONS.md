# Giai đoạn 20 — Remotion, phong cách bản tin và nghiệm thu

**CHUYỂN MÁY (v1.0.0-rc.2):** Đọc `references/PORTABILITY_CONTRACT.md`, thiết lập `$skill`, `$runtime`, `$py` trên đúng máy. Đường dẫn ổ D:, ADMIN-PC-02, job và benchmark trong tài liệu giai đoạn chỉ là ví dụ/hồ sơ lịch sử; **không chạy nguyên văn trên máy mới**. Quy trình hiện tại theo `AGENT_RUNBOOK.md`.


**Trạng thái:** Đợt 8, ưu tiên hoàn thiện hình ảnh trước phát hành v1.0.0. Thực hiện trên ADMIN-PC-02; Skill chỉ lưu mã nguồn/Markdown, MP4 và chứng cứ chạy ở \`D:\skill-tintuc-runtime\`.

## 20.01 — Bộ nhận diện gốc
- Thương hiệu: AI NEWS VIDEO; monogram “AN” được vẽ bằng CSS trong Remotion. Không sao chép logo, tải font hay artwork bên ngoài.
- Font trên Windows: Arial / Segoe UI; thử tiếng Việt UTF-8 và tiếng Anh. Bảng màu có cấu hình cố định trong \`scripts/studio_design.py\`, chuyển thành visual_design.json để QA. React giữ các bảng màu tương ứng.
- Tất cả video có tên tin/số thứ tự, dải nguồn, thanh thời gian, vị trí phụ đề và dấu DEMO (nếu là test).

## 20.02 — Ba phong cách do người dùng chọn
Đặt một giá trị sau vào **SCRIPT đầu vào trước khi \`workflow.py draft\`**:

| visual_style | Chương trình | Màu nhấn | Chuyển cảnh | Phù hợp |
|---|---|---|---|---|
| \`quick\` | Tin nhanh / NEWS FLASH | Cyan/coral | 9 frame | Bản tin một chủ đề nhanh |
| \`roundup\` | Bản tin tổng hợp / NEWS ROUNDUP | Blue/coral | 12 frame | Nhiều tin, recap |
| \`deep_dive\` | Phân tích chuyên sâu / DEEP DIVE | Amber/teal | 15 frame | Giải thích, đồ họa dữ liệu |

Nếu SCRIPT không cung cấp, hệ thống mặc định \`roundup\` để tương thích. \`editorial_core.draft_manifest\` ghi \`visual_style\` vào kịch bản được gửi duyệt và SHA-256; bất kỳ thay đổi preset **sau phê duyệt** đều làm sai dấu hash và không được tự thực hiện. Không dùng tham số CLI để vượt qua phê duyệt.

## 20.03 — Intro và outro động
- Intro overlay thương hiệu ở đầu cảnh đầu tiên, outro overlay cuối cảnh cuối; **không thêm giây, không thay lời đọc hoặc subtitle**.
- Video DEMO có watermark không được xóa, ở vùng riêng không che caption. Tin thật không tự thêm CTA quảng cáo hay lời nói ngoài approved script.

## 20.04 — Chuyển cảnh Remotion
- Story được chia thành \`Sequence\` theo \`durationFrames\` được đo bằng Piper WAV thật.
- Animation opacity/translate/palette là CSS/Remotion nội bộ; hiện có fade in/out bằng 9/12/15 frame tùy preset. Không dùng \`--every-nth-frame\` cho bản tin thật; native 30 FPS.
- Nếu thời lượng câu chuyện quá ngắn, transition tự giới hạn theo phần tư của scene.

## 20.05 — Infographic có truy vết
- Bar chart chỉ dùng giá trị 0–100 và label/title từ \`visual_plan[type=infographic].data_points\` đã nằm trong draft được duyệt. Không tự tạo số liệu, cột phần trăm hay biểu đồ giả làm dữ liệu thật.
- Layout ngang: chart nằm bên phải, nội dung bên trái. Dọc: chart có vùng riêng, tự thu nhỏ với 4–5 điểm; không kéo đè phụ đề.
- Trong ảnh DEMO, mọi con số được đánh dấu giả lập. Với tin thật, \`claim_ids\` của graphic phải gắn claim nguồn đã đọc.

## 20.06 — Safe-area
- Dọc 1080×1920: giữ guard top 136px, bên trái 88px, bên phải 130px; phụ đề cách đáy 385px; watermark ở đáy, footer không che subtitle. Infographic top ~940px và kết thúc trước vùng caption.
- Ngang 1920×1080: top guard 90px; phụ đề cách đáy 166px; infographic bên phải x~1015px, kết thúc trước subtitle.
- Bản chữ quá dài bị từ chối **trước khi hash phê duyệt**, hoặc cảnh báo để kiểm tra bố cục; không lặng lẽ cắt headline/summary bằng \`slice\` hoặc CSS line-clamp.
- Kết quả \`visual_design.json\` có preset, cảnh báo, vùng an toàn, không được thay trực tiếp sau khi approved.

## 20.07 — Kiểm thử ngôn ngữ và edge cases
- \`tests/test_stage20.py\` kiểm ba preset, copy tiếng Việt/Anh, Unicode, title/summary dài, infographic 0–100, vùng an toàn, intro/outro, logo gốc, tính bất biến nội dung và SHA-256 style.
- Bài DEMO dựng thật bao gồm Tin nhanh tiếng Việt (15s), Tổng hợp tiếng Việt hai tin (30s), Phân tích tiếng Anh (15s), cả 9:16 và 16:9.
- Kiểm mắt 3–5 khung hình mỗi tỷ lệ: chữ, safe-area, biểu đồ, chuyển cảnh, nguồn/watermark, không lầm ảnh giả lập với tin thật.
- \`qa_engine.py\` từ chối thiếu design sidecar, style/props mismatch, độ phân giải/FPS/audio phụ đề không hợp lệ; các trường hợp quá dài hoặc metadata phiên bản trước phát cảnh báo kiểm tay.

## 20.08 — Hiệu năng và ổn định
- Renderer không tải font/ảnh/logo ngoài qua mạng; bảng màu/brand CSS và chart nội bộ, animation opacity/transform không cần model VLM mới.
- Chạy \`stage5_benchmark.py\` với \`--remotion-concurrency 2\` (đã vận hành trên GTX 1060 3GB), lấy walltime, peak RSS cây tiến trình và VRAM/GPU **toàn thiết bị**. Khi hết RAM/VRAM hoặc Chromium crash, sử dụng \`REMOTION_CONCURRENCY=1\`; encoder \`auto\` dùng NVENC nếu có, fallback CPU nếu thiếu.
- Không khẳng định GPU luôn render nhanh hơn; cuối pipeline xuất H.264/AAC 30 FPS, kiểm FFprobe và SHA-256.
- Mọi benchmark là DEMO riêng, không sửa approved.json hay ZIP/video cũ. Thời gian phụ thuộc số frame, B-roll/chart, Chrome, tải nền Windows.

## Sử dụng trên máy hiện tại
\`\`\`powershell
$py = Join-Path $runtime '.venv\Scripts\python.exe'
# 1. Kiểm tra script chưa duyệt: visual_style=quick|roundup|deep_dive
# 2. workflow.py draft (đóng băng hash chứa visual_style), xin phê duyệt người dùng
# 3. workflow.py render theo approved.json
# 4. QA đầu ra: visual_design.json, props-*.json, voice_qa.json, qa_report.json,
#    subtitles_*.srt, MP4, media_rights.json
& $py -B "$skill\scripts\doctor.py"
& (Join-Path $skill 'scripts\setup_remotion.ps1') -Runtime $runtime
& $py -B -m unittest discover -s (Join-Path $skill 'tests') -q
\`\`\`

**Giới hạn:** Stage20 là phép nghiệm thu bố cục/kỹ thuật và preview frame của video DEMO. Không xác thực sự thật tin tức, bản quyền thương mại, tính chính xác của forced alignment hay khả năng cài đặt trên một PC thứ hai. Người dùng vẫn quyết định tin, duyệt hash, xem/nghe và tự đăng TikTok/YouTube.
