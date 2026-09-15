# Label Guardian Product Description

## Mô Tả Ngắn

Label Guardian là nền tảng QA nhãn cho dữ liệu perception, giúp tự động phát hiện các annotation nghi ngờ sai, xếp hạng mức độ rủi ro và đưa vào quy trình review có kiểm soát bởi con người.

Sản phẩm tập trung vào việc giảm chi phí kiểm tra thủ công, tăng độ tin cậy của dữ liệu huấn luyện và chuẩn hóa vòng đời chỉnh sửa nhãn trên các dataset xe tự hành như KITTI và nuScenes.

## Mô Tả Chi Tiết

### 1. Bài Toán Cần Giải Quyết

Trong các hệ thống perception cho xe tự hành, chất lượng annotation ảnh hưởng trực tiếp đến chất lượng mô hình phát hiện vật thể, tracking và ra quyết định. Dữ liệu thường được gán nhãn bởi nhiều annotator, trên nhiều scene, nhiều sequence và nhiều điều kiện môi trường khác nhau, nên rất dễ phát sinh lỗi.

Các lỗi phổ biến gồm:

- Sai class, ví dụ `car` bị gán thành `truck` hoặc `pedestrian` bị gán nhầm.
- Bounding box bị lệch, quá rộng, quá hẹp hoặc không bám sát vật thể.
- Thiếu nhãn ở những vật thể xuất hiện rõ trong ảnh.
- Nhãn thừa ở vị trí không có vật thể thật.
- Nhãn trùng lặp trên cùng một vật thể.
- Track ID không ổn định giữa các frame liên tiếp.
- Annotation không nhất quán giữa các camera, sequence hoặc split dữ liệu.

Khi dataset tăng lên hàng chục nghìn hoặc hàng trăm nghìn frame, việc review thủ công toàn bộ dữ liệu trở nên tốn kém, chậm và khó duy trì độ nhất quán. Doanh nghiệp cần một hệ thống có thể tự động ưu tiên những mẫu đáng nghi nhất, nhưng vẫn giữ quyền quyết định cuối cùng cho con người.

### 2. Định Hướng Giải Pháp

Label Guardian được xây dựng như một lớp QA thông minh đặt phía sau annotation pipeline. Hệ thống không tự động ghi đè ground truth và không coi prediction của mô hình là chân lý tuyệt đối.

Nguyên tắc vận hành:

- Agent tự động phân tích annotation hiện tại.
- Model reference sinh prediction để làm tín hiệu đối chiếu.
- Rule engine tính toán bằng chứng định lượng và phát hiện nghi vấn.
- LLM chỉ diễn giải bằng ngôn ngữ tự nhiên và đề xuất hướng xử lý.
- Reviewer xem evidence, xác nhận, sửa hoặc bỏ qua từng case.
- Mọi thay đổi annotation được lưu thành revision mới, có audit và history.

Cách tiếp cận này giúp giảm khối lượng review thủ công mà vẫn tránh rủi ro từ việc để AI tự sửa nhãn không qua kiểm duyệt.

### 3. Core QA Agent

Core Agent của Label Guardian được thiết kế dưới dạng pipeline LangGraph tuần tự. Đây không phải là một ReAct agent tự quyết định gọi tool tùy ý, mà là một pipeline có thứ tự rõ ràng để đảm bảo kết quả ổn định, kiểm thử được và tái lập được.

Luồng xử lý chính:

- Nạp ảnh đầu vào và nhãn gốc.
- Tự tìm file annotation theo quy ước dataset nếu chỉ có `image_path`.
- Parse nhãn từ định dạng YOLO `.txt` hoặc Pascal VOC `.xml`.
- Chạy YOLO inference để sinh prediction từ ảnh.
- Validate bbox, class name, confidence và label ID.
- Ghép cặp ground truth và prediction bằng Hungarian matching trên ma trận IoU.
- Tính các metric QA như precision, recall, F1, class accuracy và average IoU.
- Áp rule deterministic để flag các issue nghi ngờ.
- Gọi LLM để sinh explanation và suggested fix theo structured output.
- Build QA report cuối cùng với status `pass`, `needs_review` hoặc `error`.

Các nhóm lỗi hiện được chuẩn hóa:

