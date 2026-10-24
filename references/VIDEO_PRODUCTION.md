# Hướng dẫn sản xuất video v0.7.0 — Giai đoạn 08–19

**CHUYỂN MÁY (v1.0.0-rc.2):** Đọc `references/PORTABILITY_CONTRACT.md`, thiết lập `$skill`, `$runtime`, `$py` trên đúng máy. Đường dẫn ổ D:, ADMIN-PC-02, job và benchmark trong tài liệu giai đoạn chỉ là ví dụ/hồ sơ lịch sử; **không chạy nguyên văn trên máy mới**. Quy trình hiện tại theo `AGENT_RUNBOOK.md`.


## Tổng quan
Renderer mới: scripts/run_news_video.ps1 gọi scripts/video_pipeline.py. Nó dùng Piper TTS tạo audio ngoại tuyến, Remotion dựng hình/hoạt ảnh/phụ đề, FFmpeg tạo MP4 cuối với H.264/AAC.
- 9:16 = 1080x1920, 16:9 = 1920x1080, both = cả hai từ cùng manifest.
- 30 FPS, layout độc lập mỗi tỷ lệ. Audio được tạo một lần; mỗi bản MP4 có SRT riêng.
- Không đăng lên TikTok/YouTube. Người dùng tự đăng.
- Chương trình cũ run_local.ps1 vẫn giữ cho quy trình legacy, dùng run_news_video.ps1 cho engine mới.

## Giai đoạn 08: nguồn hình ảnh và B-roll
AI tìm nguồn media theo ngữ cảnh sự kiện và giấy phép; có thể chạy:
  & $py -B (Join-Path $skill "scripts\media_catalog.py") --query "NASA space telescope" --limit 10 --out (Join-Path $runtime 'output\media-candidates-unique.json')
Công cụ lấy ứng viên từ Wikimedia Commons API, hiển thị tác giả, tên giấy phép, URL trang file và credit; toàn bộ mặc định REQUIRES_HUMAN_LICENSE_CHECK.
Cần kiểm tra từng giấy phép trên trang chính thức và quy định thương mại/attribution/quyền hình ảnh. Không tự tải hoặc sử dụng media khi chưa được duyệt.
Với visual_plan, type = news_card, infographic, licensed_image, licensed_broll. Media thật phải có media_path tương đối trong thư mục brief, license_evidence và claim_ids. Ảnh dùng crop giữ đúng tỷ lệ và tùy chọn focal_x/focal_y (0..1); B-roll chuẩn hóa bằng FFmpeg rồi dùng Remotion.
Crop theo focal point được cung cấp, CHƯA tự nhận diện khuôn mặt bằng AI. Khi không có media có quyền, fallback card/đồ họa gốc. Không tạo hình giả làm bằng chứng thời sự.

## Giai đoạn 09: TTS và phụ đề
Piper model giọng Việt và Anh chạy local, chỉnh -Voice và -SpeechRate 0.75..1.35. Dùng -Lexicon trỏ đến JSON thay thế cách đọc từ khó/tên riêng (chỉ cho TTS, phụ đề giữ văn bản gốc).
Subtitles đồng bộ theo từng cụm dựa trên thời gian WAV thực, gồm file SRT và chữ cháy Remotion với vùng chữ khác nhau cho từng tỷ lệ. Đây CHƯA phải forced alignment từng từ.
Nhạc tùy chọn thông qua -Music, yêu cầu music_license trong approved brief; FFmpeg sidechaincompress giảm nhạc khi có giọng đọc và loudnorm -16 LUFS với true peak mục tiêu -1.5 dB. Kiểm chứng quyền sử dụng nhạc/voice là bắt buộc trước thương mại.

