# Đợt 5 — Kiểm thử tích hợp, QA hình/âm thanh và hiệu năng (26–29)

**Trạng thái:** triển khai mã nguồn và chạy CI nguồn; **không được tuyên bố đã dựng/nghe/xem video thực tế trên Windows từ CI GitHub**. Dự án vẫn `1.0.0-rc.2`, không được tự đăng TikTok/YouTube.

## 26 — Test hợp đồng phê duyệt, pipeline và an toàn
- Toàn bộ bộ test nguồn hiện hữu + `tests/test_stage5_qa.py` chạy mỗi Pull Request và commit `main`.
- Bài test âm tính kiểm tra phụ đề lỗi, âm thanh quá lớn hoặc im lặng, nhiều khung hình đen, bố cục vượt giới hạn, hash/tệp gốc không bị sửa.
- Bộ test dùng dữ liệu giả lập và mock với các nhánh khó tái hiện. Các test có một phần kiểm tra hành vi thật của FFmpeg ở mục 28.

## 27 — QA tự động
- `qa_engine.py` chặn **mức độ nghiêm trọng**: SRT sai, phụ đề bao phủ dưới 30% clip, cue dài hơn 110 ký tự, trung bình âm thanh quá lớn, im lặng kéo dài hơn 80% clip và hai hoặc nhiều frame được lấy mẫu gần đen.
- Một điểm đen đơn lẻ, subtitle dài nhưng trong giới hạn, peak gần 0 dB, silence ở mức cảnh báo được báo để con người xem/nghe.
- Kiểm tra tĩnh `inspect_caption_and_layout` xác nhận văn bản Remotion không vượt hợp đồng tối đa và đánh dấu tiêu đề/tóm tắt/phụ đề dài. Kiểm tra này **không chứng minh** chữ đã vừa trên hình. Để đánh giá chính xác chữ cắt/đè, cần mở ảnh khung hình render và xem.
- Các media đã duyệt và file mp4 gốc không được sửa khi chạy QA. Báo cáo đầu ra tạo riêng.

## 28 — Tám video kiểm thử giả lập trên CI
- `.github/workflows/source-checks.yml` chạy `scripts/stage5_media_smoke.py` trên GitHub Ubuntu runner.
- Bộ smoke tạo hai seed (1080×1920, 1920×1080, H.264/AAC/30 FPS), lặp stream để có các tệp giả lập 30/60/90/180 giây. **Tổng: 8 MP4**, không phải footage từ Remotion hay giọng Piper.
- Chạy QA thực `ffprobe`, `ffmpeg` âm thanh, SRT, duration và lấy mẫu frames. Kết quả JSON được tải lên GitHub Actions Artifacts, không commit MP4 vào repository.
- Bắt buộc ghi `synthetic_two_second_clip_repeated=true`, `remotion_rendered=false`, `piper_used=false` và `windows_independent_acceptance=false`; không dùng kết quả này để tuyên bố đạt visual/motion/voice/GA.
- Trong DEMO nguồn tin `example.com` mang tính giả lập, không phát video này lên mạng.

## 29 — Kiểm thử hiệu năng GPU/CPU có số liệu thật
- `scripts/stage5_perf_audit.py` đối chiếu thời gian render, mức RAM của process tree, sampling, encoder đã thực sự dùng cho mỗi ratio và sai số duration ≤5% trên báo cáo `stage5_benchmark.py` + `qa_engine.py`. Nó **không tự tạo** số đo.
- Khi yêu cầu NVENC, cả hai tỷ lệ phải thật sự báo `h264_nvenc`. Khi yêu cầu CPU, phải báo `libx264`. Chế độ auto cho phép fallback và ghi rõ encoder.
- `nvidia-smi` theo dõi toàn GPU, không đại diện mức VRAM tuyệt đối của riêng job. Nếu GPU không có hoặc model Piper chưa cài, không được suy ra hiệu năng.
- Kiểm tra thời gian người dùng đã duyệt với Piper cần **mẫu WAV thực tế**. Hiệu năng và chất lượng GPU/CPU không thể xác nhận chỉ từ source CI.

## Nghiệm thu Windows đầy đủ (cần máy Windows thực tế)
Sao chép bộ nguồn sạch từ GitHub đến máy Windows, cài runtime riêng, FFmpeg/ffprobe, Remotion/Chrome, Piper ONNX và kiểm tra GPU/NVENC. Chạy script khi máy sẵn sàng:

```powershell
python scripts/stage5_windows_acceptance.py --out "D:\\skill-tintuc-stage5-validation" --encoder auto --compare-cpu
```

- Tạo 4 kịch bản **DEMO** 30 EN, 60 VI, 90 EN, 180 VI, mỗi mục 9:16 và 16:9.
- Calibrate lời dẫn bằng Piper thật (sai lệch ≤5%), render Remotion native 30fps, đo thời gian, CPU/RAM/NVIDIA device telemetry và QA video/audio/SRT/frame.
- `--compare-cpu` kiểm tra thêm CPU 30 giây. Muốn kiểm tra NVENC bắt buộc thay `--encoder nvenc` khi máy có encoder được FFmpeg kiểm chứng.
- Không ghi vào Skill gốc và không ghi đè dữ liệu cũ. Kết quả gồm báo cáo từng profile và `stage5-windows-summary.json`.
- Sau khi có PASS kỹ thuật, người dùng phải **nghe** tiếng Việt/Anh, xem video cả hai tỷ lệ ở nhiều đoạn, xác nhận có không bị cắt chữ, nhạc không lấn tiếng, crop/B-roll đúng chủ thể, giấy phép hợp lệ. Sau đó mới chuyển sang Đợt 6/GA.

## Điều kiện công bố
- CI source + synthetic-media matrix + source SHA256 PASS là đủ kết thúc **công việc mã nguồn Đợt 5**, nhưng **không đủ chứng nhận nghiệm thu Windows độc lập**.
- Không phát hành GA khi chưa có bằng chứng thực từ máy mới và kiểm cuối của người dùng.