- `wrong_class`: bbox khớp vị trí nhưng class giữa ground truth và prediction khác nhau.
- `loose_bbox`: bbox đúng class nhưng chưa đủ khít với vật thể.
- `missing_label`: model phát hiện vật thể có confidence đủ cao nhưng không có nhãn tương ứng.
- `bbox_misaligned`: ground truth có prediction gần đó nhưng IoU thấp, nghi bbox bị lệch hoặc sai kích thước.
- `extra_or_wrong_label`: ground truth không khớp với prediction nào, nghi nhãn thừa hoặc sai vị trí hoàn toàn.
- `duplicate_label`: hai nhãn cùng class overlap gần như hoàn toàn, nghi bị gán trùng.

Mỗi issue đều có evidence cụ thể để reviewer truy ngược:

- IoU giữa ground truth và prediction.
- Confidence của prediction.
- Class gốc và class dự đoán.
- Bounding box liên quan.
- Label ID hoặc cặp label bị nghi ngờ.
- Severity và blocking flag.

### 4. Vai Trò Của LLM Trong Agent

Một nguyên tắc quan trọng của Label Guardian là LLM không quyết định loại lỗi, severity hay trạng thái QA. Các quyết định đó được thực hiện bằng code deterministic trước khi gọi LLM.

LLM chỉ đảm nhiệm phần diễn giải:

- Giải thích vì sao annotation bị đánh dấu nghi ngờ.
- Tóm tắt evidence theo cách dễ hiểu cho reviewer.
- Đề xuất hướng sửa phù hợp, ví dụ đổi class, kéo lại box, thêm nhãn hoặc xóa nhãn thừa.
- Không tự ý thay đổi `issue_type`.
- Không tự ý nâng/hạ `severity`.
- Không khẳng định chắc chắn nhãn sai nếu evidence chỉ cho thấy nghi vấn.

Thiết kế này giúp hệ thống tận dụng khả năng diễn giải của LLM nhưng vẫn kiểm soát được hallucination. Nếu LLM lỗi do hết quota, mất mạng hoặc sai API key, pipeline vẫn giữ nguyên metrics và flagged issues; hệ thống chỉ fallback phần explanation thay vì làm hỏng toàn bộ report.

### 5. QA Workflow Cho Người Dùng

Kết quả của agent không chỉ là một report riêng lẻ. Các evaluation được persist thành QA cases và đưa vào QA Queue để reviewer xử lý theo mức độ ưu tiên.

Workflow sản phẩm:

- Dataset được ingest và chuẩn hóa thành frame, object và provenance.
- Agent đánh giá ảnh/frame dựa trên annotation hiện tại.
- Các issue đáng nghi được lưu thành QA case.
- QA Queue cho phép lọc, sắp xếp và ưu tiên case theo risk score, severity và trạng thái.
- Reviewer mở case để xem ảnh, annotation hiện tại, prediction và evidence.
- Reviewer quyết định sửa, xác nhận đúng, bỏ qua hoặc cần kiểm tra thêm.
- Nếu cần sửa, reviewer mở 2D Editor tích hợp để chỉnh annotation trực tiếp.
- Sau khi lưu, hệ thống tạo annotation revision mới và cập nhật trạng thái case.

Quy trình này biến QA nhãn từ một hoạt động kiểm tra thủ công rời rạc thành một workflow có trạng thái, có evidence và có lịch sử kiểm toán.

### 6. Integrated 2D Editor Và Annotation Revision

Label Guardian sử dụng 2D Editor tích hợp làm công cụ chỉnh sửa annotation chính. Điều này giúp người dùng xử lý QA case ngay trong cùng một hệ thống thay vì phụ thuộc vào editor ngoài.

2D Editor hỗ trợ:

- Xem ảnh và overlay annotation.
- Tạo bounding box mới.
- Chọn, di chuyển, resize và xóa bounding box.
- Đổi class, track ID, color và attributes.
- Pan, zoom, visibility toggle.
- Undo/redo và phím tắt.
- Validation để chặn box quá nhỏ hoặc nằm ngoài ảnh.
- Save & Next để xử lý nhanh nhiều frame.
- Cảnh báo khi có thay đổi chưa lưu.

Cơ chế revision được thiết kế để bảo toàn dữ liệu:

