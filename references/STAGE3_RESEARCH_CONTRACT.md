# Đợt 3 — Nghiên cứu tin tức 13–17 (v1.0.0-rc.2)

## Bản chất
Bộ Skill **tìm ứng viên RSS, không xác minh sự thật tự động**. Toàn bộ lời dẫn, ngày tháng, quốc gia xảy ra sự kiện, nguồn tin, độ độc lập của mỗi claim và giấy phép hình ảnh phải được AI Agent đọc/đối chiếu, người dùng chọn tin và duyệt chính xác draft SHA-256. Không tự đăng video.

## 13. Tìm tin theo thị trường, thể loại, thời gian
- Google News RSS dùng `country` làm **market/edition** và `category` làm chủ đề tìm kiếm, `--hours` lọc timestamp thực của bài (1..168 giờ); `when:Xd` của URL chỉ là truy vấn xấp xỉ, không đủ thay lọc thời gian.
- `WORLD` là edition toàn cầu tiếng Anh, không bảo đảm bao phủ mọi quốc gia. Không coi `gl=US` là bằng chứng sự kiện xảy ra tại Mỹ.
- Giới hạn từ khóa tùy chọn 120 ký tự; tối đa 16 RSS feeds/campaign. Mỗi feed phải có metadata hợp lệ, HTTPS công khai; giới hạn kích thước XML và retry có kiểm soát. Lỗi feed được ghi riêng trong `feed_results` (không thay bằng thông tin bịa).
- Feed phụ ở `examples/rss_sources.json` chỉ xuất hiện khi khớp country/category; bộ lọc không tự giả mạo phạm vi quốc gia.

## 14. Cụm sự kiện và trùng tiêu đề
- Gom những tiêu đề **gần giống** trong khung đăng tin 36 giờ, không gom các báo cáo có số liệu khác nhau (2.1 ≠ 2.2).
- Số lượng bài từ các feed là tín hiệu khám phá; không phải số lượng nguồn gốc độc lập. Tên cơ quan RSS chỉ là publisher hint; các bài cùng trích từ một thông cáo không phải hai chứng cứ.
- Các `possible_event_groups` trong `research_screening.json` là gợi ý cho người biên tập, không chứng minh hai bài thực sự cùng sự kiện. Một bài có ID trùng được tách định danh theo URL/thời gian, không tự hợp nhất vào tin đã xác minh.

## 15. Kiểm chứng nguồn, thời điểm và quốc gia xảy ra sự kiện
- `evidence.json` yêu cầu claim ledger, URL, `origin_id`, `publisher`, `ownership_group` nếu biết, `read_confirmed`, `syndicated_copy`, `published_at`, `retrieved_at`, `event_at`, `as_of` kèm timezone.
- Mỗi claim phải có tối thiểu hai xuất xứ có bằng chứng độc lập theo hồ sơ, đặc biệt không tính bản đăng lại từ cùng publisher/origin/ownership group.
- `workflow.py evidence` kiểm `event_country` theo `country` người dùng yêu cầu. Nếu chọn US mà nguồn xác định sự kiện ở VN, loại khỏi danh sách US; `WORLD` cho phép mọi quốc gia **khi đã xác minh**.
- Các bằng chứng có ngày xuất bản, đọc và sự kiện bất hợp lý bị đánh dấu; tin ngoài khung giờ lọc không đủ điều kiện. Phần mềm chỉ kiểm tra dấu vết cấu trúc, **không tự chứng thực** nội dung đã đọc thực sự đúng.

## 16. HTML reader và an toàn mạng
- `safe_http.py`: chỉ HTTPS trên 443, không credential, không hostname local và không IP private/reserved; giải DNS, kiểm **toàn bộ** địa chỉ, kết nối TCP tới IP đã thẩm định và xác minh TLS certificate/SNI theo hostname gốc.
- Không kế thừa proxy, từ chối downgrade/redirect khác origin, tối đa ba redirect, có timeout và byte budget; RSS XML không nhận DTD/ENTITY. Từ chối HTTP content encoding lạ.
- `source_reader.py` kiểm robots.txt và chính sách cho URL ban đầu lẫn URL cuối sau redirect (nếu cùng origin), giới hạn 1.5MB HTML, trả về text snapshot với trạng thái `TEXT_EXTRACTED_NOT_VERIFIED`.
- Nếu trang yêu cầu JavaScript, paywall, redirects giữa domain hoặc không xác định robots, chuyển sang **kiểm tra thủ công/qua browser được cấp phép**; không vượt paywall hay bí mật truy cập, không tự đánh dấu `read_confirmed=true`.

## 17. Chất lượng kịch bản và lời dẫn
- `editorial_quality.py` gắn cảnh báo giật gân, mốc thời gian tương đối không có ngày, kịch bản quá ngắn hoặc tốc độ nói ước lượng bất thường và headline trùng.
- Cảnh báo được đặt trong `draft.json` trước khi ký `script_sha256`. Không tự thay lời dẫn, không tạo claim, không tự quyết định title \"viral\".
- Người dùng xem và phê duyệt cả nội dung lẫn cảnh báo; đổi nội dung hoặc cảnh báo sau duyệt làm fingerprint không còn khớp.
- `news_editor.py` trình nguồn, chứng cứ và lời dẫn như một đề xuất biên tập chứ không phải chân lý.

## Giới hạn thử nghiệm
- `tests/test_stage3_research.py` sử dụng fixture tin **giả lập** và mock mạng. CI không chứng minh đang lấy đủ tin ngoài Internet tại một thời điểm cụ thể.
- Không chạy tải trang ngoài, không phân phối media có bản quyền, không render hay auto-upload trong đợt sửa GitHub này.
- Chưa được gọi v1.0.0 GA cho đến khi có QA và nghiệm thu Windows độc lập.
