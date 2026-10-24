# Giai đoạn 18–19 — Giọng đọc, phụ đề nhấn từ và Smart Crop

**CHUYỂN MÁY (v1.0.0-rc.2):** Đọc `references/PORTABILITY_CONTRACT.md`, thiết lập `$skill`, `$runtime`, `$py` trên đúng máy. Đường dẫn ổ D:, ADMIN-PC-02, job và benchmark trong tài liệu giai đoạn chỉ là ví dụ/hồ sơ lịch sử; **không chạy nguyên văn trên máy mới**. Quy trình hiện tại theo `AGENT_RUNBOOK.md`.


Phiên bản AI News Video Skill kế tiếp, sản xuất nội bộ trên Windows bằng Piper, Remotion, FFmpeg, Pillow và OpenCV local. ChatGPT điều phối, người dùng CHỌN TIN, duyệt chính xác nội dung và tự đăng video. Không gọi dịch vụ thị giác/giọng nói bên ngoài và không triển khai API đăng tự động.

## Giai đoạn 18: Giọng đọc AI và phụ đề thông minh

1. **18.01 Đánh giá Piper** — model Việt Nam và tiếng Anh phải được tải local; Piper tạo WAV theo từng cụm, ghi thời lượng từ số mẫu âm thanh. Không khẳng định cảm nhận tự nhiên chỉ qua máy đo.
2. **18.02 Từ điển thuật ngữ** — `-Lexicon` chứa JSON sửa cách đọc (không đổi phụ đề). Dữ liệu ngôn từ người dùng duyệt phải giữ nguyên. Với kịch bản THẬT, SHA-256 từ điển phải có trong brief được phê duyệt; không dùng từ điển chưa duyệt sửa giọng.
3. **18.03 Nhịp đọc** — Piper hỗ trợ speech rate 0.75–1.35. Chạy `tts_duration_preflight.py` trước khi khóa/hash script; đo đúng WAV, điều chỉnh bản nháp chưa duyệt nếu lệch ±5%.
4. **18.04 Căn chỉnh audio–text** — chunks dựa WAV thực, SRT theo cụm. File `voice_qa.json` ghi sample rate, duration, cue count, coverage và các cảnh báo.
5. **18.05 Nhấn từ** — `narration_quality.enrich_cues` tạo thời gian từng từ **ước lượng bên trong cue** với tốc độ theo độ dài từ. Remotion tô sáng từ đang dự đoán, không dùng bản này để chứng minh độ chính xác từng âm tiết. `word_forced_alignment_performed:false` luôn hiển thị rõ. Chưa cài Whisper/MFA hoặc forced aligner.
6. **18.06 Phụ đề hai tỷ lệ** — Remotion nhận cue và highlight; 9:16/16:9 có fontsize, vị trí và giới hạn chiều cao riêng; SRT chứa nguyên văn.
7. **18.07 Mix nhạc và chuẩn âm lượng** — chỉ sử dụng nhạc khi approved brief chứa minh chứng quyền. FFmpeg ducking nhạc dưới lời nói và loudnorm; QA đo mean/max dB, phát hiện mute/im lặng dài.
8. **18.08 QA kỹ thuật** — kiểm timeline không chồng, độ phủ phụ đề, số/số liệu đọc cần nghe lại, nguồn từ điển; nghe thực tế và xác nhận tên riêng vẫn là công việc AI/người dùng trước đăng.

## Giai đoạn 19: Media rights và Smart Crop

