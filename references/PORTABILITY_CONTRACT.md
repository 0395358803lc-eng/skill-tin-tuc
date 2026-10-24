# Hợp đồng chuyển máy AI News Video Skill v1.0.0-rc.2

Đây là mã nguồn dành cho AI Agent, không kèm model Piper, node_modules, Python venv, media hoặc tài khoản. Không có tích hợp tự đăng TikTok/YouTube.

## 1. Khám phá thư mục trên máy Windows đích

AI Agent phải xác định thư mục chứa `SKILL.md` thực tế từ đường dẫn đã được người dùng tích hợp. Không mặc định dùng ổ D:, ADMIN-PC-02 hay thư mục runtime lịch sử. Mở PowerShell tại thư mục Skill rồi khởi tạo:

```powershell
$skill = (Resolve-Path .).Path
if (-not (Test-Path (Join-Path $skill 'SKILL.md'))) { throw 'Not a Skill root' }
$runtime = if ($env:NEWS_SKILL_RUNTIME) { $env:NEWS_SKILL_RUNTIME } else { "$skill-runtime" }
if ([IO.Path]::GetFullPath($runtime).StartsWith(([IO.Path]::GetFullPath($skill).TrimEnd('\')+'\'), [StringComparison]::OrdinalIgnoreCase)) { throw 'Runtime must be outside Skill' }
$py = Join-Path $runtime '.venv\Scripts\python.exe'
$env:NEWS_SKILL_RUNTIME = $runtime
```

Trước khi cài trên máy mới, đọc `references/WINDOWS_BOOTSTRAP.md` và chạy `bootstrap_windows.ps1 -CheckOnly` để kiểm tra không thay đổi máy. Nếu `$py` chưa tồn tại, chưa được chạy job. Phải thực hiện `references/INSTALL_WINDOWS.md` và `scripts/bootstrap_windows.ps1` với runtime trống, nguồn FFmpeg và Piper hợp lệ do người dùng cung cấp. Không tự tải model, ghi đè dữ liệu hoặc cài đặt trái phép.

Khi đã cài, kiểm tra:

```powershell
& $py -B (Join-Path $skill 'scripts\doctor.py') --runtime $runtime
& $py -B -m unittest discover -s (Join-Path $skill 'tests') -q
```

Sau đó đọc `references/AGENT_ORCHESTRATION.md` để tiếp nhận yêu cầu và tách job nhiều phiên, rồi dùng `references/AGENT_RUNBOOK.md`. Mỗi job phải lấy chính xác `job_directory` từ lệnh `workflow.py init`, không tự đoán ID và không để hai Agent ghi vào cùng job.

## 2. Phân biệt source và dữ liệu phiên

- Mọi đường dẫn `D:\skill-tintuc`, `D:\skill-tintuc-runtime`, `D:\jobs`, ADMIN-PC-02 trong tài liệu Stage 4–21 là **ví dụ hoặc chứng cứ lịch sử**. Không chạy nguyên văn trên máy mới, cần đổi sang `$skill`, `$runtime` và đường dẫn job thực.
- Video, approved.json, backup, benchmark, logs, mô hình giọng và dữ liệu nghiệm thu lịch sử không có trong gói ZIP nguồn.
- `scripts/stage21_acceptance.py` phụ thuộc chứng cứ nghiệm thu cũ: không sử dụng như kiểm thử portable cho máy mới. Kiểm thử phù hợp: `release_audit.py`, `doctor.py`, unittest, và dựng DEMO có watermark sau khi đã cài đủ runtime.
- Các tài liệu Stage 15–20 chứa tên phiên bản lịch sử để mô tả tính năng; phiên bản gói hiện tại là `v1.0.0-rc.2`.
- Trước khi tự ZIP và sau khi giải nén trên máy mới, bắt buộc kiểm tra `RELEASE_MANIFEST_SHA256.json` với `scripts/release_manifest.py verify`; hướng dẫn ở `references/TRANSFER_ZIP_WINDOWS.md`. Kiểm SHA-256 không thay thế bài nghiệm thu video/Windows độc lập do người dùng tự làm.

## 3. Cổng an toàn không thể bỏ qua

- RSS chỉ là ứng viên chưa kiểm chứng; mỗi claim phải đối chiếu nguồn thực sự đã đọc và độc lập.
- Người dùng tự chọn tin và duyệt toàn văn kịch bản + SHA-256; Agent không được giả xác nhận hoặc sửa kịch bản/media/style sau phê duyệt.
- Video tin thật phải FAIL QA nếu lệch thời lượng mục tiêu quá ±5%; QA kỹ thuật không bảo đảm tin đúng, có bản quyền, hoặc giọng/crop hoàn hảo.
- Người dùng xem/nghe, kiểm nguồn và quyền media rồi **tự đăng**. Không công bố GA nếu chưa có kiểm thử trên Windows sạch độc lập và nghiệm thu biên tập cuối.
