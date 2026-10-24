# STAGE 15 — Hướng dẫn kiểm thử thời lượng, hiệu năng, độ ổn định

**CHUYỂN MÁY (v1.0.0-rc.2):** Đọc `references/PORTABILITY_CONTRACT.md`, thiết lập `$skill`, `$runtime`, `$py` trên đúng máy. Đường dẫn ổ D:, ADMIN-PC-02, job và benchmark trong tài liệu giai đoạn chỉ là ví dụ/hồ sơ lịch sử; **không chạy nguyên văn trên máy mới**. Quy trình hiện tại theo `AGENT_RUNBOOK.md`.


Ngày nghiệm thu: 2026-10-24. Skill tại `D:\skill-tintuc`; runtime và kết quả tại `D:\skill-tintuc-runtime`. Mọi kiểm thử tạo dữ liệu mới trong runtime ngoài thư mục Skill; không làm biến đổi approved brief hay video tin thật. **Không tự đăng TikTok/YouTube.**

## 1. Tiêu chí và phân loại nghiệm thu
- Thời lượng: đo âm thanh Piper qua số mẫu WAV, sau đó FFprobe MP4. Mức kỹ thuật đặt mục tiêu **sai lệch trong ±5%** cho bộ DEMO sau hiệu chỉnh. Kịch bản của tin thật chỉ được biên tập **trước khi người dùng duyệt**.
- Hai bố cục bắt buộc 1080×1920 và 1920×1080, H264/AAC, 30 FPS **gốc**. Khi `--demo-sample-every` lớn hơn 1, MP4 vẫn có thể mang thông số 30 FPS do lặp frame, nhưng **không** tính nghiệm thu chất lượng motion native.
- Âm thanh kiểm codec, peak/mean, im lặng kéo dài; SRT kiểm cue tăng dần, không vượt duration, độ phủ >=60%. Video QA kỹ thuật phải `technical_pass=true`, `errors=[]`. Các cảnh báo biên tập cần được người duyệt đọc riêng.
- Trước đăng: người dùng cần xem/nghe toàn bộ MP4, kiểm tra tin còn mới, độ chính xác, media rights, font, giọng và chính sách nền tảng. QA kỹ thuật không chứng nhận những điều đó.
- Benchmark CPU/NVENC trên cùng đoạn chỉ có giá trị tham khảo. NVENC tăng tốc mã hóa cuối; thời gian Remotion/Chromium có thể chiếm phần lớn.

## 2. Thao tác trước khi khóa kịch bản tin thật
1. Viết bản SCRIPT.json có `narration`, `target_seconds` và `language`. Gọi `scripts/duration_planner.py --brief SCRIPT.json --out UNIQUE_ADVISORY.json` để có ước lượng nhanh.
2. **Trước** `workflow.py draft` và trước hai giai đoạn người dùng duyệt, chạy Piper đo thật:

```powershell
$py = Join-Path $runtime '.venv\Scripts\python.exe'
& $py -B "$skill\scripts\tts_duration_preflight.py" --input "$runtime\jobs\<job_id>\editorial_candidate.json" --out "$runtime\jobs\<job_id>\duration-preview-01"
```

3. Xem `duration_preflight.json` và `narration.wav`. Nếu lệch trên 5%, sửa **editorial_candidate.json chưa đóng băng**, tạo preflight mới `duration-preview-02`. Không ghi đè, không cắt xén hay tự sửa `approved.json`. Khi đạt mới gọi `workflow.py draft`, trình người dùng duyệt hash.
4. Thiếu model Piper/công cụ: báo **chưa đo**, không tự tuyên bố PASS. Dự đoán số từ chỉ là lời khuyên, phát âm thực có thể khác.

