# Mô hình learner, graph và Best-First Search

## Mastery và kiến thức đã quan sát

Tại thời điểm `t`, với learner `u` và concept `c`:

`M(u,c,t) = correct(u,c, submitted_at < t) / total(u,c, submitted_at < t)`.

Lưu tử số, mẫu số và `as_of`; không dùng sự kiện cùng hoặc sau cutoff. Một câu hỏi nối tới nhiều concept đóng góp một quan sát cho từng concept. Các lần làm lại là các sự kiện riêng nếu `log_id` khác. Khi không có dữ liệu, mastery là **unknown**. Trong tính điểm chỉ, unknown được gán quy ước `N=0.5`; điều này không biến unknown thành mastery quan sát.

Concept chỉ ở tập `K` ban đầu nếu có ít nhất `min_interactions` quan sát và mastery đạt `tau`. `tau` và số lượt tối thiểu là tham số thực nghiệm, không phải chuẩn giáo dục; chúng được chọn trên validation.

## Cạnh tiên quyết

Node là concept. Cạnh có hướng `A → B` nghĩa là A prerequisite của B. Chỉ quan hệ trong `cs.json` có `ground_truth=1` được dùng làm ràng buộc cứng; nhãn `0` là quan hệ được chú thích là không phải prerequisite. `text_predict` và `graph_predict` là dự đoán, không dùng làm ground truth. Pipeline kiểm tra ID, self-loop, duplicate và chu trình; quan hệ không hợp lệ được ghi vào `records_rejected.csv`, không đảo cạnh.

## Điểm heuristic

Với ứng viên `c`:

`H(c) = wP·P(c) + wN·N(c) + wD·D(c) + wR·R(c)`

- `P(c)` là tỷ lệ prerequisite đã có trong K; nếu prerequisite rỗng thì 1. Do điều kiện ứng viên yêu cầu mọi prerequisite đã ở K, P bằng 1 với mọi ứng viên hợp lệ; mặc định `wP=0`.
- `N(c)=1-M(u,c)` nếu có mastery quan sát; nếu unknown thì dùng 0.5 theo quy ước trên.
- `d(c)=1 - train_correct(c)/train_total(c)` chỉ dùng tương tác train. `a(u)` là trung bình mastery quan sát trước cutoff, mặc định 0.5 nếu chưa có. `D(c)=1-|d(c)-a(u)|` là một độ phù hợp đơn giản do nhóm đề xuất; không phải công thức giáo dục đã được kiểm chứng.
- `R(c)=1/(1+dist(c,target))`, trong đó khoảng cách là số cạnh trên đường có hướng ngắn nhất từ prerequisite lên target. Khi target không tới được, thuật toán không đưa concept ngoài vùng prerequisite target vào kế hoạch.
- Các trọng số không âm, tổng bằng 1. Demo dùng cấu hình được chọn trên validation: `(wP,wN,wD,wR)=(0,0.1,0.4,0.5)`, `tau=0.5`, tối thiểu 1 interaction. NDCG@5 validation bằng 0 với 5 learner có nhãn; đây là tham số thực nghiệm đã khóa, không phải chuẩn giáo dục hay bằng chứng cấu hình này tốt hơn.

## Best-First Search

Trạng thái `s=(L,K)` có kế hoạch có thứ tự L và tập K gồm kiến thức đã đạt theo lịch sử cộng concept được **giả định hoàn thành** trong nhánh kế hoạch. Khởi tạo L rỗng. Ứng viên phải nằm trong tập tổ tiên của target, chưa ở K và có đủ prerequisite trong K. Thêm ứng viên tạo trạng thái kế tiếp; mastery lịch sử không bị thay đổi.

OPEN là priority queue của nhiều trạng thái. Mỗi trạng thái được xếp theo H của concept vừa thêm, điểm cao trước; hòa thì `concept_id` tăng dần, sau đó đường đi theo tuple ID tăng dần. `visited` ngăn mở rộng lại cùng tập K. Các nhánh thay thế vẫn ở OPEN. Giới hạn số trạng thái và thời gian bảo vệ tài nguyên; các trạng thái hết giới hạn trả `budget_exhausted`.

Kết thúc với một trong các trạng thái: `target_already_mastered`, `reached`, `no_path`, hoặc `budget_exhausted`. Greedy Best-First ưu tiên H cục bộ và không cam kết lộ trình tối ưu toàn cục.

## Kiểm tra độ nhạy

Trong thực nghiệm, tau, minimum interactions và tổ hợp trọng số được chọn theo NDCG@K trên validation; cấu hình sau đó khóa trước khi đọc test. So sánh cấu hình cho thấy mức ảnh hưởng của D và các thành phần khác trong metric lịch sử, nhưng không chứng minh tác động nhân quả hoặc learning gain. Khi dữ liệu thật chưa sẵn sàng, kiểm thử thuật toán chỉ dùng fixture tổng hợp trong test và không công bố như thực nghiệm.