## Giai đoạn 10: đồ họa động và hai bố cục
Source trong remotion-template/src, runtime Node modules tại D:\skill-tintuc-runtime\remotion. Hai Composition thật: NewsVertical (1080x1920) và NewsHorizontal (1920x1080).
Có tiêu đề motion slide/fade, thanh tiến trình, bảng nguồn, caption, banner DEMO, background media hoặc gradient, khung đọc phù hợp chiều ngang/dọc.
Không giả đổi tỷ lệ đầu ra bằng crop video final. Dùng một bộ audio và cùng tập claims.
Output job riêng: news_video_9x16.mp4/news_video_16x9.mp4; nếu demo: DEMO_DO_NOT_PUBLISH_*.mp4; subtitles_*.srt; qa_report.json; sources.json; publishing_metadata.json; narration.wav và _work.

## Giai đoạn 11: FFmpeg/NVENC/CPU
Trên ADMIN-PC-02: GTX 1060 3GB, NVIDIA 582.66, FFmpeg 7.1 tương thích NVENC, FFprobe đã kiểm tra H.264/AAC. Bản FFmpeg 9.0.2 trước đó không tương thích NVENC API của driver.
Remotion/Chromium kết xuất đồ họa bằng pipeline trình duyệt và tạo tệp tạm (không đảm bảo toàn bộ frame dùng GPU). FFmpeg mã hóa lại MP4 cuối bằng NVENC H.264 hoặc CPU libx264.
--Encoder auto kiểm tra NVENC chạy thực tế rồi fallback CPU. -Encoder nvenc sẽ dừng nếu GPU không sử dụng được; -Encoder cpu ép CPU.
Remotion --concurrency 1 tránh chiếm RAM/VRAM quá mức trên máy GPU 3GB. Giữ logs và _work khi lỗi. Không tự sửa driver hoặc xóa cache của dự án khác.

## Vận hành
1. PowerShell: & (Join-Path $skill 'scripts\setup_remotion.ps1') -Runtime $runtime -InstallPackages
2. PowerShell: & (Join-Path $skill 'scripts\run_news_video.ps1') -InputFile $approvedBriefPath -DryRun
3. PowerShell: & (Join-Path $skill 'scripts\run_news_video.ps1') -InputFile $approvedBriefPath -Encoder auto

Phải có manifest approved hợp lệ, SHA-256 khớp kịch bản người dùng đã duyệt. Với bản tin thật kiểm tra lại nguồn và quyền media. DEMO chỉ để thử nghiệm, không phát hành. QA v0.5 tại scripts/qa_engine.py kiểm codec/kích thước/giọng/phụ đề/timeline/ảnh frame mẫu và checksum MP4; scripts/qa_repair.py chỉ khôi phục SRT sidecar vào thư mục mới. Đọc references/QA_AUTOREPAIR.md, references/AGENT_RUNBOOK.md.

## Giai đoạn 18–19 — Voice QA và Smart Crop
- narration_quality.py kiểm timeline của SRT từ duration WAV Piper đo thật, phát warning từ số/tên riêng. Remotion tô màu từ theo ước lượng trong một cue, không phải forced alignment.
- smart_media.py dùng OpenCV Haar nhận vùng khuôn mặt, edge saliency và keyframe tracking; FFmpeg crop video theo quỹ đạo tại 30 FPS, mỗi tỷ lệ thực hiện riêng. Chỉ bật với smart_crop:true trong visual_plan có bản quyền và hash trước khi người dùng duyệt. focal_x/y thủ công được ưu tiên.
- Bộ báo cáo voice_qa.json, smart_crop_report.json và QA độc lập chứng minh codec, kích thước, thời lượng, caption, âm thanh và tính toàn vẹn tệp. Không tự chứng minh đúng nguồn tin, phát âm hoàn hảo, khuôn mặt hay quyền sử dụng thương mại.
- Đọc references/STAGE18_19_OPERATIONS.md và kiểm lại Voice QA, Smart Crop trên máy đang cài.

## v0.8.0 — Style/Infographic/Video Safe Area
Đặt visual_style trước khi người dùng duyệt hash. Ba preset Remotion có intro/outro trong timeline, source/footer/safe-caption và infographic 0..100 gắn dữ liệu trong approved visual_plan. Trường hợp summary/headline dài hoặc chart nhiều điểm cần xem trực quan ảnh frame cả hai tỷ lệ; cảnh báo của design validator không thay người duyệt.
