# Hướng dẫn cài đặt/di chuyển AI News Video Skill v1.0.0-rc.2 (Windows)

## Môi trường phát triển trước đây (chỉ tham khảo lịch sử)

Skill từng chạy trên Windows với Python 3.13, Node 24, Remotion 4.0.538, FFmpeg/FFprobe, Piper và GTX 1060 3GB. Không yêu cầu máy đích có cùng đường dẫn, driver hoặc dữ liệu lịch sử. Video, backup và hồ sơ nghiệm thu không thuộc gói nguồn.

## Yêu cầu máy mới
1. Giải nén/thả thư mục Skill, giữ nguyên scripts, references, remotion-template và tests.
2. Cài Python tương thích, tạo sibling runtime (<skill-path>-runtime) và môi trường .venv.
3. Cài Python dependencies từ requirements.txt bằng python -m pip install -r requirements.txt; giọng Piper ONNX+JSON theo giấy phép và ngôn ngữ, đặt vào runtime/models.
4. Cài Node.js tương thích, Chrome/Chromium chạy được, FFmpeg/FFprobe hỗ trợ libass và H.264; test encoder NVENC thực tế. Không thay driver khi chưa có yêu cầu.
5. Chạy & '<SKILL>\scripts\setup_remotion.ps1' -InstallPackages. Script sao chép remotion-template và package-lock.json vào runtime/remotion rồi npm ci; source portable nằm trong Skill.
6. Chạy python -B <SKILL>\scripts\doctor.py. Đảm bảo ready_dual_aspect=true, nvenc_operational có thể false nếu CPU fallback.
7. Chạy unit tests bằng <RUNTIME>\.venv\Scripts\python.exe -B -m unittest discover -s <SKILL>\tests -v. Giai đoạn 12–13 bổ sung qa_engine.py, qa_repair.py và workflow.py; đọc references/AGENT_RUNBOOK.md và references/QA_AUTOREPAIR.md.
8. Thử với file DEMO có dấu watermark (không được xuất bản) và cả hai tỷ lệ.

## Vận hành trên máy Windows được cấp quyền

Khởi tạo `$skill`, `$runtime`, `$py` theo `PORTABILITY_CONTRACT.md`. Sau khi bootstrap thành công:

```powershell
& $py -B (Join-Path $skill 'scripts\doctor.py') --runtime $runtime
& (Join-Path $skill 'scripts\setup_remotion.ps1') -Runtime $runtime
& (Join-Path $skill 'scripts\run_news_video.ps1') -InputFile (Join-Path $skill 'examples\demo_brief.json') -AllowDemo -DryRun
# Tin thật chỉ dùng approved brief có phê duyệt thực từ người dùng:
# & (Join-Path $skill 'scripts\run_news_video.ps1') -InputFile $approvedBriefPath -Encoder auto
```

Tùy chọn: `-Encoder auto/cpu/nvenc`, `-Voice`, `-SpeechRate 0.75..1.35`, `-Lexicon`, `-Music`, `-OutputDir`. Không đổi lời dẫn, tỷ lệ hoặc media sau khi phê duyệt.

## Bảo mật và dữ liệu
- Các job output luôn riêng, không ghi đè, tự động xóa hay reset output người dùng.
- Không lưu OAuth/TikTok/YouTube, API bí mật vào Skill. Người dùng tự đăng video.
- Mọi nội dung DEMO là giả lập; tên file DEMO_DO_NOT_PUBLISH_*.mp4 và watermark bắt buộc.
- Với job nhiều giai đoạn: chạy python -B <SKILL>\scripts\workflow.py init rồi discover/evidence/select/draft/approve/render/qa/handoff. Khi gián đoạn, dùng status hoặc resume để biết bước tiếp theo; không tự xóa .stage4.lock nếu còn tiến trình.
- Đồ họa Remotion, voice model, media có quyền và lời dẫn tạo mới cần được kiểm tra trước dùng thương mại.
- Trước khi chuyển máy, sao lưu Skill/approved manifests và output quan trọng, mang theo giấy phép và mô hình cần thiết theo chính sách sử dụng tương ứng.

## Bổ sung Giai đoạn 18–19 (v0.7.0) — Smart Crop local
- Cài dependencies trong venv runtime: python -m pip install -r requirements-smart-crop.txt. Thư viện OpenCV, NumPy, Pillow phải nằm ngoài Skill; nếu không có OpenCV thì chỉ khả dụng crop ảnh bằng Pillow và vùng tương phản, video Smart Crop cần OpenCV.
- Sau khi cập nhật Skill, gọi scripts/setup_remotion.ps1 để đồng bộ remotion-template sang runtime/remotion. Node modules phải tương thích package-lock.json.
- Chạy scripts/doctor.py và xem stage18_voice_caption, stage19_smart_crop trước sản xuất. Giữ nguyên các model Piper được phép sử dụng.
- Một từ điển phát âm chỉnh giọng bản tin thật phải được ghi SHA-256 trong kịch bản trước khi người dùng phê duyệt. Đầu ra có voice_qa.json, smart_crop_report.json, hai MP4 khi chọn both và SRT tương ứng.
- Mọi cảnh ảnh/B-roll có smart_crop:true cần nguồn, tác giả, tên giấy phép, bằng chứng quyền sử dụng, attribution và SHA-256; kiểm lại quyền thương mại trước khi đăng.

## v0.8.0 — Remotion Theme
Sau khi cập nhật Skill trên máy mới hoặc thay News.jsx, chạy scripts/setup_remotion.ps1, xác nhận runtime/remotion/src/News.jsx khớp SHA-256 nguồn. Không thêm font hay logo bên ngoài; preset quick/roundup/deep_dive được tích hợp sẵn. Chạy doctor.py, unittest, render DEMO 9:16/16:9 và kiểm frame trước sử dụng tin thật.

## v1.0.0-rc.2 — Bộ cài portable

**Quy trình ưu tiên:** Xem `references/WINDOWS_BOOTSTRAP.md`. Chạy `scripts/bootstrap_windows.ps1 -CheckOnly` trước mọi thao tác cài đặt; kết quả chỉ là chẩn đoán, không tải model hay tạo runtime. Hỗ trợ `NEWS_CHROME_PATH`/`REMOTION_BROWSER_EXECUTABLE` và kiểm mã hóa FFmpeg bằng H.264 NVENC hoặc CPU libx264. Khi `doctor.py` chưa trả `ready_dual_aspect=true`, chưa dựng video thật. `npm.cmd ci` dùng thay `npm` để tránh chính sách PowerShell chặn `npm.ps1`.
Lựa chọn một thư mục source và một thư mục runtime trống trên Windows đã cài Python 3.13, Node.js và Chrome. Dùng scripts/bootstrap_windows.ps1 -Runtime <FRESH_RUNTIME> -FFmpegSource <FOLDER> -VoiceModelsSource <FOLDER>. Installer không tải model, không xóa tệp, từ chối ghi đè runtime chưa cho phép, cài pip requirements-smart-crop.txt (gồm psutil) và npm ci theo package-lock. Nếu muốn dùng runtime đã có, bắt buộc -AcceptExistingRuntime và tự kiểm bảo toàn dữ liệu. Chạy doctor, unittest, dựng DEMO cả hai tỷ lệ, QA thật; không dùng máy Windows duy nhất làm chứng cứ cross-host.
