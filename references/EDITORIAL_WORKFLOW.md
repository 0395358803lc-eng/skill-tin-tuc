# Quy trình tương tác với người dùng — cập nhật cho v0.5.0 (Đợt 2–4)

**CHUYỂN MÁY (v1.0.0-rc.2):** Đọc `references/PORTABILITY_CONTRACT.md`, thiết lập `$skill`, `$runtime`, `$py` trên đúng máy. Đường dẫn ổ D:, ADMIN-PC-02, job và benchmark trong tài liệu giai đoạn chỉ là ví dụ/hồ sơ lịch sử; **không chạy nguyên văn trên máy mới**. Quy trình hiện tại theo `AGENT_RUNBOOK.md`.


## 0. Phạm vi
- ChatGPT là tổng biên tập và người điều phối, chạy công cụ qua Remote Desktop Commander nếu có máy kết nối.
- Chỉ dùng dữ liệu tin đã tìm bằng web/RSS và được kiểm chứng qua nguồn gốc; không bịa nguồn, trích dẫn, ảnh hoặc ngày giờ.
- Không có chức năng đăng TikTok/YouTube. Người dùng tự đăng video.
- Cho người dùng chọn: 9:16 / 16:9 / cả hai. Renderer v0.4 hỗ trợ cả hai tỷ lệ bằng composition Remotion riêng; không đổi cấu hình sau phê duyệt.

## 1. Thu thập yêu cầu tự nhiên
Hiểu các thông số nếu đã có; chỉ hỏi phần thiếu quan trọng:
- Quốc gia **sự kiện** (US, VN, WORLD hoặc nơi khác) và nếu cần phân biệt quốc gia **nguồn báo**.
- Nhóm tin: general / politics / economy / technology / science / entertainment / sports / environment / health.
- Khung thời gian: 6h, 24h, 72h hoặc 168h.
- Ngôn ngữ lời dẫn vi-VN / en-US (từng ngôn ngữ cần voice model tương ứng).
- Thời lượng 30, 60, 90, 180 giây; tỷ lệ 9:16 / 16:9 / cả hai.
- Phong cách dẫn: nhanh, trung tính, chuyên sâu. Không được đưa ý kiến riêng thành sự thật.

Nếu người dùng chỉ nói 'Tin công nghệ Mỹ trong 24 giờ, tiếng Việt, 1 phút', hiểu đủ, tìm tin trước, không hỏi lại.
Nếu chưa cung cấp: mặc định US, general, 24h, vi-VN, 60s, 9:16, trung tính — báo cho người dùng biết khi mặc định có thể ảnh hưởng sản phẩm.

## 2. Giai đoạn P1: tìm ứng viên — không được gọi là tin đã xác thực
- Dùng web tìm kiếm mới, hãng tin trực tiếp và `scripts/news_rss.py`.
- Dùng lệnh trên máy: 
  `& $py -B (Join-Path $skill "scripts\news_rss.py") --country US --category technology --hours 24 --limit 20 --out (Join-Path $runtime 'output\research-unique.json')`
- Thêm `--feeds examples/rss_sources.json` cho các nguồn được cấu hình, đọc `feed_results` để biết nguồn lỗi.
- Lọc sự kiện đúng địa điểm người dùng muốn, không cho rằng edition RSS = nơi sự kiện xảy ra.
- Gom các bài có tiêu đề giống nhau và xử lý trùng sự kiện còn lại bằng tổng biên tập. Thuật toán chỉ nhóm tiêu đề tương tự.
- Chạy `python -B scripts/news_editor.py queue --candidates CANDIDATES.json --out QUEUE.json --markdown QUEUE.md --limit 12`.
- Trạng thái đầu ra: UNVERIFIED_EDITORIAL_QUEUE.

## 3. Giai đoạn P2: đọc nguyên bản và tạo hồ sơ bằng chứng
- Không dựa vào RSS snippet, kết quả tìm kiếm hoặc nguồn trung gian để tự khẳng định.
- Mở trực tiếp trang báo gốc bằng chức năng web của AI; nếu cần dùng `scripts/source_reader.py --url HTTPS_URL --out SOURCE.json` để trích xuất sơ bộ trang HTML hợp lệ.
- Tôn trọng robots.txt, không tự vượt paywall, không lấy trộm media. Reader chỉ cung cấp TEXT_EXTRACTED_NOT_VERIFIED, không phải xác minh tự động.
- So sánh tối thiểu 2 nguồn thực sự độc lập: tổ chức xuất bản, nguồn sơ cấp, xuất xứ phát ngôn, cùng nguồn tin gốc và các bản sao.
- Ghi event_at, published_at, retrieved_at (ISO-8601 có múi giờ); ghi đủ quốc gia nơi xảy ra sự kiện.
- Tạo EVIDENCE.json theo `references/EVIDENCE_SCHEMA.md`, kèm từng claim và source_ids hỗ trợ.
- Đánh dấu `read_confirmed=true` chỉ khi AI/người kiểm duyệt thực sự đọc nội dung bài.
- Không khai `confidence=high` nếu claim chưa có hai nguồn đã đọc có xuất xứ độc lập.
- Đối với chính trị, sức khỏe, tài chính, xung đột, bầu cử, ưu tiên nguồn sơ cấp và mô tả các bất đồng nguồn một cách cân bằng.
- `python -B scripts/news_editor.py check --evidence EVIDENCE.json --report EVIDENCE_REPORT.json --markdown EVIDENCE_REVIEW.md`.
- Chỉ các tin eligible_for_human_editorial_review=true mới được đề xuất như hồ sơ đủ bằng chứng để người dùng cân nhắc. Không đồng nhất 'đủ hồ sơ' với sự thật được phần mềm chứng nhận.

