# Đợt 6 — Giai đoạn 16–17: Vận hành job bền vững & nghiên cứu tin nhiều nguồn

**CHUYỂN MÁY (v1.0.0-rc.2):** Đọc `references/PORTABILITY_CONTRACT.md`, thiết lập `$skill`, `$runtime`, `$py` trên đúng máy. Đường dẫn ổ D:, ADMIN-PC-02, job và benchmark trong tài liệu giai đoạn chỉ là ví dụ/hồ sơ lịch sử; **không chạy nguyên văn trên máy mới**. Quy trình hiện tại theo `AGENT_RUNBOOK.md`.


Tài liệu vận hành cho **AI News Video Skill** trên Windows. Mã nguồn nằm trong thư mục Skill; job, model, log, video và checkpoints chỉ nằm trong **runtime ngoài Skill**. Không có API TikTok/YouTube; người dùng tự đăng video sau duyệt cuối.

## Giai đoạn 16 — 8 hạng mục
- **16.01 Checkpoint sự kiện**: mọi lần chuyển trạng thái được ghi vào events.jsonl và checkpoints.jsonl với SHA-256 tệp cốt lõi; append được fsync.
- **16.02 Atomic write**: JSON job tạo qua file tạm cùng thư mục, flush+fsync, tạo hardlink cuối bằng chế độ không ghi đè. Nếu file cuối đã tồn tại, báo lỗi. Hỗ trợ NTFS, không yêu cầu DB cloud.
- **16.03 Khóa job**: .stage4.lock có token ngẫu nhiên, PID, thời điểm tạo tiến trình; không cho hai lệnh thay đổi job đồng thời.
- **16.04 Kiểm tra khóa cũ**: phân biệt ACTIVE / STALE / UNKNOWN; không cướp khóa active hoặc không xác định.
- **16.05 Phục hồi khóa cũ có kiểm soát**: \`workflow.py recover-lock --job ...\` chỉ chạy khi chủ khóa thật sự đã biến mất hoặc PID tái sử dụng có thời gian bắt đầu khác; lưu log có hash khóa. Người điều phối phải kiểm PID trước khi chọn lệnh.
- **16.06 Resume checkpoint**: \`workflow.py resume --job ...\` đọc trạng thái, SHA-256, cổng người dùng và thư mục attempts. Nếu artifact đổi hoặc xuất hiện mà chưa checkpoint, báo \`NEEDS_MANUAL_RECOVERY\`; không tự bỏ qua.
- **16.07 Khôi phục render bị ngắt**: nếu folder attempt chứa đủ MP4, manifest chính xác, 30 FPS, approved.json bất biến, có thể \`workflow.py reconcile-render --job ...\`. Lệnh chạy QA độc lập rồi mới ghi render_result.json. Không bao giờ gọi render lại ở cùng attempt hoặc thay lời đọc. Folder chưa đầy đủ sẽ bị chặn và giữ nguyên để phân tích.
- **16.08 Kiểm thử**: tranh chấp lock bằng tiến trình thật, ghi mới không overwrite, partial JSONL, artifact sau checkpoint, approved.json bị sửa, stale lock, completed attempt và incomplete attempt.

### Ví dụ thao tác job
\`\`\`powershell
$py = Join-Path $runtime '.venv\Scripts\python.exe'
$j = Join-Path $runtime 'jobs\<JOB_ID>'

& $py -B "$skill\scripts\workflow.py" status --job $j
& $py -B "$skill\scripts\workflow.py" resume --job $j

# Chỉ khi status xác nhận khóa thật sự STALE và không có tiến trình công việc còn chạy:
& $py -B "$skill\scripts\workflow.py" recover-lock --job $j

# Chỉ khi video attempt đã render hoàn chỉnh, checksum approved đúng, không có render_result:
& $py -B "$skill\scripts\workflow.py" reconcile-render --job $j
\`\`\`

Không coi \`safe_to_mutate: false\` là lỗi luôn có thể sửa tự động: đây là hàng rào tránh ghi đè. Job tạo trước phiên bản này có \`LEGACY_NO_CHECKPOINTS\`; không được gán checkpoint giả cho quá khứ. Báo trạng thái này và yêu cầu kiểm tra thủ công.

## Giai đoạn 17 — 8 hạng mục
- **17.01 Mở rộng RSS có phân loại**: Google News khu vực được bổ sung feed công nghệ The Verge, Ars Technica, TechCrunch khi country=US/category=technology; chuyên mục chung NPR không lẫn vào technology. Feed phải có HTTPS và được kiểm tra riêng, không dùng RSS như dữ liệu chứng thực.
- **17.02 Sàng lọc sự kiện**: lấy tối đa 60 ứng viên RSS, chuẩn hóa title/link, phân nhóm tiêu đề gần giống với độ trùng cao và thời gian gần nhau. Ghi \`research_screening.json\`. Nhóm tiêu đề **chưa chứng minh cùng một sự kiện**.
- **17.03 Danh sách 5–12**: chọn tối đa 12 nhóm khác nhau, ước lượng recency cùng độ đa dạng publisher hint. Nếu chưa có 5 tin, nói đúng số lượng; không tạo tin mới. \`queue.json\` và \`queue.md\` vẫn ghi UNVERIFIED.
- **17.04 Nguồn độc lập thật sự**: \`research_enrichment.audited_sources\` kiểm claim-level, \`origin_id\`, publisher và \`ownership_group\`, URL chuẩn hóa và \`syndicated_copy\`. Hai URL cùng một đơn vị/nhà sở hữu **không phải hai nguồn độc lập**. Metadata là khai báo: AI biên tập phải đọc bài gốc và xác minh quan hệ xuất bản.
- **17.05 Claim ledger**: mọi claim đòi ít nhất hai nguồn độc lập đã đọc để được đưa qua cổng Stage17; \`core.check_bundle\` còn kiểm contradictions/confidence. Kết quả chỉ xác định **đủ hồ sơ để AI/người kiểm duyệt**, không xác nhận tự động sự thật.
- **17.06 Tin cũ và sai thời điểm**: so \`event_at\` với \`as_of\` và window 6/24/72/168 giờ; kiểm source publication/read timestamps, phát hiện nguồn ở tương lai hoặc trước thời điểm phát hành. Không sử dụng ngày đăng RSS như thời điểm xảy ra sự kiện.
- **17.07 Xếp hạng minh bạch**: \`editorial_priority_score\` của core dựa evidence, impact, recency, video fit, diversity; các thang impact/fit do AI biên tập đánh giá, không là xác suất chính xác hoặc cơ hội viral.
- **17.08 Báo cáo truy vết**: \`stage17_evidence_review.json/md\` có cờ mỗi story/claim; \`review.json/md\` chỉ đưa story qua nếu qua cả structural và provenance/freshness gate. Sau đó người dùng phải CHỌN ID, và DUYỆT đúng script hash trước khi render.

### Nguồn và bản quyền
- The Verge (RSS): \`https://www.theverge.com/rss/tech/index.xml\`
- Ars Technica: \`https://feeds.arstechnica.com/arstechnica/index\`
- TechCrunch: \`https://techcrunch.com/feed/\` — có điều kiện sử dụng RSS; chỉ dùng đường dẫn/headline để khám phá, ghi nguồn và liên kết bài gốc, không tái xuất bản feed content hay ảnh/video có bản quyền.

**Không cấp quyền dùng lại ảnh, bài báo, footage hoặc âm thanh chỉ vì có RSS.** Agent phải rà giấy phép media trước khi đưa vào video.

## Thử nghiệm và giới hạn nghiệm thu
\`\`\`powershell
$py = Join-Path $runtime '.venv\Scripts\python.exe'
& $py -B -m unittest discover -s (Join-Path $skill 'tests') -q
& $py -B "$skill\scripts\workflow.py" init --jobs-root "$runtime\new-tests" --job-id 'research-test-UNIQUE' --country US --category technology --hours 72 --aspect both
& $py -B "$skill\scripts\workflow.py" discover --job "$runtime\new-tests\research-test-UNIQUE"
\`\`\`

Chỉ chạy với ID và thư mục mới; job không được ghi đè. Bài khám phá RSS mới có thể lấy 5–12 ứng viên, nhưng tin chỉ thành verified/evidence-eligible sau khi Agent tự đọc nguồn và dựng hồ sơ kiểm chứng. Không tự chọn sự kiện hoặc tự duyệt script thay người dùng.

Giới hạn hiện tại: chưa kiểm thử thực tế mất điện giữa quá trình render, PID tái dùng xảy ra tự nhiên hoặc chạy cùng job qua nhiều máy chia sẻ filesystem. Kiểm thử đã giả lập crash/checkpoint và tranh chấp tiến trình tại local Windows. NTFS/os.link là điều kiện của atomic-write và cần xác minh ở hệ thống khác.
