import os
import re
import json
import shutil
from pathlib import Path


# ============================================================
# CẤU HÌNH
# ============================================================

INPUT_DIR = Path("PL")
OUTPUT_DIR = Path("PL_tong")

JSON_OUTPUT = OUTPUT_DIR / "PL_tong.json"
TEXT_OUTPUT = OUTPUT_DIR / "PL_tong.txt"
EMPTY_OUTPUT = OUTPUT_DIR / "nghi_dinh_trong.txt"


# ============================================================
# HÀM CHUẨN HÓA TEXT
# ============================================================

def clean_text(text):
    """
    Chuẩn hóa khoảng trắng nhưng vẫn giữ cấu trúc dòng.
    """
    if text is None:
        return ""

    text = str(text)

    # Chuẩn hóa xuống dòng
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Loại bỏ khoảng trắng cuối dòng
    lines = [line.rstrip() for line in text.split("\n")]

    # Loại bỏ các dòng trống liên tiếp
    result = []
    previous_empty = False

    for line in lines:
        line = line.strip()

        if not line:
            if not previous_empty:
                result.append("")
            previous_empty = True
        else:
            result.append(line)
            previous_empty = False

    return "\n".join(result).strip()


# ============================================================
# XÁC ĐỊNH ĐIỀU
# ============================================================

def is_article(node):
    """
    Kiểm tra node có phải Điều hay không.
    """
    if not isinstance(node, dict):
        return False

    level = str(node.get("level", "")).lower().strip()
    number = str(node.get("number", "")).strip()

    if level == "dieu":
        return True

    if re.match(r"^Điều\s+\d+", number, re.IGNORECASE):
        return True

    return False


# ============================================================
# XÁC ĐỊNH KHOẢN
# ============================================================

def is_clause(node):
    """
    Kiểm tra node có phải Khoản hay không.
    """
    if not isinstance(node, dict):
        return False

    level = str(node.get("level", "")).lower().strip()
    number = str(node.get("number", "")).strip()

    if level == "khoan":
        return True

    if re.match(r"^Khoản\s+\d+", number, re.IGNORECASE):
        return True

    return False


# ============================================================
# XÁC ĐỊNH ĐIỂM
# ============================================================

def is_point(node):
    """
    Kiểm tra node có phải điểm a/b/c... hay không.
    """
    if not isinstance(node, dict):
        return False

    level = str(node.get("level", "")).lower().strip()
    number = str(node.get("number", "")).strip()

    if level in {
        "diem",
        "point",
        "muc"
    }:
        return True

    if re.match(r"^[a-zđ]\)?\.?$", number, re.IGNORECASE):
        return True

    if re.match(r"^[a-zđ]\s*[\)\.]", number, re.IGNORECASE):
        return True

    return False


# ============================================================
# LẤY NỘI DUNG NODE
# ============================================================

def get_node_content(node):
    """
    Lấy nội dung của node.
    """
    content = node.get("content", "")

    if content:
        return clean_text(content)

    title = node.get("title", "")

    if title:
        return clean_text(title)

    return ""


# ============================================================
# CHUẨN HÓA SỐ ĐIỀU
# ============================================================

def normalize_article_number(number):
    """
    Ví dụ:
    Điều 1
    điều 1
    Điều 01
    """
    number = clean_text(number)

    if not number:
        return ""

    match = re.search(r"Điều\s+(\d+[A-Za-z]?)", number, re.IGNORECASE)

    if match:
        return f"Điều {match.group(1)}"

    return number


# ============================================================
# CHUẨN HÓA SỐ KHOẢN
# ============================================================

def normalize_clause_number(number):
    number = clean_text(number)

    if not number:
        return ""

    match = re.search(r"Khoản\s+(\d+)", number, re.IGNORECASE)

    if match:
        return f"Khoản {match.group(1)}"

    # Trường hợp chỉ có "1", "2", "3"
    if re.match(r"^\d+$", number):
        return f"Khoản {number}"

    return number


# ============================================================
# CHUẨN HÓA ĐIỂM
# ============================================================

def normalize_point_number(number):
    number = clean_text(number)

    if not number:
        return ""

    # a, a), a., a )
    match = re.match(r"^([a-zđ])\s*[\)\.]?$", number, re.IGNORECASE)

    if match:
        return f"{match.group(1)})"

    match = re.match(r"^([a-zđ])\s*[\)\.]\s*", number, re.IGNORECASE)

    if match:
        return f"{match.group(1)})"

    return number


# ============================================================
# RENDER NODE
# ============================================================

