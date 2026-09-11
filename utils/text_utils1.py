"""
utils/text_utils.py
===================
Tập hợp các hàm tiện ích xử lý văn bản và metadata
cho dự án VBPL Scraper.

Logic sửa đổi/bổ sung:
- Loại bỏ nội dung của button khỏi Content gốc.
- Nhận diện nhãn sửa đổi/bổ sung ổn định hơn.
- Làm sạch nội dung lấy từ Modal sửa đổi.
- Tạo source_key từ Điều/Khoản/Điểm đã xác định TRƯỚC khi mở Modal.
- Không bao giờ suy ra lại source_key từ nội dung Modal.
"""

import re
import copy
from bs4 import BeautifulSoup


# =========================================================================
# CHUẨN HÓA VĂN BẢN
# =========================================================================

def clean_text(text: str) -> str:
    """
    Chuẩn hóa khoảng trắng.

    Không thay đổi nội dung pháp lý, chỉ loại bỏ xuống dòng /
    khoảng trắng thừa.
    """
    if not text:
        return ""

    text = re.sub(r"\s+", " ", str(text))
    return text.strip()


def text_excluding_buttons(node, sep: str = " ") -> str:
    """
    Lấy text của một HTML node nhưng loại bỏ toàn bộ nội dung
    nằm trong <button>.

    Mục đích:
    - Không đưa nhãn "Điều khoản được sửa đổi, bổ sung"
      vào Content của Điều/Khoản/Điểm.
    - Tránh button sửa đổi làm nhiễu việc parse nội dung pháp lý.
    """
    if node is None:
        return ""

    node_copy = copy.deepcopy(node)

    for button in node_copy.find_all("button"):
        button.decompose()

    return node_copy.get_text(sep, strip=True)


# =========================================================================
# KEY / ID
# =========================================================================

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


def build_amendment_source_key(
    document_key: str,
    article_text: str = "",
    clause_text: str = "",
    item_text: str = "",
) -> str:
    """
    Tạo source_key cho node được gắn nội dung sửa đổi/bổ sung.

    QUAN TRỌNG:
    source_key phải được tạo từ context của BUTTON trên DOM,
    trước khi click mở Modal.

    Nội dung Modal chỉ là Amendment Content và KHÔNG được dùng
    để thay đổi source_key.

    Ví dụ:
        document_key = "123_2026_ND_CP"
        article_text = "Điều 1. ..."
        clause_text  = "18. Khoản 2 Điều 191 ..."

    => 123_2026_ND_CP_Dieu_1_Khoan_18
    """
    source_key = document_key or "unk"

    if article_text:
        article_text = clean_text(article_text)
        match = re.match(
            r"^Điều\s+(\d+[a-zA-Z]?)",
            article_text,
            flags=re.IGNORECASE,
        )
        if match:
            source_key += f"_Dieu_{slugify_key(match.group(1))}"

    if clause_text:
        clause_text = clean_text(clause_text)
        match = re.match(r"^(\d+)\.\s*", clause_text)
        if match:
            source_key += f"_Khoan_{match.group(1)}"

    if item_text:
        item_text = clean_text(item_text)
        match = re.match(r"^([a-zđĐ])\)\s*", item_text)
        if match:
            source_key += f"_Diem_{slugify_key(match.group(1))}"

    return source_key


# =========================================================================
# TRÍCH XUẤT THÔNG TIN TÀI LIỆU
# =========================================================================

