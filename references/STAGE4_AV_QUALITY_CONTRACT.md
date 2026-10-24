# Đợt 4 — Audio/Video chất lượng cao 18–25 (v1.0.0-rc.2)

Mục tiêu: nâng độ tin cậy của render **hoàn toàn cục bộ**, giữ nội dung và tài nguyên đã được người dùng duyệt; không tự động upload TikTok/YouTube. Đây là đặc tả mã nguồn/kiểm thử tự động, **chưa phải nghiệm thu nghe nhìn Windows hay GA**.

## 18. Giọng AI cục bộ
- `scripts/local_voices.py` quét **chỉ** các cặp Piper `.onnx` + `.onnx.json` đã nằm trong thư mục `PIPER_VOICE_DIR`. Với ngôn ngữ Việt/Anh, ưu tiên model có nhãn metadata `high` so với `medium` và `low`; điểm metadata không chứng minh giọng nghe hay.
- `workflow.py render --voice ...` vẫn cho người điều khiển chọn chính xác giọng local đã cài; nếu không có model, không tự tải từ mạng. Phải nghe mẫu và chọn giọng trước khi chạy job thật; model cần đúng ngôn ngữ, giấy phép và cấu hình.
- Thay đổi model sau khi phê duyệt lời dẫn có thể thay đổi độ dài; bắt buộc QA thời lượng và nghe lại.

## 19. Nhịp kể, ngắt câu, phát âm và âm thanh
- Piper tiếp tục TTS trên Windows local, giữ text phụ đề từ script gốc; từ điển phát âm phải có SHA-256 đã duyệt ở Đợt 2. TTS ngắt câu dài/ngắn theo dấu kết thúc, dấu phẩy và kết thúc story; không tái viết lời dẫn.
- Audio và subtitle theo thời gian WAV đã đo, không dựa trên tốc độ đọc giả định.
- Đọc lại phát âm tiếng Việt/Anh, acronym, năm, đơn vị, tên riêng bằng tai; không có thang điểm âm học tổng quát chứng minh \"giống người\".

## 20. Phụ đề và forced alignment offline
- Mặc định tạo cue từ WAV thật nhưng **word highlight vẫn là ước lượng** và báo cáo `CHUNK_REAL_WAV_WORD_ESTIMATED`.
- Có thể cài **aligner Python ngoại vi trong runtime** (do người dùng kiểm toán và cung cấp) và đặt đường dẫn file `NEWS_LOCAL_ALIGNER`; nếu không đặt thì dùng mặc định ước lượng. Không tự tải model AI hoặc kết nối API; tiến trình aligner được gọi không qua shell với môi trường yêu cầu offline.
- Giao thức gọi: `python aligner.py --audio narration.wav --cues alignment_input.json --output alignment_output.json`.
- Output bắt buộc có `{"schema":"LOCAL_WORD_ALIGNMENT_V1","cues":[{"words":[{"text":"exact","start":0.0,"end":0.3}]}]}` cho từng cue. `scripts/local_alignment.py` kiểm độ dài, thứ tự và text nguyên vẹn, timestamp tăng dần, không vượt cue hay WAV. Không có output hợp lệ → fail closed, không giả vờ đã căn chỉnh. QA ghi `LOCAL_OFFLINE_FORCED_ALIGNMENT_VALIDATED` chỉ khi đã kiểm output thực tế.
- Việc kiểm cấu trúc timestamp **không chứng nhận** căn chỉnh âm học chính xác: phải nghe và xem phụ đề thật. Không tự bật aligner với mã chạy bên ngoài chưa kiểm toán.

## 21. Nhạc và âm lượng
- Chỉ trộn nhạc có `music_path`, `music_sha256` và `music_license` nằm trong draft đã được người dùng duyệt.
- Chuỗi FFmpeg: high-pass giọng, giảm nền, sidechain ducking, `loudnorm I=-16 TP=-1.5`, peak limiting, 48kHz AAC, không thay WAV nguyên bản. QA đo âm lượng/silence; vẫn phải nghe tránh sai lời hoặc nhạc lấn giọng.
- Nếu không có nhạc hợp pháp, render không nhạc.

## 22. Smart Crop cục bộ
- Nhận diện mặt bằng OpenCV Haar (chỉ gợi ý focal, không nhận diện danh tính); khi có nhiều mặt, trung tâm trọng số hạn chế bỏ qua khuôn mặt khác.
- Với video, lấy mẫu theo thời gian, làm mượt chuyển động và ghi mức độ không chắc chắn; `focal_x/y` được duyệt thủ công luôn ưu tiên.
- Crop hoạt động riêng 1080x1920 và 1920x1080; yêu cầu kiểm tra lại tiêu điểm sau dựng. Không tuyên bố chính xác về chủ thể của tin.

## 23. Media đúng câu chuyện và quyền sử dụng
- Media/B-roll nằm trong `visual_plan` đã duyệt, gắn `claim_ids`, đường dẫn, SHA-256 và chứng cứ quyền sử dụng. Video chỉ được dùng sau khi kiểm SHA-256.
- `media_rights.json` và `smart_crop_report.json` ghi fingerprint, nguồn/giấy phép/tác giả, cảnh báo metadata thiếu và yêu cầu người dùng đánh giá sự phù hợp của từng shot.
- Không tự tìm hoặc đưa hình ảnh chưa xác minh lên video như bằng chứng sự kiện; đồ họa gốc là phương án an toàn khi thiếu media.

## 24. Remotion
- Giữ 3 phong cách riêng `quick`, `roundup`, `deep_dive`; 9:16 và 16:9 với safe-area, infographic và caption.
- Thêm hiệu ứng chuyển shot mượt, màu highlight theo palette đã duyệt và điều chỉnh chữ caption khi dài. Không tự cắt nội dung văn bản đã duyệt để giấu lỗi.
- Thời lượng và bố cục cần kiểm độc lập bằng render thật; không tự cấp nhãn GA.

## 25. Render độc lập theo job
- `video_pipeline.isolated_remotion_site` sao chép source Remotion sang `job/attempt-*/_work/remotion-site`, tạo `public/assets` độc lập; chỉ dùng chung `node_modules` qua symlink (Linux) / junction (Windows).
- Mỗi job giữ nguyên media, props, log, render, SRT và QA của mình. Không ghi media sang `<runtime>/remotion/public/assets` chung; không xóa tệp/bản render của job khác.
- Model Piper, ffmpeg và package code dùng chung khi đã cài; khóa job và checkpoint của các giai đoạn trước vẫn áp dụng.

## Nghiệm thu
- CI tự động: `tests/test_stage4_av.py`, toàn bộ test cũ, kiểm manifest SHA-256 và metadata RC.
- Bài kiểm thực tế còn phải làm trên Windows: 2 tỉ lệ 9:16/16:9, 2 job chạy đồng thời, Piper local, model aligner offline nếu dùng, loa/headphones, giới hạn âm lượng, Smart Crop có chủ thể đang chuyển động, B-roll có quyền, thời lượng và khung hình thực tế.
- Người dùng **tự chọn tin**, duyệt chính xác script, kiểm tra cuối và tự đăng; không tự động xuất bản.
