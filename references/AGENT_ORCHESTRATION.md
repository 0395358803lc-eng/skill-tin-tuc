# Quy trình điều phối AI Agent — Giai đoạn 3 / v1.0.0-rc.2

Đây là hướng dẫn hiện hành khi người dùng gửi yêu cầu **bằng ngôn ngữ tự nhiên**. AI Agent thực hiện phân tích ngữ nghĩa và đọc nguồn; các script chỉ giúp phát hiện gợi ý, kiểm tra tính hợp lệ và điều phối workflow. **Không có script nào tự biết sự thật hay được phép chọn/duyệt thay người dùng.**

## 1. Tiếp nhận: không tự chạy job từ một câu lệnh mơ hồ

Đọc `SKILL.md`, `PORTABILITY_CONTRACT.md`, `WINDOWS_BOOTSTRAP.md` và `AGENT_RUNBOOK.md`. Xác nhận đúng Windows host và root source. Chuẩn bị `$skill`, `$runtime`, `$py` theo PORTABILITY_CONTRACT.

Gọi script **chỉ-đọc**, truyền yêu cầu vào `--text` hoặc đọc một file do người dùng cung cấp. Nếu runtime venv chưa có, dùng `py -3.13 -B` thay cho `$py -B` để chạy `agent_bridge.py` trực tiếp; công cụ này chỉ dùng thư viện Python chuẩn:

```powershell
& $py -B (Join-Path $skill 'scripts\agent_bridge.py') intake --text 'Tạo bản tin công nghệ Việt Nam 60 giây, 9:16, tiếng Việt'
```

Đầu ra JSON `INTAKE_ADVISORY_ONLY` có `parameters`, `defaults_applied`, `ambiguities_and_missing` và `workflow_init_arguments`. Không có job nào được tạo; câu chữ đầu vào cũng không lưu trong Skill.

- Đây là bộ nhận diện cụm từ có chủ đích **bảo thủ**, không phải LLM; AI Agent phải hiểu ngữ cảnh, kiểm tra quốc gia xảy ra sự kiện so với edition RSS và chỉ chấp nhận tham số khi không còn mơ hồ.
- Quốc gia là thông tin bắt buộc; nếu thiếu, hỏi quốc gia/khu vực cần lấy tin. Nếu thiếu chuyên mục, mặc định `general` và thông báo. Mặc định kỹ thuật: `hours=24`, `language=vi-VN`, `target_seconds=60`, `aspect_ratio=both`, `tone=neutral`. Những mặc định đó phải được trình bày rõ trước khi khởi tạo.
- Các giá trị được workflow hỗ trợ: `hours` 6/24/72/168; `seconds` 30/60/90/180; `language` vi-VN/en-US/en-GB; `aspect` 9:16/16:9/both. Ví dụ 120 giây hoặc hai quốc gia chưa phân giải: `ready_for_review=false`. Không tự ép giá trị gần đúng hoặc bỏ qua xung đột.
- Không suy luận Mỹ chỉ vì người dùng nói tiếng Anh hoặc xài từ `my`; không suy luận nội dung đã qua kiểm chứng chỉ vì người dùng yêu cầu tin "mới nhất".
- Agent không được tự nhận một gợi ý `ready_for_review=true` là người dùng đã phê duyệt kịch bản; các cổng P3/P5/P7 vẫn riêng biệt.

Sau khi giải quyết tham số và đảm bảo host đã được cấp quyền, gọi đúng `workflow.py init` cho job mới; không tạo job trùng khi người dùng yêu cầu tiếp tục một job cũ.

## 2. Nhiều tab ChatGPT: khóa phạm vi bằng job_directory

Chỉ định `$jobsRoot` chính xác cho host/runtime được chọn:

```powershell
$jobsRoot = Join-Path $runtime 'jobs'
& $py -B (Join-Path $skill 'scripts\agent_bridge.py') list --jobs-root $jobsRoot
```

Danh sách đọc tối đa 100 job, chỉ quét **thư mục job cấp một** của `$jobsRoot`, không tìm video ở thư mục khác. Thông tin job hợp lệ gồm `job_id`, `job_directory`, `stage` và `blocked`. Danh sách chỉ để lựa chọn, **không suy đoán job gần nhất thuộc phiên chat hiện tại**.

Khi tạo job, Agent lưu lại **đường dẫn chính xác** trả về từ `workflow.py init` trong ngữ cảnh phiên chat. Khi tiếp tục, nếu không có đường dẫn cũ và có nhiều job thì hỏi người dùng xác định job; không tự chọn job từ `list`, không dựa vào tab khác hoặc thời gian tạo.

