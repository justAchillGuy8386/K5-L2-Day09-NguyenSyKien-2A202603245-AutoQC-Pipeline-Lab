# Báo cáo Day 09 — Nguyễn Sỹ Kiên, 2A202603245

## 1. Kết luận trước
Pipeline đưa ra quyết định **HOLD** (mã thoát: 10). Lô dữ liệu đầu vào gồm **224 ảnh**, bước intake phát hiện và loại bỏ **22 ảnh** lỗi nghiêm trọng (ảnh hỏng, quá nhỏ, trùng lặp, rò rỉ tập test), tiếp nhận **202 ảnh** sạch vào quy trình và xuất **202 ảnh** ra bản nháp tại `submission/export/clean_v1/`. Lý do chính: Pipeline đã giải quyết sạch toàn bộ lỗi cú pháp bắt buộc (`n_errors = 0`), tuy nhiên sau khi người duyệt sử dụng hết ngân sách **80/80 ảnh**, hệ thống vẫn còn **44/202 ảnh** (tỉ lệ **21.78%**) mang các cảnh báo ngữ nghĩa chưa được xác minh, vượt qua ngưỡng quy định của cổng Hold (10.00%).

## 2. Lỗi và phân việc
Tổng hợp các lỗi phát hiện từ `02_error_list_v1` (tổng số 224 ảnh đầu vào, tiếp nhận 202 ảnh):

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `CORRUPT_IMAGE` | 2 ảnh | Máy loại bỏ (`remove_image`) | File ảnh hỏng không thể giải mã (`OSError`, `UnidentifiedImageError`), không có giá trị huấn luyện. |
| `BAD_SIZE` | 3 ảnh | Máy loại bỏ (`remove_image`) | Cạnh ngắn $< 250\text{px}$, vi phạm yêu cầu độ phân giải tối thiểu của dự án. |
| `DUP_IMAGE_EXACT` | 8 ảnh | Máy loại bỏ (`remove_image`) | Trùng khớp từng byte (`md5`), gây thiên lệch dữ liệu nếu giữ lại. |
| `DUP_IMAGE_NEAR` | 4 ảnh | Máy loại bỏ (`remove_image`) | Trùng gần đúng qua perceptual hash ($\text{pHash} \le 10$), là các ảnh thu nhỏ/cắt cúp từ ảnh gốc. |
| `LEAK_TEST` | 5 ảnh | Máy loại bỏ (`remove_image`) | Trùng với tập kiểm định `test/val`, loại bỏ để tránh rò rỉ dữ liệu (data leakage) tạo metric đẹp giả. |
| `BAD_FORMAT` | 3 dòng | Máy sửa (`drop_line`) | Dòng nhãn thiếu cột hoặc chứa giá trị `nan`/`inf`, lỗi cú pháp rõ ràng, xoá bỏ an toàn. |
| `BAD_CLASS_ID` | 6 dòng | Máy sửa (`drop_line`) | ID lớp ngoài khoảng 0..3 (-1, 4, 7, 93), không thuộc danh mục bài toán. |
| `BOX_ZERO` | 4 dòng | Máy sửa (`drop_line`) | Chiều rộng hoặc chiều cao $\le 0$, box rỗng không mang thông tin không gian. |
| `BOX_OUT_OF_IMAGE` | 8 dòng | Máy sửa (`clip_box`) | Mép box tràn ra ngoài khoảng $[0, 1]$, máy cắt gọn toạ độ về mép ảnh an toàn. |
| `DUP_BOX` | 7 dòng | Máy sửa (`drop_line`) | Hai box cùng lớp gần như trùng khít ($IoU > 0.9$), xoá box lặp ở dòng sau. |
| `BAD_CLASS_NAME` | 2 mục | Máy sửa (`rename_classes`) | Tên lớp trong `data.yaml` viết hoa sai ('Person', 'Bus'), chuẩn hoá lại theo config. |
| `MISSING_LABEL_FILE` | 6 ảnh | Người sửa (ưu tiên) | Ảnh có dữ liệu nhưng thiếu file `.txt`; máy không được bịa nhãn mà phải chuyển người gán. |
| `EMPTY_LABEL` | 12 ảnh | Người kiểm tra | File nhãn rỗng; cần người xác nhận là ảnh nền thật hay do gán sót vật thể. |
| `BOX_TINY` | 6 dòng | Người kiểm tra | Cạnh box $< 12\text{px}$, cần mắt người đánh giá xem vật thể có nhận diện được không hay là nhiễu. |
| `BOX_HUGE` | 3 dòng | Người kiểm tra | Box chiếm $> 95\%$ diện tích ảnh, nghi ngờ vẽ bao trùm cả khung nền. |
| `CLASS_RARE` | 4 mục | Người theo dõi | Cảnh báo thống kê mất cân bằng số lượng mẫu giữa các lớp trong dataset. |
| `POSSIBLE_WRONG_CLASS` | 18 dòng | Người duyệt | Model checker và nhãn lệch lớp (IoU cao); máy không thể tự quyết định nhãn nào đúng. |
| `POSSIBLE_MISSING` | 68 dòng | Người duyệt | Model checker thấy vật thể rõ ràng nhưng nhãn không có box; người cần vẽ bổ sung. |
| `POSSIBLE_LOOSE_BOX` | 31 dòng | Người duyệt | Cùng lớp nhưng $IoU < 0.5$; người cần căn chỉnh lại mép bounding box. |
| `POSSIBLE_FALSE_POS` | 29 dòng | Người duyệt | Nhãn có box nhưng model không phát hiện; người xác minh xem box bị thừa hay model bỏ sót. |

