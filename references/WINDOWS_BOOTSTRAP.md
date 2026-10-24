# Cài đặt và kiểm tra runtime trên Windows — bộ nguồn v1.0.0-rc.2

Mục tiêu: sau khi giải nén Skill ở vị trí bất kỳ, AI Agent xác định công cụ cần thiết và báo thiếu phụ thuộc **trước** khi tạo runtime hoặc dựng video. Tài liệu này đi kèm `PORTABILITY_CONTRACT.md` và `INSTALL_WINDOWS.md`.

## A. Kiểm tra chỉ-đọc, không thay đổi máy

Mở PowerShell trong thư mục chứa `SKILL.md`. Chuẩn bị FFmpeg/ffprobe và các model ONNX+JSON được phép sử dụng trong những thư mục riêng do người dùng cung cấp.

```powershell
$skill = (Resolve-Path .).Path
$runtime = "$skill-runtime"
$ffmpegSource = '<THU_MUC_CHUA_FFMPEG_EXE_VA_FFPROBE_EXE>'
$voiceModelsSource = '<THU_MUC_CHUA_ONNX_VA_ONNX_JSON>'
& (Join-Path $skill 'scripts\bootstrap_windows.ps1') -Runtime $runtime -FFmpegSource $ffmpegSource -VoiceModelsSource $voiceModelsSource -CheckOnly
```

Lệnh trên chỉ đọc và xuất JSON: `python_313`, `node`, `npm`, `chrome`, `ffmpeg_and_ffprobe`, `piper_vi_en_models`, `runtime_safe`, `missing`. Mã lỗi 2 là thiếu điều kiện, **không có nghĩa môi trường đã được cài hay render thành công**. Nếu runtime cũ không rỗng, preflight báo `runtime_safe=false` trừ khi truyền `-AcceptExistingRuntime`; phải xem dữ liệu đang có trước khi quyết định cập nhật.

Trường hợp Chrome/Chromium nằm ở vị trí riêng, đặt một biến môi trường trước cả preflight và render (giữ nguyên trong phiên Agent):

```powershell
$env:NEWS_CHROME_PATH = '<DUONG_DAN_CHROME_EXE_HOP_LE>'
```

Biến thay thế `REMOTION_BROWSER_EXECUTABLE` cũng được hỗ trợ; nếu override sai, doctor không âm thầm dùng browser khác. Nếu không override, hệ thống thử PATH và các vị trí cài Chrome/Chromium phổ biến. Không tự cài/truy cập trình duyệt ngoài quyền được cấp.

## B. Cài đặt khi đã sẵn sàng

```powershell
& (Join-Path $skill 'scripts\bootstrap_windows.ps1') -Runtime $runtime -FFmpegSource $ffmpegSource -VoiceModelsSource $voiceModelsSource
```

Lệnh thường tạo Python 3.13 venv trong **runtime ngoài Skill**, cài Python packages qua pip và Remotion qua `npm.cmd ci`, sao chép FFmpeg/Piper từ thư mục được chỉ định, kiểm tra `doctor.py` và chạy unittest. pip/npm có thể sử dụng mạng để tải dependencies; AI Agent phải được người dùng cho phép trước khi cài. **Không tự tải model giọng, không sửa driver, không ghi đè nguồn video, không tự đăng.**

Nếu runtime chưa trống, mặc định DỪNG; `-AcceptExistingRuntime` cho phép tiếp tục sau khi đã kiểm tra thủ công, nhưng file model/FFmpeg trùng tên vẫn không được ghi đè. Remotion chỉ thay nội dung source khác hash khi có `-AllowSourceUpdate`; gọi riêng khi chủ động nâng cấp và có backup.

## C. Chẩn đoán thực tế và bộ mã hóa

```powershell
$py = Join-Path $runtime '.venv\Scripts\python.exe'
& $py -B (Join-Path $skill 'scripts\doctor.py') --runtime $runtime
& $py -B -m unittest discover -s (Join-Path $skill 'tests') -q
```

Các trạng thái quan trọng:
- `ready_dual_aspect` và `ready_to_render`: chỉ true khi Python, FFmpeg (có libass/subtitles), FFprobe, hai giọng, Node/npm, Chrome/Chromium, Remotion và bộ mã hóa H.264 thực sự đủ.
- `nvenc_operational` và `cpu_h264_operational`: kiểm mã hóa một frame thật bằng FFmpeg; `recommended_encoder` là `nvenc` nếu GPU tương thích, hoặc `cpu` khi libx264 đạt. Không suy ra NVENC chỉ từ `nvidia-smi`.
- `missing_requirements` và `recommended_actions`: báo thành phần thiếu, không tự cài hay tự sửa.
- `stage19_smart_crop`: OpenCV local cần để crop video nâng cao. Kết quả chẩn đoán không chứng minh bản quyền media hay chất lượng biên tập.

`workflow.py render --encoder auto` chọn NVENC có hoạt động thực hoặc CPU fallback. Nếu thiếu cả hai bộ mã hóa, DỪNG. CPU fallback có thể chậm hơn GPU, nhưng không được bỏ QA.

## D. Giới hạn nghiệm thu

Các bài kiểm thử logic và chế độ `-CheckOnly` không thay thế bài thử cài đặt mới + dựng DEMO hai tỷ lệ trên Windows độc lập. Chỉ công bố `v1.0.0 GA` sau khi chạy thật, QA kỹ thuật và duyệt người dùng cuối. Phiên bản hiện tại vẫn `v1.0.0-rc.2`.