def extract_document_number(title: str) -> str:
    """
    Trích xuất số/ký hiệu văn bản từ tiêu đề.
    """
    patterns = [
        r"(\d+/\d{4}/NĐ-CP)",
        r"(\d+/\d{4}/QĐ-TTg)",
        r"(\d+/\d{4}/TT-[A-ZĐ]+)",
        r"(\d+/\d{4}/TTLT-[A-ZĐ-]+)",
        r"(\d+/\d{4}/[A-ZĐ0-9-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, title or "", flags=re.IGNORECASE)
        if match:
            return match.group(1)

    return ""


def extract_document_type(title: str) -> str:
    """Xác định loại văn bản từ tiêu đề."""
    types = [
        "Thông tư liên tịch",
        "Nghị định",
        "Thông tư",
        "Quyết định",
        "Nghị quyết",
        "Luật",
        "Pháp lệnh",
        "Chỉ thị",
        "Thông báo",
        "Công văn",
    ]

    title_lower = (title or "").lower()

    for doc_type in types:
        if doc_type.lower() in title_lower:
            return doc_type

    return ""


def detect_status(page_text: str) -> str:
    """
    Xác định trạng thái hiệu lực của văn bản.

    Thứ tự kiểm tra từ cụ thể đến tổng quát để tránh nhầm:
    "Hết hiệu lực một phần" phải được kiểm tra trước
    "Hết hiệu lực".
    """
    text = (page_text or "").lower()

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
    "amend",
    "amended",
    "modify",
    "modified",
    "sua-doi",
    "sua_doi",
    "suadoi",
    "bo-sung",
    "bo_sung",
    "bosung",
]


def is_amendment_text(text: str) -> bool:
    """
    Kiểm tra một đoạn text có chứa dấu hiệu sửa đổi/bổ sung hay không.
    """
    text = clean_text(text).lower()

    return any(marker in text for marker in AMENDMENT_TEXT_MARKERS)


def has_amendment_label(node) -> bool:
    """
    Kiểm tra một thẻ HTML (Điều/Khoản/Điểm) có nhãn
    sửa đổi/bổ sung hay không.

    Chỉ kiểm tra các sibling kế tiếp trong phạm vi hợp lý.
    Không tính text của chính button nằm bên trong node.
    """
    if node is None:
        return False

    curr = node.find_next_sibling()

    for _ in range(7):
        if not curr:
            break

        classes = curr.get("class", [])

        # Sang Điều mới thì dừng.
        if classes and "prov-article" in classes:
            break

        # Không lấy text của button làm căn cứ nhận diện nội dung node.
        curr_text = clean_text(
            text_excluding_buttons(curr, " ")
        ).lower()

        if is_amendment_text(curr_text):
            return True

        # Kiểm tra class / id / title của element con.
        for element in curr.find_all(True, recursive=True):
            attr_str = (
                " ".join(element.get("class", []))
                + " "
                + str(element.get("id", ""))
                + " "
                + str(element.get("title", ""))
            ).lower()

            if any(
                keyword in attr_str
                for keyword in AMENDMENT_ATTR_KEYWORDS
            ):
                return True

        curr = curr.find_next_sibling()

    return False


# =========================================================================
# LÀM SẠCH NỘI DUNG MODAL SỬA ĐỔI
# =========================================================================

def clean_amendment_content(modal_text: str) -> str:
    """
    Làm sạch nội dung lấy từ Modal sửa đổi/bổ sung.

    Chỉ loại bỏ phần wrapper UI như "Chi tiết thay đổi".
    Không tự phân tích Điều/Khoản/Điểm trong Modal để tạo key.

    Ví dụ:
        "Chi tiết thay đổi Điều 31 ..."

    sẽ trả về phần nội dung sau "Chi tiết thay đổi".
    """
    if not modal_text:
        return ""

    text = clean_text(modal_text)

    text = re.sub(
        r"^.*?Chi tiết thay đổi\s*",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    return clean_text(text)


# =========================================================================
# TÌM NODE THEO KEY
# =========================================================================

def find_article_by_key(articles, key: str):
    """
    Tìm Điều/Khoản/Điểm theo Key trong danh sách articles phẳng.

    Trả về object đầu tiên có Key trùng source_key.
    """
    if not key:
        return None

    for article in articles or []:
        if article.get("Key") == key:
            return article

    return None
