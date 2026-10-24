# Đợt 6 — Đóng gói và phát hành GitHub (30–32)

## Trạng thái và nguyên tắc
**Đã xây dựng hệ thống tự động đóng gói và phát hành bản RC**, không phải GA. Phiên bản `1.0.0-rc.2` duy trì nguyên văn. Không có tích hợp tự đăng TikTok/YouTube. Không được gắn nhãn `v1.0.0` hoặc ghi “GA” trước khi có báo cáo chạy Piper/Remotion/FFmpeg trên Windows độc lập, đánh giá chất lượng video/âm thanh và người dùng ký duyệt.

## 30 — Bộ nguồn ZIP chuyển máy, kiểm SHA-256
Gói phát hành GitHub có tên `AI-News-Video-Skill-1.0.0-rc.2-source.zip`.

Gồm thư mục gốc `AI-News-Video-Skill-1.0.0-rc.2/` chứa **toàn bộ** các tệp đã liệt kê trong `RELEASE_MANIFEST_SHA256.json`, bao gồm `.gitignore`, `SKILL.md`, `README.md`, references, scripts, tests, examples, Remotion JS/package-lock và requirements. Không có các dữ liệu phát sinh: `.git`, `.venv`, `node_modules`, model `.onnx`, media/bản tin/MP4/WAV, kết quả render, tokens, keys hoặc backup.

`scripts/package_source.py` kiểm manifest/trạng thái RC trước khi tạo, từ chối ghi đè, ký SHA-256 mọi tệp, đóng ZIP thứ tự và timestamp cố định. Sau khi tạo, chính công cụ kiểm ZIP lần nữa, giải nén sang thư mục **tạm** và chạy `release_manifest.verify`. Điều này kiểm tra tính toàn vẹn nhưng **không chứng minh ZIP được phát hành bởi người đáng tin nếu chưa xác thực checksum từ GitHub**.

Sau khi tải GitHub Release Candidate, kiểm SHA-256 bằng PowerShell:
```powershell
Get-FileHash -LiteralPath '.\AI-News-Video-Skill-1.0.0-rc.2-source.zip' -Algorithm SHA256
```
So sánh với `RC_ZIP_SHA256.txt` trên cùng Release và checksum độc lập từ nguồn tin cậy. Lưu ý: checksum cùng gói là chứng cứ toàn vẹn vận chuyển, không phải chữ ký nguồn độc lập.

Hoặc kiểm trực tiếp:
```powershell
python -B scripts/package_source.py verify --zip '<ĐƯỜNG_DẪN_ZIP>' --expect-manifest-sha256 '<64_HEX_MANIFEST_SHA256>'
```

Nếu muốn tự đóng ZIP bằng Python (không nén lại thủ công):
```powershell
$skill=(Resolve-Path .).Path
$zip=Join-Path (Split-Path -Parent $skill) 'AI-News-Video-Skill-1.0.0-rc.2-source.zip'
py -3.13 -B (Join-Path $skill 'scripts\package_source.py') build --source $skill --zip $zip
```
ZIP phải được tạo ở **ngoài** thư mục nguồn.

## 31 — Kiểm trên Windows độc lập
CI GitHub gồm hai tầng:
- **Linux source CI:** kiểm Python AST, unit test, 8 video FFmpeg DEMO mẫu theo 30/60/90/180 × 9:16/16:9, manifest và metadata phiên bản; tạo ZIP, giải nén/kiểm lại, tải lên Actions Artifact.
- **Windows GitHub-hosted:** tải ZIP đúng của job Linux, so SHA-256 manifest, giải nén sang thư mục mới, chạy `release_manifest.verify` và `bootstrap_windows.ps1 -CheckOnly`. Nếu runner thiếu Piper/FFmpeg/Chrome, trạng thái preflight chỉ ghi thiếu, **không bị coi là đạt render**.

**Nghiệm thu video và phần cứng thực tế chưa được thay thế** bởi việc giải nén ZIP. Tại máy Windows hoặc VM mới (có quyền cài phần mềm), trước hết:
1. Chạy `scripts/bootstrap_windows.ps1 -CheckOnly`, cung cấp đúng tệp model Piper và FFmpeg có bản quyền.
2. Khi phụ thuộc đã đầy đủ, chạy bootstrap tạo runtime **ngoài** Skill, `doctor.py` và unit test.
3. Chạy `scripts/stage5_windows_acceptance.py --out <THƯ_MỤC_VALIDATION_MỚI> --encoder auto --compare-cpu` dùng 4 DEMO ở 2 tỷ lệ; kiểm NVENC bằng thêm lần `--encoder nvenc` nếu phần cứng hỗ trợ và sử dụng thư mục **khác**, không ghi đè.
4. Kiểm `stage5-windows-summary.json`, các báo cáo QA, checksum MP4, WAV, phụ đề, crop và các chỉ số thời gian/CPU/GPU. Kiểm trực tiếp **hình ảnh, phụ đề, giọng đọc EN/VI, tỷ lệ**, bản quyền media và nội dung trước khi đăng.
5. Ghi báo cáo nhận xét và phê duyệt cuối từ **người dùng thật**, có ngày, định danh nguồn commit/manifest, tình trạng máy thử độc lập; không do Agent tự điền giả.

## 32 — Chỉ công bố GA sau khi có bằng chứng
`scripts/stage6_release_gate.py` đọc báo cáo nguồn và (nếu có) báo cáo Windows + phê duyệt người dùng; mặc định trả `RC_READY_WINDOWS_ACCEPTANCE_PENDING`. Nó chỉ *đánh giá điều kiện*, không gắn tag, không gọi GitHub API phát hành, không tự phê duyệt. Bản `v1.0.0-rc.2` có thể phát hành **prerelease** để kiểm thử và chuyển máy; không phải `v1.0.0 GA`.

Để công bố GA, tối thiểu phải có: nguồn ZIP phát hành được kiểm độc lập; mã nguồn chạy được trên máy Windows mới; 4 profile 30/60/90/180 giây có video native Remotion/Piper ở 9:16 và 16:9 đạt QA; đo được GPU/CPU thực tế; người dùng nghe/xem, kiểm nguồn/bản quyền và phê duyệt. Dự án chỉ đổi phiên bản toàn bộ metadata, tạo manifest và checksum mới **trong lần phát hành GA mới**, sau khi chứng cứ đầy đủ.

## Hạn chế kỹ thuật
- GitHub Runner Windows là máy độc lập để thử **giải nén và chạy preflight**; không chứng minh Remotion/Piper/GPU trên máy đích.
- Unit test kiểm thuật toán; video FFmpeg dùng màu và âm thử lặp, không phải bản tin.
- `stage6_release_gate.py` không có định danh số/PKI cho người ký; báo cáo người dùng có thể cần kiểm nguồn và lưu bằng chứng độc lập.
- Tuyệt đối không tự xóa job cũ, không tự ghi đè dữ liệu/video bàn giao và không tự đăng.