**Giải thích hàng đợi `05_review_queue.csv`:**
- Hàng đợi được sắp xếp theo tổng trọng số ưu tiên: Các ảnh `NEEDS_LABEL` mang trọng số cao nhất (10 điểm) vì thiếu toàn bộ nhãn; các ảnh vừa bị xoá dòng lỗi (`FIXED_DROP_LINE`: 2 điểm) lại vừa có nghi vấn sai lớp (`POSSIBLE_WRONG_CLASS`: 3 điểm) hoặc thiếu nhãn (`POSSIBLE_MISSING`: 2 điểm) được ưu tiên xếp ngay đầu (ví dụ: `img_0020` có priority 14.53, `img_0185` có priority 10.05, kế đến là các ảnh thiếu file nhãn như `img_0031`, `img_0053`).
- Với ngân sách 80 ảnh, người duyệt mô phỏng đã xử lý sạch 6 ảnh `NEEDS_LABEL` và giải quyết được phần lớn các ca nghiêm trọng nhất: số ca `POSSIBLE_WRONG_CLASS` giảm từ 18 xuống còn 4 dòng; `POSSIBLE_MISSING` giảm từ 68 xuống 26 dòng; `POSSIBLE_LOOSE_BOX` giảm từ 31 xuống 24 dòng. Người duyệt đã can thiệp và xử lý thành công **hơn 60 lỗi ngữ nghĩa** phức tạp nhất.

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|:---:|:---:|:---:|---|
| `duplicates.phash_dist` | 2 | **10** | DUP_IMAGE_NEAR: 1.00 / 0.50 → 1.00 / 0.67 | Tăng Recall để phát hiện các ảnh gần trùng biến đổi (như `img_0186` thu nhỏ 85% từ `img_0061` có khoảng cách 10). Không chọn 16 vì trên tập raw sẽ xoá oan 9 ảnh sạch do băm quá lỏng. |
| `second_opinion.conf` | 0.25 | **0.50** | MISSING: 0.50 / 1.00 → 0.57 / 1.00; F1: 0.67 → 0.73 | Giảm báo động giả để không làm tràn ngân sách 80 ảnh của người duyệt, đồng thời bảo toàn Recall 100% (bắt trọn mọi ca thiếu nhãn được chèn). Nâng lên 0.70 thì Recall sụt giảm xuống 0.88. |