```powershell
$job = '<JOB_DIRECTORY_DO_WORKFLOW_INIT_TRA_VE>'
& $py -B (Join-Path $skill 'scripts\agent_bridge.py') inspect --jobs-root $jobsRoot --job $job
& $py -B (Join-Path $skill 'scripts\workflow.py') resume --job $job
```

`inspect` chỉ chấp nhận một thư mục job nằm **trực tiếp** trong jobs root được chỉ định và cần `job.json` thật. Không tự đọc hay ghi ở đường dẫn ngoài scope, hoặc theo liên kết tượng trưng.

## 3. Bộ điều phối P0–P7

| Stage từ workflow | Công việc Agent | Cổng bắt buộc |
|---|---|---|
| `CREATED` | P1 — `workflow.py discover` | RSS chỉ là ứng viên |
| `AWAITING_EVIDENCE` | P2 — đọc bài gốc, biên tập EVIDENCE.json, `workflow.py evidence` | Nguồn có thể kiểm tra độc lập, nguồn đã đọc |
| `NEEDS_EVIDENCE` | Tìm nguồn bổ sung; dùng job nghiên cứu mới khi cần | Không bịa nguồn hoặc vượt gate |
| `AWAITING_SELECTION` | P3 — trình các tin có ID/nguồn/ngày, đợi chọn | **Thông điệp chọn tin thật** |
| `AWAITING_SCRIPT` | P4 — viết SCRIPT.json từ tin đã chọn, đo giọng/thời lượng rồi `draft` | Nội dung/nguồn/media quyền hợp lệ |
| `AWAITING_APPROVAL` | P5 — trình nguyên văn draft + SHA-256, đợi duyệt | **Phê duyệt exact hash riêng** |
| `APPROVED` | P6 — doctor, kiểm media, `workflow.py render --encoder auto` | approved.json bất biến |
| `RENDERED` | P7 — `workflow.py qa` | Video/SRT/giọng/codec/thời lượng |
| `TECHNICAL_QA_FAILED` | Kiểm lỗi, chỉ dùng thao tác khôi phục được cho phép | Không sửa kịch bản hoặc nới tiêu chí |
| `TECHNICAL_QA_PASSED` | P7 — `workflow.py handoff` | QA không thay thế phê duyệt đăng |
| `AWAITING_HUMAN_FINAL_REVIEW` | Bàn giao video, SRT, QA, rights, nguồn | **Người dùng xem/nghe rồi tự đăng** |

Gọi `agent_bridge.py inspect` để nhận `phase`, `suggested_workflow_command`, `requires_human_action`, `blocked` và `recovery`. Gợi ý không bao giờ tự gọi workflow hay thay thế việc đọc tin/phê duyệt.

## 4. Khôi phục gián đoạn và khóa an toàn

Trước **mọi thao tác ghi** phải kiểm `workflow.py resume`/`agent_bridge.py inspect`:

1. Nếu `safe_to_mutate=false`, **DỪNG**. Đọc `recovery.checkpoint.issues`, `recovery.lock` và các attempt; không tự render lại, không xóa lock hoặc sửa artifact.
2. Nếu `ACTIVE`/`UNKNOWN`, không cướp khóa. Chỉ cân nhắc `recover-lock` khi trạng thái `STALE` đã có xác minh từ hệ thống. Không dừng tiến trình tab khác.
3. Nếu checkpoint `NEEDS_MANUAL_RECOVERY`, không lấy stage bề ngoài làm bằng chứng đã duyệt. Trường hợp attempt render hoàn tất nhưng thiếu render_result, `reconcile-render` là đường khôi phục riêng, chỉ sau khi kiểm SHA-256 và chạy QA độc lập thực tế.
4. Nếu approved.json bị sửa, phải ngừng và xin phê duyệt lại trong một job/bản nháp mới; không tự sửa hash hoặc chèn confirmation.
5. Khi tiếp tục, không tạo job mới thay cho job đang tạm dừng trừ khi cần sửa immutable artifact/chuyển khung tin mới và đã nói rõ với người dùng.

## 5. Bàn giao và giới hạn

Đầu ra `handoff.json` và video chỉ là **AWAITING_HUMAN_FINAL_REVIEW**. Agent không tự tải lên nền tảng, không xác nhận quyền sử dụng thay chủ bản quyền và không coi bài test kỹ thuật là chứng nhận GA. Tất cả file runtime, job và báo cáo phải nằm ngoài thư mục source Skill. File này phục vụ tích hợp vào AI Agent từ ZIP; không chứa ký ức phiên chat hay đường dẫn của máy phát triển.
