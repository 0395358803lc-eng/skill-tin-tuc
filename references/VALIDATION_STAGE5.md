# Stage 14–15 — Hướng dẫn kiểm thử bản tin thật và video dài (v0.5.1)

**CHUYỂN MÁY (v1.0.0-rc.2):** Đọc `references/PORTABILITY_CONTRACT.md`, thiết lập `$skill`, `$runtime`, `$py` trên đúng máy. Đường dẫn ổ D:, ADMIN-PC-02, job và benchmark trong tài liệu giai đoạn chỉ là ví dụ/hồ sơ lịch sử; **không chạy nguyên văn trên máy mới**. Quy trình hiện tại theo `AGENT_RUNBOOK.md`.


## Trạng thái và giới hạn nghiệm thu
- Giai đoạn 14 cần người dùng thực sự lựa chọn tin và duyệt toàn văn kịch bản. Thỏa thuận triển khai giai đoạn không được dùng thay cho hai quyết định nội dung.
- Job chuẩn bị tin thật: `D:\skill-tintuc-runtime\jobs\stage5-evidence72-20261024`, trạng thái AWAITING_SELECTION, 2 sự kiện có hồ sơ nguồn để biên tập viên đánh giá. Từng bản tin phải kiểm lại tính thời sự khi người dùng chọn.
- Thử nghiệm kỹ thuật 30/60/90/180 sử dụng **dữ liệu giả lập có demo=true, video watermark DO NOT PUBLISH**. Không phải bằng chứng đã hoàn thành xuất bản tin thật.

## Kiểm thử video dài
- `scripts/stage5_fixture.py` tạo dataset kỹ thuật có số lượng tin theo thời lượng và nội dung hoàn toàn giả lập (cấm đăng).
- `scripts/stage5_benchmark.py` chạy video_pipeline.py, đo tổng thời gian, RAM theo cây tiến trình, GPU utilization và VRAM máy qua nvidia-smi; chỉ dùng demo. Cần `pip install -r requirements-benchmark.txt`.
- Piper backend mặc định `inprocess`: nạp một lần model và tái sử dụng qua các đoạn. Để thử tương thích backend cũ, đặt `PIPER_BACKEND=subprocess`; không nên dùng cho bản tin dài vì nạp model lặp lại gây chậm.
- Remotion production luôn render 30 FPS gốc, không có lấy mẫu frame. Với thử nghiệm dài có thể dùng `--demo-sample-every 5` hoặc `10`: kết xuất ít frame hơn và FFmpeg lặp frame để tạo video nominal 30 FPS. Bản video này **KHÔNG đạt chuẩn chuyển động 30 FPS gốc**, chỉ dùng để kiểm stress audio, subtitle, timeline, mux và QA.
- `qa_engine.py` cảnh báo DEMO frame sampling, video ngắn hơn 85% target, phụ đề ít hơn 60% thời lượng; không tự suy diễn nội dung đã được kiểm chứng.
- Khi báo lỗi, không ghi đè input/output; mỗi lần thử dùng thư mục mới.

## Lệnh mẫu trên ADMIN-PC-02
```powershell
$py = Join-Path $runtime '.venv\Scripts\python.exe'
$root = Join-Path $runtime 'stage5-bench'
& $py -B "$skill\scripts\stage5_fixture.py" --seconds 90 --language en-US --aspect both --out "$root\new-demo90.json"
& $py -B "$skill\scripts\stage5_benchmark.py" --input "$root\new-demo90.json" --out "$root\new-demo90-output" --report "$root\new-demo90-metrics.json" --encoder auto --demo-sample-every 5
# Chỉ DEMO stress. Bỏ --demo-sample-every để kiểm nghiệm full native 30fps.
$env:PATH=(Join-Path $runtime 'tools\ffmpeg-selected')+';'+$env:PATH
& $py -B "$skill\scripts\qa_engine.py" --folder "$root\new-demo90-output" --expect both --report "$root\new-demo90-qa.json"
```

## Kết quả đã có tính đến 2026-10-24
| Cấu hình mục tiêu | Chất lượng motion gốc | Độ dài audio+MP4 | Tổng thời gian chạy | Phương thức | Kết quả |
| --- | --- | --- | --- | --- | --- |
| 30s, 1 tin, hai tỷ lệ | 30 FPS | 25.00s | 216.35s | Remotion đầy đủ + Piper + NVENC | PASS kỹ thuật |
| 60s, 3 tin, hai tỷ lệ | 30 FPS | 47.63s | 384.31s | Remotion đầy đủ + Piper + NVENC | PASS kỹ thuật |
| 90s, 4 tin, hai tỷ lệ | 6 FPS gốc, output lặp thành 30 FPS | 74.20s | 148.64s | DEMO sampled x5 | PASS kỹ thuật / KHÔNG chuẩn motion gốc |
| 180s, 5 tin, hai tỷ lệ | 3 FPS gốc, output lặp thành 30 FPS | 154.77s | 173.30s | DEMO sampled x10 | PASS kỹ thuật / KHÔNG chuẩn motion gốc |

