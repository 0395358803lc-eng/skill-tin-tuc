# QA tự động và tự sửa lỗi giới hạn — Giai đoạn 12 / v0.5.0

**CHUYỂN MÁY (v1.0.0-rc.2):** Đọc `references/PORTABILITY_CONTRACT.md`, thiết lập `$skill`, `$runtime`, `$py` trên đúng máy. Đường dẫn ổ D:, ADMIN-PC-02, job và benchmark trong tài liệu giai đoạn chỉ là ví dụ/hồ sơ lịch sử; **không chạy nguyên văn trên máy mới**. Quy trình hiện tại theo `AGENT_RUNBOOK.md`.


## Cổng kỹ thuật
scripts/qa_engine.py đọc từng MP4 thực tế bằng FFprobe, kiểm tra:
- Tỷ lệ đúng yêu cầu 9:16 = 1080×1920, 16:9 = 1920×1080. Với both phải có cả hai.
- Một stream H.264 và một stream AAC, 30 FPS, thời lượng sai lệch tối đa 1 giây so với timeline đã ghép; tin thật lệch quá ±5% mục tiêu phải FAIL.
- Phụ đề SRT tồn tại, số thứ tự liên tục, nội dung không rỗng, timecode theo mm:ss/ms hợp lệ, không chồng/tăng ngược/vượt thời lượng.
- Phân tích âm lượng bằng FFmpeg volumedetect và silencedetect; phát hiện audio quá nhỏ/mất tiếng hoặc đoạn tĩnh kéo dài cần nghe rà soát.
- Trích 3 frame đại diện mỗi tỷ lệ tại xấp xỉ 13%, 50%, 84% thời lượng, lưu ảnh preview và độ sáng/độ tương phản để gợi ý lỗi đen hình. Đây không phải QA nhận diện mọi lỗi hình ảnh.
- Kiểm tra sources.json, publishing_metadata.json, narration.wav, media_rights.json; lưu checksum SHA-256 từng MP4.
- Không nhận status renderer lỗi, không tự xác nhận nguồn tin hay quyền thương mại.

## Các trạng thái
- TECHNICAL_PASS_REVIEW_REQUIRED: thông số MP4/SRT đạt; vẫn bắt buộc người thật xem/nghe, đối chiếu fact, kiểm quyền media/music/voice.
- FAIL: có lỗi kỹ thuật; không được bàn giao như file sẵn sàng đăng.
- DEMO_NOT_FOR_PUBLICATION: cảnh báo bắt buộc, không thể giao video DEMO như video thật.
- Không bao giờ có trạng thái AUTO_PUBLISH_READY; workflow.handoff chỉ ra AWAITING_HUMAN_FINAL_REVIEW.

## Các lỗi có thể tự sửa
- MISSING_SRT, INVALID_SRT: scripts/qa_repair.py đọc cues gốc từ _work/props-9x16.json và/hoặc props-16x9.json đã lưu, tạo lại subtitle sidecar trong thư mục sửa chữa riêng, ghi repair_audit.json, QA lại.
- Nếu SRT là nguồn đã được dựng/cháy vào MP4, sửa sidecar chỉ phục hồi tệp ngoài; KHÔNG biến đổi phụ đề cháy trong MP4. Khi lỗi thực tế thuộc phụ đề cháy, cần render lại.
- GPU/NVENC: workflow.py render tự thử lại 1 lần bằng CPU chỉ khi lỗi có dấu hiệu thiết bị/hardware thực sự. Giữ attempt-01 và attempt-02 riêng.
- Không tự sửa mất/câm âm thanh, video hỏng codec, lỗi cảnh/giấy phép, phát ngôn sai hay tin lỗi thời. Phải dừng và quay lại giai đoạn chịu trách nhiệm.
- Không ghi đè video, bản thảo, hash, approval hay media nguồn.

## Dùng độc lập
Trong PowerShell, thêm thư mục (Join-Path $runtime 'tools\ffmpeg-selected') vào PATH. Ví dụ:
  & $py -B (Join-Path $skill "scripts\qa_engine.py") --folder <OUTPUT_DIR> --expect both --report <QA_UNIQUE.json>
  & $py -B (Join-Path $skill "scripts\qa_repair.py") --folder <OUTPUT_DIR> --qa <QA_FILE> --out <NEW_REPAIRED_DIR>

QA đầu tiên thất bại với mã lỗi 2 vẫn tạo được QA JSON để điều tra; trình sửa chỉ được gọi nếu toàn bộ lỗi thuộc MISSING_SRT/INVALID_SRT. Sau khi sửa, bắt buộc QA lại sang report mới.
Khi dùng workflow:
  & $py -B (Join-Path $skill "scripts\workflow.py") qa --job <JOB_DIR>
Kết quả được lưu trong technical_qa.json; một job chỉ có một lần nghiệm thu, không ghi đè. Nếu phải thay đổi kịch bản/media sau phê duyệt cần job mới và xin người dùng phê duyệt lại.

## Bằng chứng thử nghiệm Đợt 4
- QA hai video 9:16+16:9 giai đoạn trước: D:\skill-tintuc-runtime\logs\stage4-qa-baseline-20261023.json — TECHNICAL_PASS_REVIEW_REQUIRED.
- Bản sao cố ý xóa SRT ngang: D:\skill-tintuc-runtime\output\stage4-corrupt-srt-fixture-20261023.
- Kết quả QA phát hiện MISSING_SRT:16:9: D:\skill-tintuc-runtime\logs\stage4-corrupted-qa.json.
- Thư mục khôi phục riêng: D:\skill-tintuc-runtime\output\stage4-repaired-srt-20261023.
- QA sau khôi phục: D:\skill-tintuc-runtime\logs\stage4-repaired-qa.json — TECHNICAL_PASS_REVIEW_REQUIRED.
- Thư mục nguồn cố ý hỏng vẫn thiếu SRT, chứng minh không ghi đè.

## Giới hạn tính năng
- Không có vision tự động xác thực mọi frame hoặc kiểm duyệt nội dung thật của video.
- Không có forced word alignment; SRT theo cụm thời lượng WAV.
- Không có full semantic fact-check bằng phần mềm và không có kiểm toán quyền pháp lý tự động.
- Không tự động chạy khi ChatGPT chưa thực thi hoặc máy chủ Remote Desktop Commander mất kết nối; trạng thái job vẫn giữ trên ổ.