def render_node(node, level=0):
    """
    Chuyển content_tree thành text có phân cấp.

    Điều:
    Khoản:
    Điểm:
    """

    if not isinstance(node, dict):
        return []

    lines = []

    node_level = str(node.get("level", "")).lower().strip()
    number = str(node.get("number", "")).strip()
    title = clean_text(node.get("title", ""))
    content = clean_text(node.get("content", ""))

    # --------------------------------------------------------
    # ĐIỀU
    # --------------------------------------------------------

    if node_level == "dieu" or re.match(
        r"^Điều\s+\d+",
        number,
        re.IGNORECASE
    ):

        article_number = normalize_article_number(number)

        if title:
            lines.append(
                f"{article_number}. {title}"
            )
        else:
            lines.append(article_number)

        children = node.get("children", [])

        for child in children:
            child_lines = render_node(child, 1)
            lines.extend(child_lines)

        return lines

    # --------------------------------------------------------
    # KHOẢN
    # --------------------------------------------------------

    if node_level == "khoan" or re.match(
        r"^Khoản\s+\d+",
        number,
        re.IGNORECASE
    ):

        clause_number = normalize_clause_number(number)

        text = content or title

        if text:
            lines.append(
                f"  {clause_number}. {text}"
            )
        else:
            lines.append(
                f"  {clause_number}."
            )

        children = node.get("children", [])

        for child in children:
            child_lines = render_node(child, 2)
            lines.extend(child_lines)

        return lines

    # --------------------------------------------------------
    # ĐIỂM
    # --------------------------------------------------------

    if (
        node_level in {"diem", "point", "muc"}
        or re.match(r"^[a-zđ]\s*[\)\.]?$", number, re.IGNORECASE)
        or re.match(r"^[a-zđ]\s*[\)\.]", number, re.IGNORECASE)
    ):

        point_number = normalize_point_number(number)

        text = content or title

        if text:
            lines.append(
                f"    {point_number} {text}"
            )
        else:
            lines.append(
                f"    {point_number}"
            )

        children = node.get("children", [])

        for child in children:
            child_lines = render_node(child, 3)
            lines.extend(child_lines)

        return lines

    # --------------------------------------------------------
    # NODE KHÁC
    # --------------------------------------------------------

    text = content or title

    if text:
        indent = "  " * level
        lines.append(indent + text)

    children = node.get("children", [])

    for child in children:
        lines.extend(
            render_node(child, level)
        )

    return lines


# ============================================================
# KIỂM TRA JSON CÓ NỘI DUNG PHÁP LUẬT KHÔNG
# ============================================================

def json_has_legal_content(data):
    """
    Xác định JSON có Điều/Khoản hay không.
    """

    if not isinstance(data, dict):
        return False

    content_tree = data.get("content_tree")

    if not isinstance(content_tree, list):
        return False

    if not content_tree:
        return False

    def recursive_check(nodes):
        for node in nodes:

            if not isinstance(node, dict):
                continue

            if is_article(node) or is_clause(node):
                return True

            children = node.get("children", [])

            if isinstance(children, list):
                if recursive_check(children):
                    return True

        return False

    return recursive_check(content_tree)


# ============================================================
# JSON → TEXT
# ============================================================

def json_to_text(data):
    """
    Chuyển 1 JSON văn bản thành định dạng TXT chuẩn.
    """

    title = clean_text(data.get("title", ""))
    doc_number = clean_text(data.get("doc_number", ""))
    doc_type = clean_text(data.get("doc_type", ""))
    keyword = clean_text(data.get("keyword", ""))
    issued_date = clean_text(data.get("issued_date", ""))
    effective_date = clean_text(data.get("effective_date", ""))
    status = clean_text(data.get("status", ""))
    source_url = clean_text(data.get("source_url", ""))

    lines = []

    # --------------------------------------------------------
    # TÊN VĂN BẢN
    # --------------------------------------------------------

    if title:
        lines.append(title)

    # --------------------------------------------------------
    # THÔNG TIN
    # --------------------------------------------------------

    if doc_number:
        lines.append(f"Số hiệu: {doc_number}")

    date_value = issued_date if issued_date else ""

    date_line = f"Ngày: {date_value}"

    if status:
        date_line += f"  |  Trạng thái: {status}"

    lines.append(date_line)

    if source_url:
        lines.append(f"Nguồn: {source_url}")

    lines.append("-" * 60)
    lines.append("")

    # --------------------------------------------------------
    # CONTENT TREE
    # --------------------------------------------------------

    content_tree = data.get("content_tree", [])

    if isinstance(content_tree, list):

        for node in content_tree:

            node_lines = render_node(node)

            if node_lines:
                lines.extend(node_lines)
                lines.append("")

    return clean_text("\n".join(lines))