1. **19.01 Phát hiện media** — sử dụng media_catalog.py/Wikimedia chỉ để thu nguồn và quyền ở dạng ỨNG VIÊN. Không tự lấy ảnh thiếu giấy phép.
2. **19.02 Rights Ledger** — Smart Crop chỉ áp dụng cho scene có `type: licensed_image` hoặc `licensed_broll`, file nằm trong job, và `media_sha256`, `license_evidence`, `source_url`, `author`, `license_name`, `attribution` đầy đủ. Metadata được giữ trong `media_rights.json` và `smart_crop_report.json`. Quyền thương mại phải do người dùng kiểm lại.
3. **19.03 Focal detection local** — `smart_media.py` sử dụng OpenCV Haar để phát hiện khuôn mặt, fallback sang saliency biên cạnh CPU (không phân biệt danh tính). Khi ảnh ít texture, focal về trung tâm với độ tin cậy LOW.
4. **19.04 Smart Crop still** — ảnh EXIF transpose, cover/aspect preservation, resize LANCZOS; không kéo dãn, focal tự chọn chỉ khi user đã bật `smart_crop:true`. Nếu có tọa độ focal_x/y do user nhập, KHÔNG tự ghi đè.
5. **19.05 Smart Crop B-roll** — lấy 7 frame theo thời lượng clip và chu kỳ nguồn, phát hiện focus, giới hạn đổi tâm 0.2 mỗi mẫu; FFmpeg biểu thức nội suy theo t, crop dynamic cho 9:16 và 16:9 riêng. Lưu vết x/y từng frame mẫu, không giả nhận dạng ngữ nghĩa cảnh.
6. **19.06 Đúng cảnh và phân cảnh** — scene thuộc `visual_plan` của brief đã phê duyệt; Remotion chia timeline theo từng scene và narration. Không tạo footage minh chứng từ AI, không ghép sai sự kiện khác khi chưa được duyệt.
7. **19.07 Infographic hợp nguồn** — chart/overlay chỉ lấy data_points trong approved scene. Trường hợp thiếu quyền sử dụng media, fallback đồ họa gốc chỉ khi được kịch bản/phê duyệt cho phép; tuyệt đối không tự giả biến dữ liệu.
8. **19.08 QA** — FFprobe H264/AAC 30fps và 1080x1920/1920x1080, rà cảnh đen, im lặng, SRT, nội suy crop, checksum nguồn, hình mờ/cắt nội dung, chồng chữ, bản quyền và thông tin bối cảnh. `LOW` focal => cảnh báo kiểm mắt; không phải PASS thị giác vô điều kiện.

## Cách dùng trong một brief trước khi duyệt

```json
{
  "type": "licensed_image",
  "instruction": "Hình minh họa hợp bối cảnh, không giả làm ảnh sự kiện",
  "media_path": "approved_assets/shot01.jpg",
  "media_sha256": "<SHA256 đúng 64 ký tự>",
  "license_evidence": "Giấy phép và URL dẫn tới điều khoản rõ ràng",
  "source_url": "https://...",
  "author": "Tác giả/đơn vị sở hữu",
  "license_name": "Tên giấy phép đã kiểm tra",
  "attribution": "Credit xuất bản phù hợp",
  "smart_crop": true,
  "claim_ids": ["CLAIM_01"]
}
```

**Ghi chú:** Smart Crop là **opt-in**, thêm vào visual_plan trước khi người dùng phê duyệt; bản approved cũ mặc định giữ crop manual/center như trước. Để người dùng buộc điểm nhìn cụ thể, cung cấp focal_x/focal_y 0–1. Không cắt mặt hay bằng chứng quan trọng; nếu hiện ảnh sai bối cảnh, đổi media khi còn giai đoạn draft và xin duyệt lại.

## Tính di động
- `pip install -r requirements.txt` cho bộ tối thiểu; bổ sung `pip install opencv-python-headless` vào venv local để Smart Crop video và face tracking. Khu vực không có OpenCV: ảnh dùng saliency từ Pillow, video auto crop báo thiếu tool (không âm thầm khai báo thành công).
- Runtime `$runtime\remotion` phải được đồng bộ bằng `scripts/setup_remotion.ps1` sau khi cập nhật `remotion-template/src`.
- Tất cả file báo cáo, clip DEMO, model voice, output MP4 ở runtime, không đóng gói vào Skill Markdown/code.
- Không tạo MP4 cho những scene media ngoài job hoặc không khớp SHA256. Bản tin thật phải qua QA và duyệt cuối trước khi người dùng tự đăng.

## Giới hạn nghiệm thu
Word timings ước lượng trong mỗi WAV chunk, **chưa có forced alignment** hay kết quả kiểm chứng từng âm vị; nhấn màu chỉ tăng trải nghiệm khi xem. Haar cascade mặt và saliency/di chuyển hình không hiểu ý nghĩa tin; các tình huống khuôn mặt nhiều người, chuyển cảnh nhanh, logo, chữ, footage mờ hoặc thiếu sáng cần rà mắt và có thể chọn focal manual.
