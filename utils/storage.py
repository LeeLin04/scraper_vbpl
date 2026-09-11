"""
utils/storage.py – Quản lý lưu trữ file (JSON, TXT) và tiến độ (progress.json)

Chứa toàn bộ logic đọc/ghi đĩa của dự án.
Khi cần thay đổi định dạng file output hoặc cơ chế Resume, chỉ cần sửa file này.
"""

import json
import os

from config import OUTPUT_DIR, PROGRESS_FILE
from utils.text_utils import slugify_key


# =========================================================================
# LƯU VĂN BẢN (JSON + TXT)
# =========================================================================

def save_document(document: dict, output_dir: str = OUTPUT_DIR) -> str:
    """
    Lưu một văn bản thành file JSON và file TXT tóm tắt.
    Trả về đường dẫn file JSON đã lưu.

    Cấu trúc file output:
        PL/
            100_2024_ND_CP.json
            100_2024_ND_CP.txt
    """
    os.makedirs(output_dir, exist_ok=True)

    doc_number = document.get("doc_number", "")
    document_key = slugify_key(doc_number)

    # --- JSON ---
    json_path = os.path.join(output_dir, f"{document_key}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(document, f, ensure_ascii=False, indent=2)

    # --- TXT (dễ đọc) ---
    txt_path = os.path.join(output_dir, f"{document_key}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"TÊN VĂN BẢN : {document.get('title', '')}\n")
        f.write(f"SỐ VĂN BẢN  : {document.get('doc_number', '')}\n")
        f.write(f"LOẠI VĂN BẢN: {document.get('doc_type', '')}\n")
        f.write(f"TỪ KHÓA     : {document.get('keyword', '')}\n")
        f.write(f"TRẠNG THÁI  : {document.get('status', '')}\n")
        f.write(f"NGÀY BAN HÀNH: {document.get('issued_date', '')}\n")
        f.write(f"NGÀY HIỆU LỰC: {document.get('effective_date', '')}\n")
        f.write(f"URL         : {document.get('source_url', '')}\n")
        f.write("=" * 80 + "\n\n")

        for dieu in document.get("content_tree", []):
            f.write(f"{'─'*60}\n")
            old_title = dieu.get("old_content", "")
            f.write(f"{dieu.get('number', '')} – ")
            if old_title:
                f.write(f"NỘI DUNG CŨ:\n{old_title}\nNỘI DUNG SAU SỬA ĐỔI:\n")
            f.write(dieu.get("title", ""))
            if dieu.get("label"):
                f.write(f"  [{dieu['label']}]")
            f.write("\n\n")

            for khoan in dieu.get("children", []):
                f.write(f"  {khoan.get('number', '')}.\n")
                old_content = khoan.get("old_content", "")
                if old_content:
                    f.write(f"  NỘI DUNG CŨ:\n  {old_content}\n\n")
                    f.write("  NỘI DUNG SAU SỬA ĐỔI:\n")
                f.write(f"  {khoan.get('content', '')}\n\n")

    return json_path


# =========================================================================
# QUẢN LÝ TIẾN ĐỘ (RESUME)
# =========================================================================

def load_progress() -> list:
    """
    Đọc danh sách các URL đã cào thành công từ file progress.json.
    Giúp tiếp tục chạy (Resume) mà không cào lại các URL cũ.
    """
    if not os.path.exists(PROGRESS_FILE):
        return []
    try:
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("completed_urls", [])
    except (json.JSONDecodeError, OSError):
        return []


def save_progress(url: str) -> None:
    """
    Ghi nhận một URL đã cào thành công vào file progress.json.
    """
    completed = load_progress()
    if url not in completed:
        completed.append(url)
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump({"completed_urls": completed}, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def reset_progress() -> None:
    """
    Xóa file progress.json để bắt đầu lại từ đầu.
    """
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