- Dataset gốc là revision 0 và không bị sửa trực tiếp.
- Mỗi lần save tạo một annotation revision bất biến mới.
- Restore cũng tạo revision mới thay vì xóa lịch sử.
- Client gửi `expectedRevision` để tránh ghi đè khi nhiều tab/người dùng cùng sửa.
- Nếu revision đã cũ, backend trả conflict để người dùng reload trước khi lưu tiếp.
- Audit ghi lại actor, note, before/after revision và trạng thái case.

Nhờ đó, hệ thống vừa hỗ trợ chỉnh sửa nhanh trong demo/MVP, vừa giữ được yêu cầu kiểm soát dữ liệu phù hợp với môi trường doanh nghiệp.

### 7. Dữ Liệu, Ingestion Và Golden Dataset

Label Guardian được xây dựng để làm việc với dataset thật trên cloud, không chỉ dữ liệu mock. Golden dataset là nguồn dữ liệu chuẩn dùng cho QA, demo, kiểm thử pipeline, annotation review và đánh giá model.

Kiến trúc dữ liệu hiện tại:

- Ảnh/frame và artifact lớn được lưu trong Google Cloud Storage.
- Metadata, bbox, provenance, ingestion state, QA cases, evaluations và annotation revisions được lưu trong Supabase PostgreSQL.
- Backend FastAPI là lớp trung gian duy nhất giữa frontend và dữ liệu riêng tư.
- Frontend không đọc trực tiếp GCS mà gọi API backend để lấy frame, annotation và nội dung ảnh.
- Dataset chính thức được tổ chức trong vùng `datasets/official`.
- Product split được dùng làm fallback để demo khi full dataset chưa ingest xong.

Pipeline ingestion cho KITTI và nuScenes được định hướng cloud-native:

- Stage raw official archive vào cloud storage.
- Normalize ảnh/frame và annotation.
- Validate cấu trúc dataset sau khi xử lý.
- Publish dữ liệu sạch vào `datasets/official`.
- Persist `QAImage`, `QAObject` và provenance vào database.
- Ghi nhận trạng thái job, event và asset để theo dõi quá trình ingest.

Thiết kế này giúp ingestion có thể chạy gần dữ liệu trên cloud, giảm phụ thuộc vào máy cá nhân và phù hợp với các dataset lớn.

### 8. Trạng Thái Thực Tế Hiện Tại

Ở trạng thái hiện tại, hệ thống đã có nền tảng end-to-end để demo và tiếp tục mở rộng.

Các thành phần đã có:

- Backend FastAPI.
- Frontend web với QA Queue và 2D Editor.
- Supabase Auth và PostgreSQL.
- Dataset API đọc frame, image content và annotation.
- QA Agent evaluation, cache và persistence QA cases.
- Annotation revision, history, restore và audit.
- Object storage trên Google Cloud Storage.
- Product split fallback cho demo.
- Hybrid deployment: frontend trên Vercel, backend/Agent/Caddy trên Google Cloud VM.
- Static IP cho API, HTTPS và domain thật.

Deployment public hiện tại:

- Frontend: `https://labelguardian.space` và `https://www.labelguardian.space` trên Vercel.
- Backend API: `https://api.labelguardian.space` trên Google Cloud VM, HTTPS qua Caddy.
- Runtime backend: Docker Compose, self-hosted GitHub Actions runner và migration one-shot.
- Data services: Supabase Auth/PostgreSQL và private Google Cloud Storage.

Về dữ liệu, các dataset KITTI và nuScenes đã được đưa lên GCS. Full ingestion vẫn là phần nặng nhất và cần tiếp tục hoàn thiện, đặc biệt với các job xử lý dataset lớn. Để không chặn demo, hệ thống được cấu hình theo hướng ưu tiên dữ liệu thật khi sẵn sàng và fallback sang product split khi full dataset chưa hoàn tất.

### 9. Tính Khả Thi

Tính khả thi của Label Guardian đến từ cách chia nhỏ bài toán thành các lớp độc lập nhưng kết nối chặt chẽ.

Các lớp chính:

