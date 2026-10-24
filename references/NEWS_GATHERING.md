# Nguồn tin, kiểm chứng và tính thời sự — Stage 04–07

**CHUYỂN MÁY (v1.0.0-rc.2):** Đọc `references/PORTABILITY_CONTRACT.md`, thiết lập `$skill`, `$runtime`, `$py` trên đúng máy. Đường dẫn ổ D:, ADMIN-PC-02, job và benchmark trong tài liệu giai đoạn chỉ là ví dụ/hồ sơ lịch sử; **không chạy nguyên văn trên máy mới**. Quy trình hiện tại theo `AGENT_RUNBOOK.md`.


## Kiến trúc nguồn
1. `news_rss.py` tìm ứng viên từ Google News và các feed HTTPS tùy chọn; kết quả luôn UNVERIFIED_RSS_CANDIDATE.
2. `news_editor.py queue` gom tiêu đề gần giống, xếp theo **độ mới của ngày đăng bài**; không tự chấm uy tín hay tác động dựa trên tiêu đề.
3. ChatGPT/web và `source_reader.py` hỗ trợ mở bài gốc, trích chứng cứ sơ bộ, xác nhận nguồn và thông tin.
4. `editorial_core.py` kiểm tra sổ nguồn/claim, xuất báo cáo lỗi/thiếu bằng chứng; không thể quyết định tuyệt đối sự thật.
5. Tổng biên tập lập danh sách tin đã kiểm chứng bằng các nguồn đọc thực tế cho người dùng lựa chọn.

## Tính độc lập của nguồn
- Hai domain khác nhau **không đủ** chứng minh độc lập: cần hai tổ chức xuất bản, xuất xứ nội dung (`origin_id`) và xem liệu cùng trích một thông cáo/Reuters/AP hay không.
- Trường `syndicated_copy` phải true nếu nguồn chỉ đăng lại cùng một nội dung gốc: không cộng vào độ độc lập.
- `read_confirmed` chỉ true nếu agent đọc toàn văn trực tiếp; `evidence_note` ghi ngắn nội dung chứng minh, không sao chép toàn bài.
- Nếu `confidence=high`, mỗi claim cần 2 nguồn đã đọc, khác xuất xứ và khác tổ chức; toàn tin cần 2 tổ chức ở các domain khác nhau.
- Nguồn sơ cấp hữu ích: chính phủ công bố dữ liệu, tổ chức nghiên cứu phát hành nghiên cứu, tài liệu tòa án/đơn vị trực tiếp liên quan. Đừng tự động coi nguồn chính thức là không thể sai.
- Các tranh cãi chính trị phải có bối cảnh, phân biệt tuyên bố của các bên và dữ kiện xác nhận; không suy diễn về động cơ.
- Các nguồn không mở được hoặc yêu cầu paywall: ghi trạng thái `read_confirmed=false`, tìm nguồn thay thế hoặc để chờ.

## Ghi thời gian
- `event_at`: thời điểm xảy ra sự kiện; `published_at`: thời điểm đăng bài; `retrieved_at`: thời điểm đọc/chụp nội dung; `as_of`: thời điểm tổng hợp. Tất cả yêu cầu timezone.
- `news_rss.py --hours` lọc **ngày đăng RSS**, không lọc event_at; AI phải lọc sự kiện thực theo thời điểm người dùng cần.
- Đối với tin nóng, ghi rõ 'tính đến [thời gian + múi giờ]' trong lời dẫn.
- Trước khi duyệt cuối, kiểm tra thông tin mới thay đổi hoặc sai lệch giữa nguồn.

## Lọc địa lý
- `--country US` nghĩa là edition RSS theo thị trường Mỹ. Một bài trên Google News US có thể nói về sự kiện ở nước khác.
- Agent phải ghi `event_country` theo chính thông tin đọc được, không suy ra từ edition RSS.
- WORLD là edition phát hiện tin tiếng Anh của Google News cộng nguồn toàn cầu, không phải tập đầy đủ các quốc gia.
- Nguồn ngoài Google được định cấu hình theo country/category trong `examples/rss_sources.json`. Feed `country=WORLD` chỉ tham gia khi người dùng chọn WORLD; feed `country=US` chỉ tham gia khi chọn US; `country=ALL` nếu cố ý dùng mọi thị trường. Sau đó AI vẫn bắt buộc kiểm tra quốc gia xảy ra sự kiện từ bài gốc.

## Điểm ưu tiên tin
Sau khi qua evidence gate, điểm ưu tiên biên tập được tính theo:
- 30% độ dày chứng cứ đã khai và tự kiểm tra cấu trúc nguồn;
- 25% tác động (**editorial estimate 0..5**, không phải số liệu thực nghiệm);
- 20% tính gần đây theo event_at và as_of;
- 15% phù hợp thời lượng video (**editorial estimate 0..5**);
- 10% đa dạng chuyên mục.

Điểm chỉ để tham khảo lựa chọn nội dung; **không phải xác suất tin đúng, lượt xem dự báo hoặc cam kết viral**. Nếu thiếu impact/video_fit, điểm thành phần mặc định bằng 0, không được phát minh số liệu. Có thể sửa xếp hạng bằng nhận định biên tập công khai với người dùng.

## Đầu vào & lệnh vận hành
```powershell
Set-Location $skill
$outDir = Join-Path $runtime 'output'
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
& $py -B (Join-Path $skill "scripts\news_rss.py") --country US --category technology --hours 24 --limit 20 --out (Join-Path $outDir 'us-technology-unique.json')
& $py -B (Join-Path $skill "scripts\news_editor.py") queue --candidates (Join-Path $outDir 'us-technology-unique.json') --out (Join-Path $outDir 'queue-unique.json') --markdown (Join-Path $outDir 'queue-unique.md') --limit 12
& $py -B (Join-Path $skill "scripts\news_editor.py") check --evidence (Join-Path $outDir 'evidence-unique.json') --report (Join-Path $outDir 'review-unique.json') --markdown (Join-Path $outDir 'review-unique.md')
```

## Lưu ý giới hạn
- Trích HTML bởi source_reader có thể mất dữ liệu tạo bằng JavaScript, cập nhật bài và chữ trong ảnh; tác nhân phải mở trực tiếp trang chính thức để đối chiếu.
- Các chính sách robots/paywall và quyền dùng lại media phải được tôn trọng.
- Tin chỉ có RSS, tin chưa đủ hai nguồn độc lập, claim chưa có chứng cứ: không xuất bản như dữ kiện chắc chắn.
- Không tạo media nhạy cảm mô phỏng sự kiện thật để đánh lừa khán giả.

## Nâng cấp Đợt 3 — Phạm vi và kết quả nguồn (v1.0.0-rc.2)
Đọc `references/STAGE3_RESEARCH_CONTRACT.md`: RSS market không phải event_country, lọc 1..168 giờ bằng published_at, so sánh hai tin có số liệu khác nhau, giới hạn HTTP/robots và kiểm đủ nguồn độc lập theo từng claim. `safe_http.py` chỉ tải HTTPS public origin, không vượt paywall, robots hay chuyển hướng qua domain khác. `editorial_quality.py` ghi các điểm cần biên tập viên xem, tuyệt đối không tự xác nhận sự thật hoặc tự đăng video.