**Một chỗ calibration có thể đánh lừa bạn:**
- Tập `data/calib/` chỉ có 39 ảnh và các ảnh gần trùng được tạo nhân tạo với mức biến đổi rất mạnh (crop sâu, chỉnh màu gắt). Tại ngưỡng `phash_dist = 16`, tập calib cho kết quả F1 cao nhất (0.91) và Recall cao nhất (0.83).
- Tuy nhiên, khi áp dụng `phash_dist = 16` vào tập thực tế `data/raw/` (224 ảnh), khoảng cách Hamming 16 (chiếm $16/64 = 25\%$ số bit) là quá lỏng, khiến số ảnh bị loại vọt lên 26 ảnh (tăng thêm 9 ảnh). Mở ảnh kiểm tra thực tế cho thấy các ảnh hoàn toàn khác nhau bị nhận nhầm là trùng lặp: ví dụ `img_0011` khác hoàn toàn `img_0008` (một ảnh có 1 người, một ảnh có 2 người) nhưng khoảng cách pHash đúng bằng 16; `img_0013` bị nhận nhầm là `LEAK_TEST` với `test_087.jpg`. Ngưỡng `phash_dist = 10` là điểm dừng hợp lý, vừa bắt được ảnh thu nhỏ thật (`img_0186`), vừa giữ độ chính xác tuyệt đối không xoá oan ảnh sạch.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
- **(a) Chứng minh gate chặn đúng:** Khi chạy thử nghiệm không có người duyệt bằng lệnh:
  `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`
  Do không có người gán nhãn, 6 ảnh thiếu nhãn vẫn còn nguyên (`n_errors = 6`). Cửa chặn gate lập tức đưa ra kết luận **REWORK**, tiến trình kết thúc với mã thoát **20**, và thư mục xuất `work/exp_nb/clean_v1/` hoàn toàn **không được tạo ra**. Điều này chứng minh cửa chặn hoạt động thực chất, kiên quyết không xuất bản dataset khi còn lỗi bắt buộc.
- **(b) ≥ 2 điểm mù của pipeline:**
  1. *Box lỏng nhẹ nhưng IoU vẫn $\ge 0.5$:* Nếu người gán nhãn vẽ box hơi rộng quanh vật thể nhưng IoU với box của model checker đạt $0.52 > \text{iou\_loose} (0.50)$, pipeline xem như hai bên đã đồng thuận đúng lớp và không phát cảnh báo.
  2. *Gán nhầm lớp ở các ca khó mà model lớn cũng nhầm:* Các trường hợp xe bán tải (pickup) hoặc xe van ranh giới giữa `car` và `truck`: nếu nhãn gán là `car` và model `yolo26l` cũng dự đoán là `car` với độ tin cậy cao, pipeline áp dụng nguyên tắc *"agreement is silent"* nên hoàn toàn bỏ qua.
  3. *Ảnh gần trùng nhưng bị crop sâu $> 50\%$ hoặc xoay nghiêng:* Băm pHash 64-bit chỉ bắt được các biến đổi co giãn nhẹ hoặc chỉnh sáng; khi ảnh bị cắt cúp quá nửa, pHash thay đổi hoàn toàn và pipeline không thể nhận diện trùng lặp.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)

Thực nghiệm huấn luyện mô hình `yolo26n.pt` trong 20 epochs, batch size 16, ảnh 640x640 trên Google Colab T4 GPU với 2 hạt giống ngẫu nhiên (seed 0 và seed 1):

| biến thể | #ảnh train | số seed | map50 (TB ± độ lệch) | map50_95 (TB ± độ lệch) | precision (TB ± độ lệch) | recall (TB ± độ lệch) |
|---|---|---|---|---|---|---|
| raw | 224 | 2 | 0.726 ± 0.000 | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| clean | 202 | 2 | 0.711 ± 0.018 | 0.491 ± 0.010 | 0.764 ± 0.033 | 0.629 ± 0.023 |

Chênh mAP50 (clean − raw) = **-0.015** (-1.5%).

