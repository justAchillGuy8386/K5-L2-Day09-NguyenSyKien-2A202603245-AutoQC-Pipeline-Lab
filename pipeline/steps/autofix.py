"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |
"""
from collections import defaultdict
import yaml

from ..common import ERROR, parse_yolo_line


def fix(ds, issues, cfg):
    error_issues = [i for i in issues if i.severity == ERROR]
    if not error_issues:
        return []

    fixes = []

    # 1. Sửa BAD_CLASS_NAME trong data.yaml
    for iss in error_issues:
        if iss.code == "BAD_CLASS_NAME":
            old_names = ds.yaml_names()
            raw_cfg = {}
            if ds.yaml_path.exists():
                try:
                    raw_cfg = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
                except Exception:
                    raw_cfg = {}
            raw_cfg["names"] = list(cfg["classes"])
            ds.yaml_path.write_text(yaml.safe_dump(raw_cfg, allow_unicode=True), encoding="utf-8")
            fixes.append({
                "image": "data.yaml",
                "line": "",
                "action": "rename_classes",
                "before": str(old_names),
                "after": str(cfg["classes"]),
            })
            break

    # 2. Xóa ảnh + nhãn lỗi (DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE)
    removed_stems = set()
    for iss in error_issues:
        if iss.code.startswith("DUP_IMAGE_") or iss.code in {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}:
            stem = iss.image
            if stem not in removed_stems:
                removed_stems.add(stem)
                img_p = ds.image_path(stem)
                if img_p and img_p.exists():
                    img_p.unlink()
                lbl_p = ds.label_path(stem)
                if lbl_p and lbl_p.exists():
                    lbl_p.unlink()
                fixes.append({
                    "image": stem,
                    "line": "",
                    "action": "remove_image",
                    "before": stem,
                    "after": "(đã xoá)",
                })

    # 3. Ghi nhận ảnh thiếu file nhãn MISSING_LABEL_FILE (chuyển người, không tạo file)
    needs_label_stems = set()
    for iss in error_issues:
        if iss.code == "MISSING_LABEL_FILE" and iss.image not in removed_stems:
            if iss.image not in needs_label_stems:
                needs_label_stems.add(iss.image)
                fixes.append({
                    "image": iss.image,
                    "line": "",
                    "action": "needs_label",
                    "before": "(không có file)",
                    "after": "chuyển người gán",
                })

    # 4. Sửa các lỗi ở cấp dòng nhãn trong file txt
    # Gom lỗi theo từng file và từng dòng gốc
    line_issues_by_stem = defaultdict(lambda: defaultdict(list))
    for iss in error_issues:
        if iss.line is not None and iss.image not in removed_stems:
            line_issues_by_stem[iss.image][iss.line].append(iss)

    drop_codes = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}

    for stem in sorted(line_issues_by_stem.keys()):
        lbl_p = ds.label_path(stem)
        if not lbl_p.exists():
            continue

        orig_lines = lbl_p.read_text(encoding="utf-8", errors="replace").splitlines()
        lines_dict = line_issues_by_stem[stem]
        new_lines = []
        stem_fixes = []

        for line_no, raw_line in enumerate(orig_lines, 1):
            if line_no not in lines_dict:
                if raw_line.strip():
                    new_lines.append(raw_line)
                continue

            issues_on_line = lines_dict[line_no]
            codes_on_line = {i.code for i in issues_on_line}

            # Quy tắc ưu tiên: drop_line thắng clip_box
            if codes_on_line & drop_codes:
                stem_fixes.append({
                    "image": stem,
                    "line": line_no,
                    "action": "drop_line",
                    "before": raw_line,
                    "after": "",
                })
                continue

            if "BOX_OUT_OF_IMAGE" in codes_on_line:
                try:
                    c, cx, cy, w, h = parse_yolo_line(raw_line)
                    x1 = cx - w / 2.0
                    y1 = cy - h / 2.0
                    x2 = cx + w / 2.0
                    y2 = cy + h / 2.0

                    x1_c = max(0.0, min(1.0, x1))
                    x2_c = max(0.0, min(1.0, x2))
                    y1_c = max(0.0, min(1.0, y1))
                    y2_c = max(0.0, min(1.0, y2))

                    new_w = x2_c - x1_c
                    new_h = y2_c - y1_c

                    if new_w <= 0.0 or new_h <= 0.0:
                        stem_fixes.append({
                            "image": stem,
                            "line": line_no,
                            "action": "drop_line",
                            "before": raw_line,
                            "after": "",
                        })
                    else:
                        new_cx = (x1_c + x2_c) / 2.0
                        new_cy = (y1_c + y2_c) / 2.0
                        new_str = f"{int(c)} {new_cx:.6g} {new_cy:.6g} {new_w:.6g} {new_h:.6g}"
                        new_lines.append(new_str)
                        stem_fixes.append({
                            "image": stem,
                            "line": line_no,
                            "action": "clip_box",
                            "before": raw_line,
                            "after": new_str,
                        })
                except Exception:
                    stem_fixes.append({
                        "image": stem,
                        "line": line_no,
                        "action": "drop_line",
                        "before": raw_line,
                        "after": "",
                    })
                continue

        if new_lines:
            lbl_p.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        else:
            lbl_p.write_text("", encoding="utf-8")

        fixes.extend(stem_fixes)

    return fixes
