"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds


def run(ds, cfg, preds=None):
    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    so_cfg = cfg.get("second_opinion", {})
    conf_thresh = so_cfg.get("conf", 0.25)
    min_area_px = so_cfg.get("min_area_px", 600)
    fp_conf = so_cfg.get("fp_conf", 0.1)
    iou_missing = so_cfg.get("iou_missing", 0.3)
    iou_match = so_cfg.get("iou_match", 0.5)
    iou_loose = so_cfg.get("iou_loose", 0.5)

    num_classes = len(ds.classes)
    issues = []

    for img_p in ds.image_files():
        stem = img_p.stem

        if preds is None or stem not in preds:
            continue
        if not ds.label_path(stem).exists():
            continue

        sz = ds.image_size(stem)
        if sz is None:
            continue
        img_w, img_h = sz

        raw_lines = ds.read_label_lines(stem)
        if raw_lines is None:
            continue

        # Lấy nhãn hợp lệ kèm số dòng gốc
        valid_labels = []
        for line_no, text in raw_lines:
            try:
                c, cx, cy, w, h = parse_yolo_line(text)
                if 0 <= c < num_classes:
                    valid_labels.append((line_no, c, (cx, cy, w, h)))
            except ValueError:
                continue

        stem_preds = preds.get(stem, [])

        # 1. Lọc các dự đoán của model cho kiểm tra thiếu/lỏng/sai lớp
        P = [
            r for r in stem_preds
            if r[1] >= conf_thresh and (r[4] * img_w * r[5] * img_h) >= min_area_px
        ]

        for r in P:
            p_cls = int(r[0])
            p_conf = float(r[1])
            p_box = (float(r[2]), float(r[3]), float(r[4]), float(r[5]))

            # Tìm các ứng viên nhãn có IoU >= iou_missing
            cands = []
            for line_no, l_cls, l_box in valid_labels:
                iou = iou_xywh(p_box, l_box)
                if iou >= iou_missing:
                    cands.append((line_no, l_cls, l_box, iou))

            if not cands:
                # Không có box nhãn nào khớp
                issues.append(
                    Issue(
                        "second_opinion",
                        WARN,
                        "POSSIBLE_MISSING",
                        stem,
                        f"model phát hiện vật (lớp {p_cls}, conf {p_conf:.2f}) nhưng nhãn thiếu box",
                        line=None,
                        extra={"conf": p_conf, "pred_cls": p_cls},
                    )
                )
                continue

            same_class = [c for c in cands if c[1] == p_cls]
            if same_class:
                best_same_iou = max(c[3] for c in same_class)
                if best_same_iou < iou_loose:
                    issues.append(
                        Issue(
                            "second_opinion",
                            WARN,
                            "POSSIBLE_LOOSE_BOX",
                            stem,
                            f"box nhãn cùng lớp {p_cls} nhưng IoU thấp ({best_same_iou:.2f} < {iou_loose})",
                            line=None,
                            extra={"conf": p_conf, "iou": best_same_iou},
                        )
                    )
                # Ngược lại, nếu best_same_iou >= iou_loose thì nhãn đúng lớp đã phủ vật này -> không cờ
                continue

            # Không có nhãn cùng lớp -> kiểm tra khác lớp
            best_diff_iou = max(c[3] for c in cands)
            if best_diff_iou >= iou_match:
                issues.append(
                    Issue(
                        "second_opinion",
                        WARN,
                        "POSSIBLE_WRONG_CLASS",
                        stem,
                        f"nghi gán nhầm lớp: model dự đoán lớp {p_cls} (conf {p_conf:.2f}), IoU {best_diff_iou:.2f}",
                        line=None,
                        extra={"conf": p_conf, "iou": best_diff_iou, "pred_cls": p_cls},
                    )
                )

        # 2. Kiểm tra POSSIBLE_FALSE_POS (box nhãn không khớp dự đoán nào của model)
        # Sử dụng fp_conf và không lọc diện tích min_area_px
        fp_preds = [r for r in stem_preds if r[1] >= fp_conf]
        for line_no, l_cls, l_box in valid_labels:
            matched = False
            for r in fp_preds:
                p_box = (float(r[2]), float(r[3]), float(r[4]), float(r[5]))
                if iou_xywh(l_box, p_box) >= iou_missing:
                    matched = True
                    break
            if not matched:
                issues.append(
                    Issue(
                        "second_opinion",
                        WARN,
                        "POSSIBLE_FALSE_POS",
                        stem,
                        f"box nhãn không khớp vật thể nào của model (dòng {line_no})",
                        line=line_no,
                        extra={"line": line_no, "label_cls": l_cls},
                    )
                )

    return issues