**Phân tích và kết luận trung thực:**
- Độ chênh lệch mAP50 giữa clean và raw là $-0.015$, trong khi độ lệch chuẩn giữa hai lần chạy seed của chính tập clean là **$0.0181$ (1.81%)** (seed 0 đạt 0.7233, seed 1 đạt 0.6977). Vì chênh lệch giữa hai biến thể nhỏ hơn độ dao động ngẫu nhiên giữa các seed, **kết luận trung thực là chưa có bằng chứng thống kê cho thấy clean vượt trội hay kém hơn raw**, sự khác biệt hiện nằm trong vùng nhiễu ngẫu nhiên.
- **Hai giả thuyết giải thích:**
  1. *Tập test (100 ảnh) bị nhiễm ảnh rò rỉ từ tập raw:* Ở tập raw có 5 ảnh bị `LEAK_TEST` trùng với kho test/val. Khi train trên raw, model học thuộc lòng các ảnh này nên điểm mAP đo trên test set bị cao giả tạo (hiệu ứng "học vẹt"). Tập clean đã loại bỏ các ảnh này nên đánh giá phản ánh đúng năng lực tổng quát hoá.
  2. *Quy mô tập train của clean bị giảm 10% (202 vs 224 ảnh):* Với tập dữ liệu nhỏ (~200 ảnh), việc loại bỏ 22 ảnh rác/trùng làm giảm số lượng box huấn luyện ở các lớp ít mẫu (ví dụ AP50 lớp truck giảm từ 0.657 xuống 0.596).
  - *Cách kiểm chứng:* Đánh giá mô hình trên một tập test độc lập lớn hơn hoàn toàn sạch rò rỉ, hoặc bổ sung thêm ảnh mới đã qua kiểm chuẩn để đưa kích thước tập clean trở lại mức 224 ảnh.

## 6. Quyết định và ghi chú AI
- **(a) Quyết định cuối:** Giữ nguyên quyết định **HOLD**. Để nâng cấp thành **Release**, dự án cần cấp thêm ngân sách cho người duyệt tối thiểu **24 ảnh nữa** (duyệt $\ge 104$ ảnh thay vì 80 ảnh) nhằm đưa số ảnh còn cảnh báo xuống $< 20/202$ ảnh ($< 10\%$).
- **(b) Ghi chú sử dụng AI (theo RULES.md):**
  - *Prompt chính:* "Viết hàm run cho label_format.py duyệt các dòng nhãn YOLO, dùng parse_yolo_line bắt BAD_FORMAT, kiểm tra BAD_CLASS_ID, BOX_ZERO, tính overflow theo max(-x1, -y1, x2-1, y2-1) cho BOX_OUT_OF_IMAGE, DUP_BOX theo iou_xywh, cảnh báo BOX_TINY và BOX_HUGE, không làm crash khi gặp dòng hỏng."
  - *Cách kiểm tra code:* Chạy 79 unit tests có sẵn (`pytest`), đối chiếu log sửa đổi trong `03_fixes.csv`, và chạy `scripts/check_submission.py`.
  - *Một lần AI sai:* Ban đầu AI áp dụng bộ lọc diện tích `min_area_px` cho cả bước kiểm tra `POSSIBLE_FALSE_POS` trong `second_opinion.py`, khiến các box nhãn nhỏ khớp với dự đoán nhỏ của model bị báo nhầm thành FALSE_POS (bị bắt bởi test `test_false_positive_uses_fp_conf_and_ignores_min_area`); sau đó phải sửa lại để bước kiểm FALSE_POS chỉ lọc theo `fp_conf` mà không lọc diện tích.

*(Thưởng +2, tùy chọn)* CVAT: Thực hiện lọc box nhỏ `width < 20` trên ảnh `img_0026` và `img_0161`. Số lượng box phát hiện khớp với cảnh báo `BOX_TINY` của pipeline (pipeline dùng ngưỡng 12px, còn CVAT hỗ trợ lọc trực quan ở ngưỡng 20px). Về thuộc tính `can_review`: người gán nhãn đánh dấu `can_review=true` khi gặp các ca mờ, khó phân biệt cần trưởng nhóm kiểm tra lại; pipeline mô phỏng điều này bằng cách đưa các cảnh báo ngữ nghĩa (`POSSIBLE_*`) vào hàng đợi `05_review_queue.csv` để người duyệt xem xét.