## 3. Bài DEMO có thể lặp lại
```powershell
$py = Join-Path $runtime '.venv\Scripts\python.exe'
$skill = (Resolve-Path .).Path
$runtime = if ($env:NEWS_SKILL_RUNTIME) { $env:NEWS_SKILL_RUNTIME } else { "$skill-runtime" }

# Tạo bốn manifest giả lập, hiệu chỉnh thực bằng Piper 1-3 lần, không tạo video tin thật:
& $py -B "$skill\scripts\stage15_duration_calibrate.py" --root "$runtime\stage15-calibration-NEW"

# Render 30 FPS gốc từ DEMO đã hiệu chỉnh. Dùng folder và report chưa tồn tại:
& $py -B "$skill\scripts\stage5_benchmark.py" --input "$runtime\stage15-calibration-NEW\target-30-en-US\calibrated_demo.json" --out "$runtime\stage15-render-30-NEW" --report "$runtime\stage15-benchmark-30-NEW.json" --encoder auto --remotion-concurrency 2 --timeout 1800

# Kiểm thử hiệu năng trên cùng 120 frame source với CPU và NVENC. Kết quả chỉ để so sánh mã hóa:
& $py -B "$skill\scripts\stage15_encoder_benchmark.py" --source "$runtime\stage5-bench\demo60-both-render\_work\remotion-16x9.mp4" --out "$runtime\stage15-encoder-NEW" --repetitions 3

# Kiểm tra ổn định, lỗi SRT/MP4 cố ý và checksum mà không sửa dữ liệu:
& $py -B "$skill\scripts\stage15_stability.py" --bench "$runtime\stage5-bench" --delivery "$runtime\deliveries\Tin-Cong-Nghe-My-20261024-60s" --root "$runtime\stage15-stability-NEW"

# Chạy unit tests hồi quy:
& $py -B -m unittest discover -s "$skill\tests" -q
```

## 4. Mốc đo lịch sử đã xác nhận
- DEMO native 30: target 30s, actual 25s, hai tỷ lệ; 216,35s xử lý.
- DEMO native 60 tiếng Việt: target 60s, actual 47,63s, hai tỷ lệ; 384,31s xử lý.
- DEMO native 90: target 90s, actual 75,60s, hai tỷ lệ; 582,28s xử lý.
- DEMO native 180: target 180s, actual 155,17s, hai tỷ lệ; 1102,11s xử lý.
- VIDEO THẬT (bản tin Mỹ 24/10, job Giai đoạn 14): 62,97s, native30, hai tỷ lệ, bản ngang đã sửa lỗi bố cục; QA cuối PASS và ở trạng thái chờ con người duyệt.
- **Các số benchmark trước khi sửa `--speech-rate` thực truyền vào pipeline không thể dùng để khẳng định đo thay đổi tốc độ đọc .85/.86.**
- DEMO sampled 90/180 có thể qua codec QA nhưng chuyển động nguồn chỉ 6/3 FPS, **không** được tính tương đương 30 FPS thật.

## 5. Độ ổn định và an toàn
- Tất cả bài test là DEMO watermark, không được phát hành.
- Khi bộ benchmark Python đã khởi chạy nhưng video_pipeline không tạo output trong 90s, watchdog ở stage5_benchmark.py chỉ dừng cây tiến trình **thuộc benchmark đó**; giữ nguyên job khác và báo lỗi. Trường hợp chính Python launcher bị treo trước khi chạy code thì watchdog bên trong chưa hoạt động: Agent phải kiểm tra PID và dừng đúng cây tiến trình đó trước khi thử lại. Mỗi lần chạy lại dùng thư mục/tên báo cáo MỚI.
- Khi máy mất kết nối, chỉ kiểm tra PID, job, log và checksum rồi tiếp tục; không xóa tự động data đã có.
- QA nhiều lần phải trùng SHA-256 MP4; thử lỗi thiếu MP4, MP4 hỏng và SRT hỏng phải fail có mã cụ thể.
- Dùng `requirements-benchmark.txt` nếu cần psutil; máy chưa có GPU thì `encoder=auto` có thể dùng CPU, `encoder=nvenc` phải báo lỗi rõ ràng.
- Benchmark memory là RAM nhóm tiến trình lấy mẫu; VRAM/GPU utilization của nvidia-smi là **toàn thiết bị**, có thể có ứng dụng khác chạy.
- Khi chuyển máy: thiết lập Python, Piper và Remotion theo INSTALL_WINDOWS.md; không copy dữ liệu runtime/log/job cũ làm thành bộ não Skill.

## 6. Báo cáo
Báo cáo nghiệm thu theo phiên được lưu bên ngoài gói Skill phát hành; khi kiểm trên máy mới tạo bằng chứng trong runtime mới.
