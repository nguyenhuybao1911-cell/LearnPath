"""Write the Vietnamese data handoff progress report as a dependency-free DOCX."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ET.register_namespace("w", W)
ET.register_namespace("r", R)


def _paragraph(text: str, style: str | None = None) -> ET.Element:
    paragraph = ET.Element(f"{{{W}}}p")
    if style:
        properties = ET.SubElement(paragraph, f"{{{W}}}pPr")
        ET.SubElement(properties, f"{{{W}}}pStyle", {f"{{{W}}}val": style})
    run = ET.SubElement(paragraph, f"{{{W}}}r")
    node = ET.SubElement(run, f"{{{W}}}t", {"{http://www.w3.org/XML/1998/namespace}space": "preserve"})
    node.text = text
    return paragraph


def write_report(profile_path: Path, output: Path, summary_path: Path | None = None) -> None:
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path and summary_path.is_file() else None
    body = ET.Element(f"{{{W}}}body")
    paragraphs = [
        ("BÁO CÁO TIẾN ĐỘ XỬ LÝ DỮ LIỆU", "Title"),
        ("Đề tài: Cá nhân hóa lộ trình học tập dựa trên Best-First Search và heuristic", None),
        ("Phạm vi bàn giao: phần dữ liệu; công việc ngày 1–2 của An và ngày 2 của Bảo. Các nhiệm vụ ngày khác và phần ngày 3 trở đi của Bảo chưa thực hiện.", None),
        ("1. Kiểm tra nguồn và phạm vi", "Heading1"),
        ("Nguồn history: MOOCCubeX, relations/user-problem.json, tải từ host LFS chính thức. File đủ 22,453,311,654 byte; SHA-256 khớp manifest nguồn: dd0d771f73263a218aaccf7340333627ef13e5f2ec4bc235ad0b339a13112e90.", None),
        ("Phạm vi domain được xác định từ concept catalog bằng hậu tố ID khớp chính xác với field. Endpoint prerequisite được bổ sung chỉ khi ánh xạ duy nhất. Interaction nối bằng problem_id nguyên gốc; không suy đoán tên hay sửa ID.", None),
        ("MOOCCubeX là dữ liệu tiếng Trung; giữ nguyên văn bản nguồn. Event log_id khác nhau được giữ lại như các lần làm riêng; attempts không nhân bản event.", None),
        ("2. Kết quả profile ba lĩnh vực", "Heading1"),
    ]
    for title, style in paragraphs:
        body.append(_paragraph(title, style))

    for domain in ("cs", "math", "psy"):
        item = profile["domains"][domain]
        splits = item["temporal_split_counts"]
        label = {"cs": "Khoa học máy tính", "math": "Toán học", "psy": "Tâm lý học"}[domain]
        body.append(_paragraph(
            f"• {label}: {item['interactions']:,} interaction; {item['learners']:,} learner; "
            f"{item['concepts_with_history']:,} concept có lịch sử; "
            f"{item['annotated_prerequisite_edges']:,} cạnh prerequisite được chú thích dương; "
            f"train/validation/test = {splits['train']:,}/{splits['validation']:,}/{splits['test']:,}.",
            "ListParagraph"))
    body.append(_paragraph(
        f"Miền được chọn: {profile['best_supported_domain']}. Ngưỡng tối thiểu 2.000 áp dụng cho train sau chia thời gian; "
        f"kết quả đạt ngưỡng: {profile['best_supported_domain_meets_minimum_train_interactions']}. "
        "Điều này là điều kiện dữ liệu đầu vào, không phải bằng chứng tổng quát hóa hay learning gain."))
    body.append(_paragraph("3. Kiểm thử và xử lý", "Heading1"))
    body.append(_paragraph("Đã chạy 26/26 kiểm thử Python đạt. Có kiểm tra schema/nối ID, phân biệt log trùng với lần làm lại, chia thời gian không leakage, learner state/heuristic, graph lỗi, nhiều prerequisite và OPEN giữ các nhánh thay thế."))
    if summary:
        body.append(_paragraph(
            f"Pipeline bàn giao: {summary['interactions_clean']:,} interaction; "
            f"{summary['selected_learners']:,} learner; {summary['concepts']} concept; "
            f"{summary['problems']} problem; {summary['prerequisite_edges']:,} cạnh prerequisite; "
            f"split {summary['split_counts']}.", "Heading2"))
        body.append(_paragraph(
            f"ID join rate trong các interaction hợp lệ: {summary['id_join_rate_all_valid_interactions']}; "
            f"unmatched concept links: {summary['interactions_unmatched_any_concept']:,}; "
            f"out of selected domain: {summary['interactions_outside_domain']:,}; "
            f"invalid: {summary['interactions_invalid']:,}; duplicate stored log_id: {summary['duplicate_stored_rows']:,}."))
    else:
        body.append(_paragraph("Bước xử lý CSV và nạp thử PostgreSQL đang tiếp tục; chưa xóa raw hay thay bộ CSV cũ."))
    body.append(_paragraph("Đã chạy scripts/verify_processed_data.py trên data/processed: số dòng đầu ra khớp profile/summary; có 7.975 log_id interaction duy nhất; unmatched gzip được đọc đến EOF, CRC hợp lệ và có 133.349.499 dòng trước khi xóa để tiết kiệm dung lượng."))
    body.append(_paragraph("Tích hợp PostgreSQL được kiểm tra trên database riêng learnpath_candidate_20261022; database cũ không bị sửa. Import hai lần không tăng số dòng. API health trả 39.292 concept; API learner state trả 39.292 concept, với concept chưa quan sát mang trạng thái unknown. Unicode tiếng Trung khớp giữa CSV và API."))
    body.append(_paragraph("4. Bàn giao và giới hạn", "Heading1"))
    body.append(_paragraph("Đã giữ CSV chuẩn hóa, profile, cấu hình, source manifest, báo cáo audit và source commit. Payload raw khoảng 22,9 GB, file unmatched gzip khoảng 896 MB và SQLite staging bỏ dở được xóa sau khi đối chiếu dữ liệu, kiểm tra database/API và lưu bộ cũ tại data/backup/processed_previous_20261022/. Không bổ sung dữ liệu giả."))
    body.append(_paragraph("Các số liệu lịch sử mô tả độ phủ và tương tác quan sát được; chúng không chứng minh đường học tối ưu hoặc kết quả học tăng."))
    section = ET.SubElement(body, f"{{{W}}}sectPr")
    ET.SubElement(section, f"{{{W}}}pgSz", {f"{{{W}}}w": "12240", f"{{{W}}}h": "15840"})
    ET.SubElement(section, f"{{{W}}}pgMar", {f"{{{W}}}top": "1440", f"{{{W}}}right": "1440", f"{{{W}}}bottom": "1440", f"{{{W}}}left": "1440"})
    document = ET.Element(f"{{{W}}}document")
    document.append(body)

    types = ET.fromstring('''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
      <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
      <Default Extension="xml" ContentType="application/xml"/>
      <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
      <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
    </Types>''')
    rels = ET.fromstring('''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
    </Relationships>''')
    document_rels = ET.fromstring('''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
    </Relationships>''')
    styles = ET.fromstring(f'''<w:styles xmlns:w="{W}">
      <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="Arial"/><w:sz w:val="22"/></w:rPr></w:style>
      <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>
      <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>
      <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:rPr><w:b/></w:rPr></w:style>
      <w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/></w:style>
    </w:styles>''')
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", ET.tostring(types, encoding="utf-8", xml_declaration=True))
        archive.writestr("_rels/.rels", ET.tostring(rels, encoding="utf-8", xml_declaration=True))
        archive.writestr("word/document.xml", ET.tostring(document, encoding="utf-8", xml_declaration=True))
        archive.writestr("word/styles.xml", ET.tostring(styles, encoding="utf-8", xml_declaration=True))
        archive.writestr("word/_rels/document.xml.rels", ET.tostring(document_rels, encoding="utf-8", xml_declaration=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=Path("data/processed/domain_coverage_profile.json"))
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--output", type=Path, default=Path("docs/bao_cao_tien_do_xu_ly_data.docx"))
    args = parser.parse_args()
    write_report(args.profile, args.output, args.summary)
    print(args.output)


if __name__ == "__main__":
    main()