# ============================================================
# PHÂN TÍCH FILE TXT
# ============================================================

def text_has_legal_content(text):
    """
    Kiểm tra TXT có Điều/Khoản hay không.
    """

    if not text:
        return False

    # Điều 1 / Điều 2...
    if re.search(
        r"(?m)^\s*Điều\s+\d+",
        text,
        re.IGNORECASE
    ):
        return True

    # Khoản 1
    if re.search(
        r"(?m)^\s*Khoản\s+\d+",
        text,
        re.IGNORECASE
    ):
        return True

    # Dạng "1. ..." thường xuất hiện dưới Điều
    if re.search(
        r"(?m)^\s{0,6}\d+\.\s+\S+",
        text
    ):
        return True

    return False


# ============================================================
# CHUẨN HÓA FILE TXT
# ============================================================

def normalize_text_file(text):
    """
    Chuẩn hóa file TXT về format thống nhất.
    """

    text = clean_text(text)

    if not text:
        return ""

    # --------------------------------------------------------
    # Chuẩn hóa dòng phân cách
    # --------------------------------------------------------

    text = re.sub(
        r"^[=\-─━]{5,}$",
        "-" * 60,
        text,
        flags=re.MULTILINE
    )

    # --------------------------------------------------------
    # Chuẩn hóa Điều
    # --------------------------------------------------------

    text = re.sub(
        r"(?m)^\s*Điều\s+(\d+)\s*[–—\-:]\s*",
        r"Điều \1. ",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"(?m)^\s*Điều\s+(\d+)\s*$",
        r"Điều \1.",
        text,
        flags=re.IGNORECASE
    )

    # --------------------------------------------------------
    # Chuẩn hóa Khoản
    # --------------------------------------------------------

    text = re.sub(
        r"(?m)^\s*Khoản\s+(\d+)\s*[.:]?\s*$",
        r"  Khoản \1.",
        text,
        flags=re.IGNORECASE
    )

    # --------------------------------------------------------
    # Chuẩn hóa điểm
    # --------------------------------------------------------

    text = re.sub(
        r"(?m)^\s*([a-zđ])\s*[\)\.]\s+",
        r"    \1) ",
        text,
        flags=re.IGNORECASE
    )

    return clean_text(text)


# ============================================================
# ĐỌC JSON
# ============================================================

def load_json_file(path):
    """
    Đọc JSON UTF-8.
    """

    try:
        with open(
            path,
            "r",
            encoding="utf-8-sig"
        ) as f:
            return json.load(f)

    except Exception as e:

        print(
            f"[LỖI JSON] {path.name}: {e}"
        )

        return None


# ============================================================
# ĐỌC TEXT
# ============================================================

