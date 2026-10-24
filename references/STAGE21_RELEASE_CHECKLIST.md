# Giai đoạn 21 — Quy trình nghiệm thu cuối và phát hành có kiểm soát

## Bản phát hành và giới hạn
Trước khi có bài kiểm tra trên Windows độc lập thực sự, phiên bản cuối của Giai đoạn 21 được đặt tên **v1.0.0-rc.2 (release candidate)**. Chưa công bố v1.0.0 GA. **Giai đoạn 4 của kế hoạch hiện tại được người dùng chọn tự kiểm thử**, vì vậy việc khóa nguồn/manifest ở Giai đoạn 5 không thay thế bằng chứng nghiệm thu độc lập. Xem `references/TRANSFER_ZIP_WINDOWS.md`. Người dùng tiếp tục chọn tin, phê duyệt chính xác draft SHA-256, duyệt video cuối và tự đăng; không tích hợp TikTok/YouTube upload.

## 21.01–21.08
- **21.01** Kiểm tra lại toàn bộ source và Markdown, requirements, AST, bảo mật, manifest SHA256; dùng scripts/release_audit.py phát hiện artifact rác và khóa truy cập.
- **21.02** Unit/integration tests: human gates, tamper-detection, style hash, voice/subtitle, Smart Crop, media rights, QA/recovery. Kiểm thử cả từ đầu với dữ liệu MOCK riêng và job APPROVED THẬT đã tồn tại.
- **21.03** Dùng approved.json do người dùng trước đây chấp thuận (hai sự kiện US-TECH-MARKET và US-TREASURY). Rerender vào thư mục MỚI, không sửa approved.json và không coi công việc này là phê duyệt lại.
- **21.04** Kiểm FFprobe H264/AAC, 30 FPS, 1080x1920 và 1920x1080, giọng Piper và phụ đề SRT, khớp SHA256, cảnh chart/tiêu đề dài, timestamp, volume và độ dài. QA tin THẬT sai mục tiêu ±5% phải FAIL.
- **21.05** Tạo corruption fixtures tách biệt: MP4 hỏng, thiếu video, SRT hỏng; kiểm lại QA, recovery, job lock, checkpoint và xác minh nguồn MP4 bất biến.
- **21.06** Nghiệm thu cài lại trong thư mục + runtime + Python venv + npm/node_modules/model/ffmpeg MỚI trên chính ADMIN-PC-02: có ích để phát hiện dependency/đường dẫn, nhưng không phải một OS/PC Windows sạch độc lập. Windows Sandbox đang bị TẮT; thiết bị repl là Linux; PC Windows thứ hai không online. Vẫn cần thử trên host Windows mới để GA.
- **21.07** Tài liệu cài đặt, source-only ZIP, không kèm video/model/cache/venv/node_modules/OAuth token và nguồn binary khác. Đối chiếu mỗi SHA-256 trước khi phát hành.
- **21.08** Phát hành release-candidate v1.0.0-rc.2 trước; CHỈ cấp nhãn v1.0.0 GA sau bài thử Windows độc lập, kiểm tra bảo mật và nghiệm thu editor/human cuối.

## Cài đặt Windows

Máy phải có Python 3.13, Node, Chrome, quyền sử dụng Piper voice ONNX/JSON và FFmpeg/ffprobe (NVENC không bắt buộc, CPU fallback). Trích xuất source Skill từ ZIP ở thư mục sạch, ví dụ D:\AI-News-Video-Skill; model/FFmpeg do người dùng tự cung cấp theo điều khoản cấp phép.

    # Mở PowerShell tại thư mục Skill vừa giải nén.
    $skill = (Resolve-Path .).Path
    $runtime = "$skill-runtime"
    $ffmpegSource = '<THU_MUC_FFMPEG_FFPROBE>'
    $voiceModelsSource = '<THU_MUC_PIPER_ONNX_JSON>'
    & (Join-Path $skill 'scripts\bootstrap_windows.ps1') -Runtime $runtime -FFmpegSource $ffmpegSource -VoiceModelsSource $voiceModelsSource

Installer tạo .venv và cài requirements-smart-crop.txt, npm ci cho Remotion theo package-lock.json, chép model/FFmpeg vào runtime, chạy doctor.py và unit tests. Nếu runtime đã có dữ liệu, mặc định DỪNG, không ghi đè. Trường hợp thiếu model/ffmpeg và giấy phép, CHẶN; không tải nguồn/mô hình từ bên thứ ba một cách ngầm định.

## Quy tắc nghiệm thu
- Technical PASS không phải xác nhận tin thật đúng, giấy phép media hay an toàn tự đăng.
- DEMO stress video ngắn không đạt ±5% vẫn có thể PASS kiểm codec/hỏng file; khác hoàn toàn duration QA cho tin thật.
- stage5_benchmark.py chỉ dành cho DEMO, từ chối approved real brief theo thiết kế. Tin thật dùng run_news_video.ps1 hoặc workflow.py render.
- Word-highlight hiện chỉ ước lượng từng từ trong chunk Piper; chưa forced alignment.
- Smart Crop là local heuristic; ảnh nhiều khuôn mặt và cảnh chuyển động cần kiểm bằng mắt.
- Không tự đổi style, media, lời dẫn, nhạc hoặc số liệu sau khi user duyệt hash.
- Sự cố QA ngoài SRT chỉ dừng và yêu cầu can thiệp; không sửa MP4 hoặc bỏ điều kiện phê duyệt.
