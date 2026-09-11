"""
scraper/parser.py – Bóc tách HTML VBPL thành cấu trúc cây JSON Điều → Khoản.

FIX: Lỗi IndexError khi articles rỗng đã được sửa bằng kiểm tra if articles.
FIX: Regex tách Điều đã hỗ trợ cả dạng "Điều 5a", "Điều 12b".
FIX: Nội dung sửa đổi cấp Điểm được map về Khoản cha thay vì bị bỏ qua.
"""

import re
from bs4 import BeautifulSoup

from utils.text_utils import (
    clean_text,
    slugify_key,
    extract_document_number,
    extract_document_type,
    detect_status,
    extract_issued_date,
    extract_effective_date,
    has_amendment_label,
)


# =========================================================================
# PARSE CẤU TRÚC ĐIỀU → KHOẢN
# =========================================================================

def parse_articles(soup: BeautifulSoup, document_key: str, doc_number: str) -> list:
    """
    Bóc tách nội dung văn bản theo cấu trúc phân cấp: Điều → Khoản.

    - Điểm không tạo node riêng, nội dung được ghép vào Khoản tương ứng.
    - Mỗi node Điều chứa danh sách "children" là các Khoản.

    FIX: Hỗ trợ Điều dạng "Điều 5a", "Điều 12b" (thêm [a-zA-Z]? vào Regex).
    FIX: Kiểm tra `if content_tree` trước khi fallback append để tránh IndexError.

    Trả về: content_tree (list)
    """
    content_tree = []
    article_nodes = soup.select(".prov-article")

    for article_node in article_nodes:
        article_text = clean_text(article_node.get_text(" ", strip=True))
        if not article_text:
            continue

        # FIX: Regex mở rộng hỗ trợ "Điều 5a", "Điều 12b"
        match = re.match(
            r"Điều\s+(\d+[a-zA-Z]?)\s*[\.:]?\s*(.*)",
            article_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            continue

        dieu_number = match.group(1)
        dieu_title = clean_text(match.group(2))
        article_key = f"{document_key}_Dieu_{slugify_key(dieu_number)}"

        is_modified = has_amendment_label(article_node)

        dieu_node = {
            "level": "dieu",
            "number": f"Điều {dieu_number}",
            "title": dieu_title,
            "key": article_key,
            "citation": f"Điều {dieu_number}, {doc_number}",
            "label": "Đã sửa" if is_modified else "",
            "children": [],
        }
        content_tree.append(dieu_node)

        # Duyệt sibling để tìm Khoản / Điểm
        curr = article_node.find_next_sibling()
        current_khoan = None

        while curr and "prov-article" not in curr.get("class", []):
            text = clean_text(curr.get_text(" ", strip=True))
            if not text:
                curr = curr.find_next_sibling()
                continue

            cls = curr.get("class", [])
            k_match = re.match(r"^(\d+)\.\s*(.*)", text, flags=re.DOTALL)
            i_match = re.match(r"^([a-zđĐ])\)\s*(.*)", text)

            # Khoản: có class prov-clause HOẶC regex số "N. ..."
            if "prov-clause" in cls or (k_match and "prov-item" not in cls):
                if k_match:
                    khoan_num = k_match.group(1)
                    khoan_key = f"{article_key}_Khoan_{khoan_num}"
                    current_khoan = {
                        "level": "khoan",
                        "number": f"Khoản {khoan_num}",
                        "content": text,
                        "key": khoan_key,
                        "citation": f"Khoản {khoan_num} Điều {dieu_number}, {doc_number}",
                        "label": "Đã sửa" if has_amendment_label(curr) else "",
                    }
                    dieu_node["children"].append(current_khoan)
                else:
                    # Fallback: prov-clause nhưng không có số Khoản rõ ràng
                    if current_khoan is not None:
                        current_khoan["content"] = (
                            current_khoan.get("content", "") + "\n" + text
                        ).strip()
                    elif content_tree:  # FIX: tránh IndexError
                        dieu_node["title"] = (
                            dieu_node.get("title", "") + "\n" + text
                        ).strip()

            # Điểm: có class prov-item HOẶC regex chữ "x) ..."
            # Không tạo node riêng – ghép vào Khoản hiện tại để giữ ngữ cảnh
            elif "prov-item" in cls or i_match:
                if current_khoan is not None:
                    current_khoan["content"] = (
                        current_khoan.get("content", "") + "\n" + text
                    ).strip()
                elif content_tree:  # FIX: tránh IndexError
                    dieu_node["title"] = (
                        dieu_node.get("title", "") + "\n" + text
                    ).strip()

            # Nội dung bổ sung không có class / regex rõ ràng
            else:
                if current_khoan is not None:
                    current_khoan["content"] = (
                        current_khoan.get("content", "") + "\n" + text
                    ).strip()
                elif content_tree:  # FIX: tránh IndexError
                    dieu_node["title"] = (
                        dieu_node.get("title", "") + "\n" + text
                    ).strip()

            curr = curr.find_next_sibling()

    return content_tree


# =========================================================================
# MAP NỘI DUNG SỬA ĐỔI TỪ MODAL VÀO CÂY
# =========================================================================

def find_node(nodes: list, target_key: str) -> dict | None:
    """
    Tìm kiếm đệ quy một node trong content_tree theo key.
    """
    for node in nodes:
        if node.get("key") == target_key:
            return node
        found = find_node(node.get("children", []), target_key)
        if found:
            return found
    return None


def apply_modal_updates(content_tree: list, modified_texts: list) -> None:
    """
    Cập nhật nội dung mới và bổ sung nội dung cũ từ Modal sửa đổi.

    FIX: Nếu target_key trỏ đến level Điểm (_Diem_x) nhưng cây không có node
         riêng cho Điểm, hàm sẽ tự động tìm Khoản cha và cập nhật vào đó.

    Thực hiện in-place, không có giá trị trả về.
    """
    for mod in modified_texts:
        if not isinstance(mod, dict):
            continue
        target_key: str = mod.get("target_key", "")
        raw_content: str = mod.get("content", "")
        if not target_key or not raw_content:
            continue

        # Lọc bỏ phần metadata "Chi tiết thay đổi ..." ở đầu nội dung Modal
        clean_content = re.sub(
            r"^.*?Chi tiết thay đổi\s*", "", raw_content,
            flags=re.IGNORECASE | re.DOTALL,
        ).strip()

        is_old_content = target_key.endswith("_cu")
        lookup_key = target_key[:-3] if is_old_content else target_key

        # Tìm chính xác node trong cây
        node = find_node(content_tree, lookup_key)

        if node is None:
            # FIX: Nếu key có dạng _Diem_x (không có node riêng),
            # cắt phần _Diem_x và tìm Khoản cha để cập nhật vào đó.
            parent_key = re.sub(r"_Diem_[^_]+$", "", lookup_key)
            if parent_key != lookup_key:
                node = find_node(content_tree, parent_key)

        if node is None:
            continue

        if node.get("level") == "khoan":
            if is_old_content:
                node["old_content"] = clean_content
            else:
                node["content"] = clean_content
                node["label"] = "Đã cập nhật"
        elif node.get("level") == "dieu":
            if is_old_content:
                node["old_content"] = clean_content
            else:
                node["title"] = clean_content
                node["label"] = "Đã cập nhật"


# =========================================================================
# XÂY DỰNG DOCUMENT JSON HOÀN CHỈNH
# =========================================================================

def build_document(
    soup: BeautifulSoup,
    page_text: str,
    doc_info: dict,
    modified_texts: list | None = None,
) -> dict:
    """
    Tổng hợp tất cả thông tin thành một document JSON hoàn chỉnh.

    doc_info: { "title", "keyword", "status", "issued_date",
                "effective_date", "source_url" }
    """
    title = doc_info.get("title", "")
    keyword = doc_info.get("keyword", "")
    status = doc_info.get("status", "") or detect_status(page_text)
    issued_date = doc_info.get("issued_date", "") or extract_issued_date(page_text)
    effective_date = doc_info.get("effective_date", "") or extract_effective_date(page_text)
    source_url = doc_info.get("source_url", "")

    doc_number = extract_document_number(title) or title
    doc_type = extract_document_type(title)
    document_key = slugify_key(doc_number)

    content_tree = parse_articles(soup, document_key, doc_number)

    if modified_texts:
        apply_modal_updates(content_tree, modified_texts)

    return {
        "title": title,
        "doc_number": doc_number,
        "doc_type": doc_type,
        "keyword": keyword,
        "issued_date": issued_date,
        "effective_date": effective_date,
        "status": status,
        "source_url": source_url,
        "content_tree": content_tree,
    }
