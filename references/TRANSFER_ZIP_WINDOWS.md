# Hướng dẫn tự đóng gói ZIP và chuyển máy — v1.0.0-rc.2

**Trạng thái phát hành: RELEASE CANDIDATE, KHÔNG PHẢI 1.0.0 GA.** Người dùng quyết định tự làm Giai đoạn 4 (nghiệm thu Windows độc lập). Các bước dưới đây chỉ khóa/kiểm nguồn và hỗ trợ người dùng tự tạo ZIP, **không chứng minh video 9:16/16:9 hoạt động trên máy đích**.

## Bộ nguồn đem đi

Toàn bộ thư mục chứa `SKILL.md` là gốc Skill phát hành. Nén **chính thư mục Skill** thành file ZIP bằng thao tác thủ công. Giữ nguyên phân cấp `SKILL.md`, `README.md`, `references/`, `scripts/`, `examples/`, `tests/`, `remotion-template/`, `requirements*.txt`, `.gitignore` và `RELEASE_MANIFEST_SHA256.json`.

**Không được đem theo:** `.venv/`, `node_modules/`, model `.onnx`/`.onnx.json`, FFmpeg, `output/`, `jobs/`, `logs/`, `deliveries/`, MP4, WAV, secrets, credentials, backup, bộ nhớ làm việc Agent, dữ liệu từng bài tin đã duyệt, file thử nghiệm phát sinh. Những thứ đó phải nằm trong runtime riêng, có giấy phép và xử lý chuyển giao dữ liệu riêng khi cần.

**Không tự xóa một tệp chỉ vì tên có "stage"/"test"/"demo".** `tests/` và `examples/` là thành phần mã nguồn quan trọng để cài và kiểm tra Skill; dữ liệu demo trong `examples/` không phải tin thật và không được đăng.

## 1. Kiểm tra tính toàn vẹn TRƯỚC khi bạn tạo ZIP

Mở PowerShell trong thư mục Skill, dùng một Python 3.13 bất kỳ để chạy bộ kiểm tra **chỉ-đọc** (không cần venv runtime):

```powershell
$skill = (Resolve-Path .).Path
if (-not (Test-Path (Join-Path $skill 'SKILL.md'))) { throw 'Wrong Skill root' }
py -3.13 -B (Join-Path $skill 'scripts\release_manifest.py') verify --source $skill
Get-FileHash -LiteralPath (Join-Path $skill 'RELEASE_MANIFEST_SHA256.json') -Algorithm SHA256
```

Chỉ tiếp tục khi kết quả có `status=RELEASE_MANIFEST_PASS` và đúng `release_status=RELEASE_CANDIDATE_NOT_GA`. Nếu lỗi, file ZIP cần được xem lại; không tự sửa manifest hoặc bỏ qua sự khác biệt. Công cụ phát hiện tệp thiếu, mới thêm, sửa khác hash, file nhị phân/rác, cấu trúc không hợp lệ và đối chiếu mã nguồn.

`content_set_sha256` là mã hash tập hợp **các tệp nguồn ngoài manifest**. Vì một file không thể tự chứa hash bất biến của chính nó, `RELEASE_MANIFEST_SHA256.json` được loại khỏi danh sách hash ở bên trong manifest. Nếu cần xác thực rằng manifest chưa bị thay đổi, hãy **lưu riêng SHA-256 của manifest ở một nơi tin cậy**, không phụ thuộc ZIP đó.

## 2. Bạn tự tạo ZIP, không để ZIP trong thư mục nguồn

Sau khi PASS, dùng File Explorer hoặc công cụ nén của bạn tạo ZIP **ở một nơi khác**, bao gồm nguyên thư mục Skill và mọi tệp ẩn cần thiết như `.gitignore`. Không đổi tên file, không loại bớt test/reference và không thêm file runtime.

Sau khi tạo ZIP, bạn có thể lưu SHA-256 của **chính file ZIP** bằng `Get-FileHash` trên máy của bạn. Đây là checksum vận chuyển, khác với `content_set_sha256` của nguồn. Không có ZIP nào được tạo sẵn bởi bước khóa bộ nguồn.

## 3. Kiểm tra trên máy Windows đích

- Giải nén ZIP sang một thư mục **mới**, không đè lên thư mục nguồn/working data khác.
- Mở PowerShell **ngay trong thư mục có SKILL.md** và chạy lại `release_manifest.py verify` như bước 1.
- Kiểm tra SHA-256 của `RELEASE_MANIFEST_SHA256.json` khớp bản đã lưu ngoài ZIP, nếu bạn dùng đối chiếu ngoài gói.
- Sau đó đọc `references/PORTABILITY_CONTRACT.md`, `references/WINDOWS_BOOTSTRAP.md` và `references/AGENT_ORCHESTRATION.md`. Chỉ chạy `bootstrap_windows.ps1 -CheckOnly` trước khi yêu cầu cài runtime. Các file model Piper/FFmpeg phải do người dùng cung cấp, không có trong ZIP và không tự tải.
- Bạn **tự nghiệm thu Giai đoạn 4**: cài đặt đầy đủ trên Windows mới, chạy unit/integration, dựng DEMO có watermark ở cả 9:16 và 16:9, xem/nghe, kiểm tra codec/H.264/AAC/30fps, SRT, nguồn/giấy phép, độ dài và SHA-256. Chưa có chứng cứ nghiệm thu này, **không đổi nhãn phiên bản thành GA**.

## 4. Khi cần sửa mã nguồn sau thời điểm khóa

Mọi thay đổi mã nguồn sau thời điểm tạo `RELEASE_MANIFEST_SHA256.json` sẽ làm kiểm tra FAIL. Đây là chức năng bảo vệ. Nếu muốn tạo **một đợt phát hành mới**, sao lưu nguyên bản cũ ra nơi khác, chỉnh sửa trên bộ nguồn đang phát triển, nghiệm thu lại và chủ động tạo manifest phát hành mới. `release_manifest.py build` chỉ tạo manifest khi nó **chưa tồn tại**, không tự ghi đè hash của bản phát hành đã khóa.

## 5. Giới hạn tuyên bố

`SOURCE_AUDIT_PASS` và `RELEASE_MANIFEST_PASS` kiểm chứng **tính toàn vẹn/bố cục của bộ nguồn**, không phải chứng nhận an toàn bảo mật toàn diện, bản quyền, sự thật của tin, hiệu năng/GPU, khả năng đăng video, hay nghiệm thu máy Windows độc lập. Người dùng vẫn chọn tin, phê duyệt kịch bản SHA-256, xem video cuối và tự đăng.