Các bài trước ghi ngưỡng cảnh báo thấp hơn 85% target. Sau kiểm tra native 180, ngưỡng cảnh báo QA được nâng lên dưới 90% target để nhận diện cả bài 180s khi lời dẫn chỉ khoảng 155s; đây là cảnh báo biên tập, không phải lỗi codec.
- RAM peak 60s: 2075.5 MB; 90s: 2078.3 MB; 180s: 2023.2 MB.
- GPU memory máy peak 60s: 583 MB; 90s: 582 MB; 180s: 607 MB.
- GPU utilization máy peak 60s: 39%, 90s: 34%, 180s: 35%.
- Tổng VRAM/GPU là chỉ số toàn máy tại thời điểm lấy mẫu, không phải số liệu riêng tiến trình đã tách.
- Thư mục metrics: `D:\skill-tintuc-runtime\stage5-bench`; báo cáo `benchmark-*.json` và `qa-final-*-both.json`.
- Pipeline không tự dựng media bên ngoài thiếu giấy phép, và không đăng TikTok/YouTube.

## Công việc chưa đáp ứng nghiệm thu đầy đủ
- Stage 14: Chưa có người dùng chọn ID và duyệt kịch bản, nên chưa có MP4 từ job tin thật đủ nguồn. Không được làm giả lời duyệt.
- Stage 15: 90 và 180 giây chưa nghiệm thu full native 30 FPS Remotion ở cả hai bố cục; chỉ đạt stress test video nominal 30 FPS. Cần lần lượt chạy native dài khi cân đối thời gian/máy hoặc sau tối ưu.
- Thời lượng giọng đọc chưa luôn sát mục tiêu, dù audio codec/SRT đúng. Có thể cải tiến ở giai đoạn sau bằng dự toán số chữ theo ngôn ngữ, tốc độ TTS, tự phát hiện lệch và trình biên tập chỉnh số từ.
- Hiệu năng dài phụ thuộc CPU/Chrome và có thể vượt nhiều lần thời lượng clip. Đừng khẳng định NVENC tăng tốc toàn pipeline.

## Bổ sung kết quả native 90/180 sau phiên tiếp tục v0.5.2

- 90 giây mục tiêu, 4 tin DEMO: hai video native 30 FPS đạt H264/AAC NVENC và QA không lỗi, duration thực 75,60 giây, thời gian dựng 582,28 giây.
- 180 giây mục tiêu, 5 tin DEMO: hai video native 30 FPS đạt H264/AAC NVENC và QA không lỗi, duration thực 155,17 giây, thời gian dựng 1102,11 giây, concurrency 3.
- QA được nâng cấp lưu ảnh tại giữa từng story, không chỉ các mốc timeline. `qa90-native30-story-frames.json`, `qa180-native30-story-frames.json` lưu kết quả.
- Cảnh báo duration nếu thấp hơn 90% target; cả 90/180 đều có cảnh báo biên tập. Không được gọi 155 giây là video thực sự dài đúng 180 giây.
- Hệ thống có `scripts/duration_planner.py` để dự kiến số từ/âm tiết trước khi người dùng phê duyệt. Sai lệch do phát âm và ngữ điệu phải kiểm bằng WAV thật. Không tự thay đổi approved script.
- Đã sửa benchmark speech-rate được truyền bằng CLI thay vì chỉ environment, do pipeline override biến môi trường bằng CLI default. **Các benchmark cũ có metadata tốc độ .85/.86 nhưng giọng tổng hợp thực tế ở rate mặc định 1.0;** không được dùng benchmark cũ để đo tác động tăng giảm tốc độ.
- Có tùy chọn Remotion concurrency 1..4 (mặc định 1); sample frames chỉ DEMO, còn sản xuất thật native30. Remotion intermediate có `--x264-preset veryfast --crf 18` đã thử đoạn 90 frame, chưa benchmark tốc độ cải thiện đầy đủ.
- Stage 14 job tin thật đang `AWAITING_SELECTION`. Người dùng tự chọn và phê duyệt lần hai; không có video tin thật sản xuất mà thiếu các cổng này.