def load_text_file(path):
    """
    Đọc TXT, ưu tiên UTF-8.
    """

    encodings = [
        "utf-8-sig",
        "utf-8",
        "cp1258"
    ]

    for encoding in encodings:

        try:

            with open(
                path,
                "r",
                encoding=encoding
            ) as f:

                return f.read()

        except UnicodeDecodeError:
            continue

        except Exception as e:

            print(
                f"[LỖI TXT] {path.name}: {e}"
            )

            return ""

    print(
        f"[LỖI ENCODING] Không đọc được: {path.name}"
    )

    return ""


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("CÔNG CỤ GỘP DỮ LIỆU PHÁP LUẬT")
    print("=" * 70)

    # --------------------------------------------------------
    # Kiểm tra thư mục PL
    # --------------------------------------------------------

    if not INPUT_DIR.exists():

        print(
            f"[LỖI] Không tìm thấy thư mục: {INPUT_DIR}"
        )

        return

    # --------------------------------------------------------
    # Tạo thư mục PL_tong
    # --------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Xóa file tổng cũ
    # --------------------------------------------------------

    for file_path in [
        JSON_OUTPUT,
        TEXT_OUTPUT,
        EMPTY_OUTPUT
    ]:

        if file_path.exists():

            try:
                file_path.unlink()
            except Exception:
                pass

    # --------------------------------------------------------
    # DANH SÁCH
    # --------------------------------------------------------

    json_documents = []
    text_documents = []

    empty_files = []

    json_count = 0
    text_count = 0

    # ========================================================
    # XỬ LÝ JSON
    # ========================================================

    json_files = sorted(
        INPUT_DIR.glob("*.json")
    )

    print(
        f"\nTìm thấy {len(json_files)} file JSON."
    )

    for index, path in enumerate(
        json_files,
        start=1
    ):

        print(
            f"[JSON {index}/{len(json_files)}] "
            f"{path.name}"
        )

        data = load_json_file(path)

        if data is None:
            continue

        # ----------------------------------------------------
        # Kiểm tra nội dung
        # ----------------------------------------------------

        if not json_has_legal_content(data):

            empty_files.append(
                path.name
            )

            print(
                "    -> BỎ QUA: không có Điều/Khoản"
            )

            continue

        # ----------------------------------------------------
        # Thêm vào JSON tổng
        # ----------------------------------------------------

        json_documents.append(data)

        # ----------------------------------------------------
        # Chuyển JSON → TXT
        # ----------------------------------------------------

        formatted_text = json_to_text(data)

        if formatted_text:

            text_documents.append(
                formatted_text
            )

        json_count += 1

    # ========================================================
    # XỬ LÝ TXT
    # ========================================================

    text_files = sorted(
        INPUT_DIR.glob("*.txt")
    )

    print(
        f"\nTìm thấy {len(text_files)} file TXT."
    )

    for index, path in enumerate(
        text_files,
        start=1
    ):

        print(
            f"[TXT {index}/{len(text_files)}] "
            f"{path.name}"
        )

        raw_text = load_text_file(path)

        if not raw_text.strip():

            empty_files.append(
                path.name
            )

            print(
                "    -> BỎ QUA: file rỗng"
            )

            continue

        # ----------------------------------------------------
        # Kiểm tra Điều/Khoản
        # ----------------------------------------------------

        if not text_has_legal_content(raw_text):

            empty_files.append(
                path.name
            )

            print(
                "    -> BỎ QUA: không có Điều/Khoản"
            )

            continue

        # ----------------------------------------------------
        # Chuẩn hóa
        # ----------------------------------------------------

        formatted_text = normalize_text_file(
            raw_text
        )

        if formatted_text:

            text_documents.append(
                formatted_text
            )

            text_count += 1

    # ========================================================
    # GHI JSON TỔNG
    # ========================================================

    print("\nĐang tạo JSON tổng...")

    with open(
        JSON_OUTPUT,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            json_documents,
            f,
            ensure_ascii=False,
            indent=2
        )

    # ========================================================
    # GHI TEXT TỔNG
    # ========================================================

    print("Đang tạo TXT tổng...")

    with open(
        TEXT_OUTPUT,
        "w",
        encoding="utf-8"
    ) as f:

        for index, document in enumerate(
            text_documents
        ):

            f.write(
                document.strip()
            )

            f.write(
                "\n"
            )

            # Phân cách giữa các văn bản
            if index < len(text_documents) - 1:

                f.write(
                    "\n"
                    + "=" * 70
                    + "\n\n"
                )

    # ========================================================
    # GHI DANH SÁCH FILE TRỐNG
    # ========================================================

    print(
        "Đang tạo danh sách văn bản không có Điều/Khoản..."
    )

    with open(
        EMPTY_OUTPUT,
        "w",
        encoding="utf-8"
    ) as f:

        if empty_files:

            f.write(
                "DANH SÁCH FILE KHÔNG CÓ NỘI DUNG ĐIỀU/KHOẢN\n"
            )

            f.write(
                "=" * 60
                + "\n\n"
            )

            for index, filename in enumerate(
                empty_files,
                start=1
            ):

                f.write(
                    f"{index}. {filename}\n"
                )

        else:

            f.write(
                "Không có file nào bị bỏ qua.\n"
            )

    # ========================================================
    # THỐNG KÊ
    # ========================================================

    print("\n" + "=" * 70)
    print("HOÀN THÀNH")
    print("=" * 70)

    print(
        f"JSON hợp lệ      : {json_count}"
    )

    print(
        f"TXT hợp lệ       : {text_count}"
    )

    print(
        f"File bỏ qua      : {len(empty_files)}"
    )

    print(
        f"\nJSON tổng: {JSON_OUTPUT}"
    )

    print(
        f"TXT tổng : {TEXT_OUTPUT}"
    )

    print(
        f"File trống: {EMPTY_OUTPUT}"
    )

    print("=" * 70)


# ============================================================
# CHẠY CHƯƠNG TRÌNH
# ============================================================

if __name__ == "__main__":
    main()