- Ingestion chuẩn hóa dữ liệu lớn từ nguồn chính thức.
- Storage layer quản lý ảnh, annotation, provenance và metadata.
- QA Agent phát hiện nghi vấn bằng evidence định lượng.
- LLM explanation layer giúp reviewer hiểu nhanh vấn đề.
- QA Queue biến kết quả agent thành workflow review có trạng thái.
- 2D Editor cho phép sửa annotation trực tiếp.
- Revision và audit bảo toàn lịch sử dữ liệu.
- Hybrid deployment giữ frontend ở CDN nhưng backend compute, dataset credential và private data trong boundary do nhóm vận hành.

MVP hiện đã chứng minh được luồng vận hành chính trên môi trường cloud thực tế. Hệ thống không cần hoàn thiện toàn bộ năng lực AI ngay từ đầu; có thể bắt đầu bằng các rule và model reference đơn giản, sau đó cải tiến dần bằng model tốt hơn, threshold được tune trên dataset thật và feedback từ reviewer.

### 10. Scope Phát Triển Tương Lai Cho Dữ Liệu 3D

Trong scope dài hạn, Label Guardian sẽ mở rộng từ QA nhãn camera 2D sang QA dữ liệu perception 3D và đa cảm biến. Đây là hướng phát triển tự nhiên vì các hệ thống xe tự hành hiện đại thường sử dụng đồng thời camera, LiDAR, calibration metadata và chuỗi thời gian.

Các loại dữ liệu 3D có thể hỗ trợ:

- LiDAR point cloud.
- 3D bounding box.
- Camera-LiDAR calibration.
- Projection giữa 3D box và ảnh 2D.
- Multi-camera synchronized frame.
- Sequence-level object tracking.
- Ego pose và timestamp metadata.

Các lỗi 3D có thể được agent phát hiện:

- 3D box lệch tâm so với cụm điểm LiDAR.
- 3D box sai kích thước hoặc sai heading/yaw.
- 3D box không bao phủ đúng object trong point cloud.
- Object có điểm LiDAR rõ nhưng thiếu nhãn 3D.
- Nhãn 3D tồn tại nhưng không có evidence từ point cloud hoặc camera.
- Sai class giữa nhãn 2D và nhãn 3D của cùng một object.
- Projection của 3D box lên ảnh không khớp với 2D bounding box.
- Track ID bị nhảy hoặc mất liên tục qua nhiều frame.
- Object velocity hoặc trajectory bất hợp lý so với sequence.
- Annotation không nhất quán giữa các camera trong cùng timestamp.

Về kỹ thuật, hướng mở rộng 3D có thể bổ sung:

- Adapter chuẩn hóa dữ liệu LiDAR và 3D annotation từ nuScenes/KITTI.
- Viewer 3D hoặc point cloud preview trong giao diện review.
- Rule engine cho 3D IoU, center distance, heading error và dimension error.
- Cross-modal consistency check giữa camera và LiDAR.
- Temporal consistency check trên toàn sequence.
- Model reference 3D như MMDetection3D hoặc các detector LiDAR phù hợp.
- QA report hợp nhất cho cùng một object qua 2D, 3D và tracking evidence.

Mục tiêu cuối cùng là biến Label Guardian thành hệ thống QA dữ liệu perception đa cảm biến, nơi camera, LiDAR và metadata thời gian được đánh giá như một nguồn dữ liệu thống nhất. Điều này giúp sản phẩm không chỉ phục vụ demo 2D hiện tại mà còn có lộ trình rõ ràng để mở rộng sang các bài toán QA annotation thực tế trong pipeline xe tự hành quy mô doanh nghiệp.

### 11. Hướng Phát Triển Tiếp Theo

Các hướng phát triển ưu tiên:

- Hoàn tất ingest full nuScenes và KITTI.
- Tune threshold của QA Agent trên dữ liệu thật.
- Tích hợp model perception reference phù hợp hơn với domain xe tự hành.
- Hoàn thiện risk score và ranking trong QA Queue.
- Bổ sung báo cáo chất lượng dataset theo class, split, sequence và annotator.
- Xây dựng feedback loop để học từ quyết định của reviewer.
- Mở rộng kiểm tra temporal consistency.
- Chuẩn hóa export annotation revision thành dataset version phát hành.
- Thiết lập CI/CD self-hosted cho build, migrate và deploy.
- Mở rộng dần sang QA dữ liệu 3D và đa cảm biến.
