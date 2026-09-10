"""
scraper/parser.py – Bóc tách HTML VBPL thành cấu trúc flat list (Điều, Khoản, Điểm).

Dựa trên logic mới từ upgrade.py:
- Trả về danh sách articles phẳng.
- Điểm được tạo thành các node riêng biệt.
- Áp dụng sửa đổi bằng cách thêm field Amendment và loại bỏ các child node cũ.
"""

import copy
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


def text_excluding_buttons(node, sep: str = " ") -> str:
    """
    Lấy text của một node NHƯNG loại bỏ nội dung nằm trong các thẻ <button>
    (vd: nhãn "Điều khoản được sửa đổi, bổ sung"). Nếu không làm vậy, text của
    nút bấm sẽ bị lẫn thẳng vào Content của Điều/Khoản chứa/đứng cạnh nó.
    """
    if node is None:
        return ""
    node_copy = copy.deepcopy(node)
    for btn in node_copy.find_all("button"):
        btn.decompose()
    return node_copy.get_text(sep, strip=True)


# =========================================================================
# PARSE CẤU TRÚC ĐIỀU, KHOẢN, ĐIỂM (FLAT)
# =========================================================================

def parse_articles(soup: BeautifulSoup, document_key: str, doc_number: str) -> list:
    """
    Tách toàn bộ văn bản theo Điều, Khoản, Điểm thành một danh sách phẳng.
    Gắn Key định danh chi tiết tới cấp độ sâu nhất có thể.
    """
    articles = []
    article_nodes = soup.select(".prov-article")
    for article_node in article_nodes:
        article_text = clean_text(text_excluding_buttons(article_node, " "))
        if not article_text:
            continue
        
        match = re.match(r"Điều\s+(\d+[a-zA-Z]?)\s*[\.:]?\s*(.*)", article_text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
            
        dieu_number = match.group(1)
        dieu_title = clean_text(match.group(2))
        
        article_key = f"{document_key}_Dieu_{slugify_key(dieu_number)}"
        is_modified = has_amendment_label(article_node)

        # Tạo object Điều
        articles.append({
            "Điều": f"Điều {dieu_number}",
            "Title": dieu_title,
            "Content": article_text,
            "Key": article_key,
            "artical": f"Điều {dieu_number}, {doc_number}",
            "Label": "Đã sửa" if is_modified else ""
        })
        
        # Bắt đầu duyệt các siblings để tìm Khoản và Điểm
        curr = article_node.find_next_sibling()
        curr_khoan_key = article_key
        curr_khoan_number = ""

        while curr and "prov-article" not in curr.get("class", []):
            text = clean_text(text_excluding_buttons(curr, " "))
            if not text:
                curr = curr.find_next_sibling()
                continue
                
            cls = curr.get("class", [])
            k_match = re.match(r"^(\d+)\.\s*(.*)", text, flags=re.DOTALL)
            i_match = re.match(r"^([a-zđĐ])\)\s*(.*)", text)

            # Xử lý Khoản
            if "prov-clause" in cls or (k_match and "prov-item" not in cls):
                if k_match:
                    khoan_num = k_match.group(1)
                    curr_khoan_number = khoan_num
                    curr_khoan_key = f"{article_key}_Khoan_{khoan_num}"
                    
                    articles.append({
                        "Khoản": f"Khoản {khoan_num}",
                        "Title": "",
                        "Content": text,
                        "Key": curr_khoan_key,
                        "artical": f"Khoản {khoan_num} Điều {dieu_number}, {doc_number}",
                        "Label": "Đã sửa" if has_amendment_label(curr) else ""
                    })
                else:
                    if articles:
                        articles[-1]["Content"] += "\n" + text
                    
            # Xử lý Điểm
            elif "prov-item" in cls or i_match:
                if i_match:
                    diem_letter = i_match.group(1)
                    diem_key = f"{curr_khoan_key}_Diem_{slugify_key(diem_letter)}"
                    khoan_prefix = f"Khoản {curr_khoan_number} " if curr_khoan_number else ""
                    
                    articles.append({
                        "Điểm": f"Điểm {diem_letter}",
                        "Title": "",
                        "Content": text,
                        "Key": diem_key,
                        "artical": f"Điểm {diem_letter} {khoan_prefix}Điều {dieu_number}, {doc_number}",
                        "Label": "Đã sửa" if has_amendment_label(curr) else ""
                    })
                else:
                    if articles:
                        articles[-1]["Content"] += "\n" + text
                    
            # Nội dung bổ sung / text thường
            else:
                if articles:
                    articles[-1]["Content"] += "\n" + text

            curr = curr.find_next_sibling()

    return articles


# =========================================================================
# MAP NỘI DUNG SỬA ĐỔI VÀ XÂY DỰNG JSON
# =========================================================================

def build_document(
    soup: BeautifulSoup,
    page_text: str,
    doc_info: dict,
    modified_texts: list | None = None,
) -> dict:
    """
    Tạo document JSON phẳng, tích hợp các nội dung sửa đổi vào trường Amendment.
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

    articles = parse_articles(soup, document_key, doc_number)

    document = {
        "title": title,
        "doc_number": doc_number,
        "doc_type": doc_type,
        "keyword": keyword,
        "issued_date": issued_date,
        "effective_date": effective_date,
        "status": status,
        "source_url": source_url,
        "articles": articles,
    }

    if modified_texts:
        matched_source_keys = set()
        for mod in modified_texts:
            if not isinstance(mod, dict):
                continue
            
            s_key = mod.get("source_key") or mod.get("target_key", "")
            m_content = mod.get("content", "")
            if not s_key or not m_content:
                continue
                
            for art in document.get("articles", []):
                if art.get("Key") == s_key:
                    clean_m_content = re.sub(
                        r"^.*?Chi tiết thay đổi\s*", "", m_content,
                        flags=re.IGNORECASE | re.DOTALL,
                    ).strip()
                    
                    existing = art.get("Amendment")
                    if existing:
                        art["Amendment"] = existing + "\n---\n" + clean_m_content
                    else:
                        art["Amendment"] = clean_m_content
                    art["Label"] = "Đã cập nhật sửa đổi"
                    matched_source_keys.add(s_key)
        
        # Xóa các khoản/điểm con cũ thuộc Điều/Khoản đã bị Amendment thay thế
        if matched_source_keys:
            document["articles"] = [
                art for art in document.get("articles", [])
                if not any(
                    art.get("Key", "").startswith(pk + "_")
                    for pk in matched_source_keys
                )
            ]

    return document