# AI News Video Skill v1.0.0-rc.2 — bộ nguồn sạch để chuyển máy

**Trạng thái: Release Candidate — CHƯA PHẢI v1.0.0 GA.** Người dùng sẽ tự thực hiện Giai đoạn 4 (nghiệm thu Windows độc lập và video thật/DEMO). Giai đoạn 5 chỉ hoàn thiện bộ mã nguồn và bản kê SHA-256; không được coi kiểm toán nguồn là nghiệm thu GA.

ChatGPT điều phối nghiên cứu tin thời sự, kiểm chứng từ ít nhất hai nguồn độc lập, đề xuất để người dùng **chọn tin**, soạn kịch bản gắn claim và hash để người dùng **duyệt toàn văn**, rồi mới tạo video. Piper hỗ trợ TTS tiếng Việt/Anh; Remotion/FFmpeg dựng 9:16, 16:9 hoặc cả hai (H.264/AAC, 30 FPS), SRT, infographic, B-roll/Smart Crop có quyền. QA kiểm codec, duration, nguồn, phụ đề, âm thanh và checksum, có cơ chế resume và phục hồi SRT an toàn. Người dùng xem/nghe, kiểm tra sự thật/bản quyền rồi **tự đăng**; không có đăng tự động.

## Cấu trúc phát hành
- `SKILL.md`: bộ não Agent, quy trình P0–P7 và hai cổng phê duyệt thực.
- `references/`: hợp đồng portable, hướng dẫn điều phối Agent nhiều phiên, nguồn, biên tập, bảo mật, quyền media, Windows, QA và phát hành.
- `scripts/`: Python/PowerShell nghiên cứu, TTS, workflow, `agent_bridge.py` chỉ-đọc, Smart Crop, Remotion, QA và `release_manifest.py` để kiểm tính toàn vẹn ZIP sau khi giải nén.
- `remotion-template/`: source frontend và package-lock.json.
- `tests/`: bộ kiểm thử hồi quy; `examples/`: fixture/DEMO, tuyệt đối không đăng.
- `requirements*.txt`, `.gitignore`, `scripts/release_manifest.py`, `RELEASE_MANIFEST_SHA256.json` và `references/TRANSFER_ZIP_WINDOWS.md` là thành phần phát hành nguồn; manifest loại trừ chính nó khỏi bảng hash.

Các báo cáo nghiệm thu lịch sử trong `reports/` đã được lưu riêng ngoài gói nguồn. Không đóng gói runtime, file thử nghiệm, video, output, job, log, model ONNX, FFmpeg, cache, node_modules, venv, token hay dữ liệu người dùng.

## Cài đặt trên máy Windows khác
Giải nén ZIP vào thư mục mới (ví dụ `D:\AI-News-Video-Skill`). Cài Python 3.13, Node.js, Google Chrome. Chuẩn bị model Piper (ONNX+JSON) và FFmpeg/ffprobe có libass **theo giấy phép** bên ngoài thư mục Skill.

```powershell
# Mở PowerShell tại thư mục Skill đã giải nén và cung cấp đường dẫn dependencies có quyền.
$skill = (Resolve-Path .).Path
if (-not (Test-Path (Join-Path $skill 'SKILL.md'))) { throw 'Not a Skill root' }
$runtime = "$skill-runtime"
$ffmpegSource = '<THU_MUC_FFMPEG_FFPROBE>'
$voiceModelsSource = '<THU_MUC_PIPER_ONNX_JSON>'
& (Join-Path $skill 'scripts\bootstrap_windows.ps1') -Runtime $runtime -FFmpegSource $ffmpegSource -VoiceModelsSource $voiceModelsSource
$py = Join-Path $runtime '.venv\Scripts\python.exe'
& $py -B (Join-Path $skill 'scripts\doctor.py') --runtime $runtime
& $py -B -m unittest discover -s (Join-Path $skill 'tests') -q
```

Thay đường dẫn bằng vị trí thực tế trên máy đích; runtime phải nằm ngoài mã nguồn. **Trước khi tự đóng ZIP và sau khi giải nén**, xem `references/TRANSFER_ZIP_WINDOWS.md` và chạy `py -3.13 -B scripts/release_manifest.py verify` tại gốc Skill. Xem thêm `references/PORTABILITY_CONTRACT.md`, `references/WINDOWS_BOOTSTRAP.md`, `references/AGENT_ORCHESTRATION.md`, `references/INSTALL_WINDOWS.md` và `references/AGENT_RUNBOOK.md`. Chạy `bootstrap_windows.ps1 -CheckOnly` trước khi cho phép cài đặt. Chrome/Chromium được tìm qua PATH hoặc `NEWS_CHROME_PATH`; GPU NVENC chỉ được chọn nếu kiểm mã hóa thực đạt, nếu không dùng CPU libx264 khi hoạt động.

## Quy tắc bảo vệ
- RSS và metadata không đủ để chứng minh tin đúng; Agent phải kiểm nguồn chính thức, thời gian và claim.
- Không giả mạo lựa chọn của người dùng hoặc tự duyệt SHA-256 kịch bản; không sửa nội dung đã duyệt.
- Không cho tin DEMO hoặc ảnh/nhạc/voice thiếu quyền vào video thực tế.
- QA kỹ thuật không thay thế người xem/nghe và kiểm tra bản quyền.
- Chỉ thông báo GA khi có bằng chứng cài mới + chạy video/QA trên một Windows PC/VM độc lập và hoàn tất kiểm duyệt cuối.

**Đây là bản nguồn portable sạch v1.0.0-rc.2, không kèm dependencies và chưa được chứng nhận GA.**

## Đợt 2 — Hardening workflow 07–12
Đã đồng bộ visual_plan tối đa 20 cảnh giữa editor và renderer; bổ sung phê duyệt SHA-256 cho nhạc nền/từ điển phát âm, kiểm tra file thật tại lúc tạo draft và trước render. Workflow chặn replay sau crash, ghi checkpoint khi commit render, tránh retry CPU khi lỗi bản quyền hoặc dữ liệu. Người dùng vẫn chọn tin và duyệt bản script chính xác, không auto-post. Xem `references/STAGE2_WORKFLOW_CONTRACT.md` và kiểm thử `tests/test_stage2_workflow.py`.

Bộ mã nguồn vẫn **v1.0.0-rc.2**, GA cần nghiệm thu Windows độc lập; CI nguồn không có model Piper và không chứng nhận chất lượng video thực tế.
