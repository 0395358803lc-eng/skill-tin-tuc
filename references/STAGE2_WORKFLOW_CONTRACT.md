# Đợt 2 — Hợp đồng workflow 07–12 (v1.0.0-rc.2)

Đây là tài liệu phát triển của bộ nguồn Release Candidate, **không phải chứng nhận GA**. Tất cả video, model Piper, nhạc, từ điển phát âm và job thực tế nằm trong runtime/job workspace riêng ngoài bộ Skill.

## 07. Cảnh quay editor → renderer
- `editorial_core.MAX_VISUAL_SCENES = 20` là giới hạn chung của `draft_manifest` và `video_pipeline.render`. Visual plan chỉ có thể thay đổi **trước khi duyệt**. Tối đa 20 shot trong mỗi story; Remotion chia shot theo timeline story, không tự tạo chứng cứ nguồn.
- Cần render kiểm nghiệm 20 scene trên Windows thật trước GA.

## 08–09. Từ điển phát âm và nhạc được duyệt
Khi cần từ điển, cung cấp trên `SCRIPT_CANDIDATE.json`:
```json
{
  "pronunciation_lexicon_path": "pronunciation.json",
  "pronunciation_lexicon_sha256": "<64 hex SHA-256>"
}
```
Khi cần nhạc nền, bổ sung:
```json
{
  "music_path": "background.wav",
  "music_sha256": "<64 hex SHA-256>",
  "music_license": "Bằng chứng quyền sử dụng nhạc trong video dự kiến"
}
```
Đây chỉ là các trường bổ sung trong script thật (các trường kịch bản khác vẫn bắt buộc). Mỗi đường dẫn tương đối với **thư mục job**, không chứa `..` hay trỏ ra ngoài workspace. Đường dẫn, SHA-256 và giấy phép được đưa vào `draft.json`, tính chung trong hash phê duyệt, sau đó không được đổi.

- `workflow.py draft` kiểm SHA-256 tệp thật và từ điển JSON ngay trước khi đóng băng draft.
- `workflow.py render` kiểm lại fingerprint; chỉ truyền `--music`/`--lexicon` theo `approved.json`, loại biến môi trường phát âm không được duyệt.
- `video_pipeline.py` cũng tự kiểm fingerprint khi chạy trực tiếp và từ chối CLI ghi đè hoặc sửa nhạc/từ điển sau phê duyệt.
- Thông tin nhạc và giấy phép được ghi trong `media_rights.json`. Giấy phép vẫn phải được người dùng tự xác nhận trước khi đăng. Model giọng và các tệp âm thanh không đóng gói trong Skill.
- Các job/approved.json cũ không có nhạc/từ điển vẫn hợp lệ; không tự thêm hoặc thay đổi nội dung.

## 10–11. Trạng thái, checkpoint và khôi phục
- Lệnh `status` và `resume` chỉ đọc, có `mutation_blocked` và thông tin checkpoint/lock. Khi khóa chưa được xác định, checksum sai, thiếu checkpoint hoặc có render dở, **không được tạo thêm bản dựng hay tự duyệt**.
- Khi render hoàn thành, `RENDER_COMMITTED` cập nhật checkpoint cho `render_result.json` nguyên vẹn.
- Render thất bại được nhận diện ngay cả khi không tạo thư mục `attempt-*`. Người điều phối phải điều tra trước khi làm tiếp; không retry tự phát trên phiên sau.
- GPU fallback chỉ tối đa một lần thử CPU, với lỗi khởi tạo/encoder NVENC/CUDA rõ ràng, không áp dụng với lỗi bản quyền, nguồn, SHA, media đã duyệt.
- `reconcile-render` chỉ phục hồi một render **đã hoàn chỉnh** sau kiểm QA độc lập; không tự sửa file video chưa hoàn chỉnh. `recover-lock` chỉ được phép sau chứng minh process cũ không còn.

## 12. Quyền phê duyệt người dùng
- Chọn story và duyệt **toàn văn kịch bản + hash** là hai quyết định khác nhau.
- Không được dùng lại tin nhắn chọn story làm tin nhắn phê duyệt script. Hash không đúng phải bị từ chối; approved.json không được sửa sau khi duyệt.
- Phần mềm **không thể tự xác minh tính xác thực của một tin nhắn chat chỉ từ JSON**. AI Agent phải sử dụng tin nhắn phê duyệt thực, không tự tổng hợp confirmation và không làm giả lời người dùng.
- QA chỉ kiểm kỹ thuật. Người dùng phải xem video/nghe giọng, kiểm chứng nguồn, bản quyền và tự đăng.

## Kiểm thử và phạm vi
- `tests/test_stage2_workflow.py`: giới hạn cảnh, SHA/rights, luồng CLI, hồi phục render, không retry lỗi quyền, tách hai phê duyệt.
- GitHub Actions chạy unit test với fixture giả và kiểm tra toàn vẹn nguồn trong một checkout sạch. Bài test tổng hợp Piper cần ONNX thật chạy trong Windows runtime riêng, không chạy trên CI nguồn.
- Giữ `1.0.0-rc.2`; chỉ phát hành GA sau nghiệm thu Windows độc lập và QA video thực tế.
