"""
utils/text_utils.py – Tập hợp các hàm tiện ích xử lý văn bản / trích xuất metadata
cho toàn bộ dự án VBPL Scraper.

Nếu cần thêm mẫu Regex hoặc logic xử lý văn bản mới, chỉ cần sửa file này.
"""

import re
from bs4 import BeautifulSoup


# =========================================================================
# CHUẨN HÓA VĂN BẢN
# =========================================================================

def clean_text(text: str) -> str:
    """
    Chuẩn hóa khoảng trắng.
    Không thay đổi nội dung pháp lý, chỉ loại bỏ xuống dòng / khoảng trắng thừa.
    """
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def slugify_key(text: str) -> str:
    """
    Chuyển text thành Key an toàn cho tên file và định danh node.
    """
    if not text:
        return "unk"
    text = str(text)
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s-]+", "_", text)
    return text.strip("_") or "unk"


# =========================================================================
# TRÍCH XUẤT THÔNG TIN TÀI LIỆU
# =========================================================================

def extract_document_number(title: str) -> str:
    """
    Trích xuất số/ký hiệu văn bản từ tiêu đề.
    Ví dụ:
        "Nghị định số 100/2024/NĐ-CP"  ->  "100/2024/NĐ-CP"
        "Thông tư 54/2026/TT-BTNMT"    ->  "54/2026/TT-BTNMT"
    """
    patterns = [
        r"(\d+/\d{4}/NĐ-CP)",
        r"(\d+/\d{4}/QĐ-TTg)",
        r"(\d+/\d{4}/TT-[A-ZĐ]+)",
        r"(\d+/\d{4}/TTLT-[A-ZĐ-]+)",
        r"(\d+/\d{4}/[A-ZĐ0-9-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, title, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def extract_document_type(title: str) -> str:
    """Xác định loại văn bản từ tiêu đề."""
    types = [
        "Thông tư liên tịch", "Nghị định", "Thông tư",
        "Quyết định", "Nghị quyết", "Luật",
        "Pháp lệnh", "Chỉ thị", "Thông báo", "Công văn",
    ]
    title_lower = (title or "").lower()
    for doc_type in types:
        if doc_type.lower() in title_lower:
            return doc_type
    return ""


def detect_status(page_text: str) -> str:
    """
    Xác định trạng thái hiệu lực của văn bản.
    Thứ tự kiểm tra từ cụ thể đến tổng quát để tránh nhầm lẫn.
    """
    text = page_text.lower()
    if "còn hiệu lực" in text:
        return "Còn hiệu lực"
    if "hết hiệu lực một phần" in text:
        return "Hết hiệu lực một phần"
    if "hết hiệu lực" in text:
        return "Hết hiệu lực"
    if "chưa có hiệu lực" in text:
        return "Chưa có hiệu lực"
    return "Khác"


def extract_issued_date(page_text: str) -> str:
    """
    Lấy Ngày ban hành, không nhầm với Ngày có hiệu lực.
    """
    if not page_text:
        return ""
    patterns = [
        r"Ngày\s+ban\s+hành\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{4})",
        r"Ngày\s+ban\s+hành\s*\n\s*(\d{1,2}/\d{1,2}/\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, page_text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def extract_effective_date(page_text: str) -> str:
    """
    Lấy Ngày có hiệu lực của văn bản.
    """
    if not page_text:
        return ""
    patterns = [
        r"Ngày\s+có\s+hiệu\s+lực\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{4})",
        r"Ngày\s+áp\s+dụng\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, page_text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


# =========================================================================
# NHẬN DIỆN NHÃN SỬA ĐỔI / BỔ SUNG
# =========================================================================

AMENDMENT_TEXT_MARKERS = [
    "điều khoản được sửa đổi, bổ sung",
    "điều khoản được sửa đổi",
    "được sửa đổi, bổ sung",
    "được sửa đổi bởi",
    "sửa đổi, bổ sung bởi",
    "sửa đổi tại",
    "bổ sung tại",
]

AMENDMENT_ATTR_KEYWORDS = [
    "amend", "amended", "modify", "modified",
    "sua-doi", "sua_doi", "suadoi",
    "bo-sung", "bo_sung", "bosung",
]


def has_amendment_label(node) -> bool:
    """
    Kiểm tra một thẻ HTML (Điều/Khoản/Điểm) có nhãn sửa đổi/bổ sung không
    bằng cách duyệt các thẻ anh em (siblings) kế tiếp.
    """
    curr = node.find_next_sibling()
    for _ in range(7):
        if not curr:
            break
        classes = curr.get("class", [])
        if classes and "prov-article" in classes:
            break

        curr_text = clean_text(curr.get_text(" ", strip=True)).lower()
        for marker in AMENDMENT_TEXT_MARKERS:
            if marker in curr_text:
                return True

        for element in curr.find_all(True, recursive=True):
            attr_str = (
                " ".join(element.get("class", [])) + " "
                + str(element.get("id", "")) + " "
                + str(element.get("title", ""))
            ).lower()
            for kw in AMENDMENT_ATTR_KEYWORDS:
                if kw in attr_str:
                    return True

        curr = curr.find_next_sibling()
    return False