## 4. Giai đoạn P3-A: chọn sự kiện trong ChatGPT
- Trình 5–12 tin (hoặc ít hơn khi thiếu chứng cứ), mỗi tin gồm ID, headline, 1–2 câu tóm tắt, event_at và published_at, quốc gia, confidence do AI đánh giá, 2 nguồn độc lập có URL, điểm phù hợp video và lưu ý chưa chắc chắn.
- Đối với tin đang có mâu thuẫn/thiếu chứng cứ, đặt riêng vào danh sách chờ; không thúc đẩy xuất bản.
- Cho người dùng chọn nhiều ID, bỏ/chuyển thứ tự, yêu cầu tìm thêm, thay chủ đề hoặc chỉnh phong cách.
- Sau khi người dùng thực sự chỉ định ID, agent mới gọi `news_editor.py select` với --user-message là nội dung quyết định của người dùng và --confirmed-at theo múi giờ.
- Phải ghi trạng thái SELECTED_AWAITING_SCRIPT_APPROVAL. Việc chọn tin không phải là duyệt lời dẫn hay duyệt nguồn media.

## 5. Giai đoạn P3-B: biên tập kịch bản và duyệt lần hai
- Agent viết mới headline, summary, narration bằng ngôn ngữ đã chọn. Không sao chép quá mức nguồn, không bịa số liệu hoặc phát ngôn.
- Bố cục gợi ý: hook chính xác 2–5s, thân bài câu ngắn (ai/chuyện gì/ở đâu/khi nào/vì sao quan trọng), kết trung tính.
- Mọi tin trong script phải có `claim_ids` ánh xạ đến hồ sơ bằng chứng; số và tên phải có căn cứ cụ thể.
- Tạo file script JSON theo `examples/script_demo.json` **nhưng thay toàn bộ dữ liệu DEMO bằng nội dung thật được kiểm chứng**.
- Chạy `python -B scripts/news_editor.py draft --evidence EVIDENCE.json --selection SELECTION.json --scripts SCRIPT.json --out DRAFT.json`.
- Trình chính xác nội dung DRAFT cho người dùng duyệt kịch bản và kiểm tra quyền media. Khi sửa DRAFT phải lấy lại hash và xin duyệt lại.
- Hash theo lệnh `news_editor.py hash --draft DRAFT.json`. Chỉ khi người dùng chấp thuận rõ ràng thì agent mới tạo APPROVAL.json gồm approved_story_ids theo đúng thứ tự, user_confirmation, confirmed_at, script_sha256.
- Lệnh `news_editor.py approve --draft DRAFT.json --confirmation APPROVAL.json --out APPROVED_BRIEF.json` mới tạo status=approved và stories[].approved=true.
- Không tự chế user_confirmation; không sử dụng dữ liệu demo để vượt quy trình. Cần tra lại tin nóng sát thời điểm đăng để tránh nội dung đã lỗi thời.

## 6. Giao sản phẩm về engine
- Từ v0.4 có renderer thật hỗ trợ 9:16, 16:9 hoặc cả hai. Gọi scripts/run_news_video.ps1 với APPROVED_BRIEF.json có approval_record nguyên vẹn. Tất cả media bên ngoài phải có license_evidence và media_path trước khi người dùng phê duyệt kịch bản.
- Với 9:16, 16:9 hoặc cả hai, ưu tiên workflow.py render --job <JOB_DIR>. Script run_news_video.ps1 dành cho trường hợp đã có approved brief hợp lệ muốn dựng độc lập; run_local.ps1 là legacy 9:16.
- Sau render chạy workflow.py qa và workflow.py handoff. QA chỉ tự tái tạo SRT sidecar thiếu/hỏng ở output MỚI; không tự sửa kịch bản, nội dung tin hay giấy phép. Handoff luôn AWAITING_HUMAN_FINAL_REVIEW để người dùng xem/nghe, kiểm nguồn và tự đăng.
- Không tự đăng lên mạng; bàn giao MP4, phụ đề, nguồn, metadata và QA.

## 7. Khả năng khôi phục
- Các file CANDIDATES, QUEUE, EVIDENCE, SELECTION, DRAFT, APPROVAL, APPROVED_BRIEF luôn có tên job riêng; không ghi đè.
- Nếu nguồn có cập nhật hoặc phát hiện sai sót: trở lại P2, thay evidence, kiểm tra lại, lấy lựa chọn/kịch bản/đồng ý mới.
- Nếu không đủ 2 nguồn độc lập: báo rõ lỗi, không tự lấp chỗ trống.
