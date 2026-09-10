"""
utils/storage.py – Quản lý lưu trữ file (JSON, TXT)

Chứa toàn bộ logic đọc/ghi file output của dự án.
Khi cần thay đổi định dạng file output, chỉ cần sửa file này.

NOTE: Chức năng Resume/Progress đã chuyển hoàn toàn sang utils/db_queue.py (SQLite).
      Không còn sử dụng progress.json.
"""

import json
import os

from config import OUTPUT_DIR
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
            f.write(f"{dieu.get('number', '')} – {dieu.get('title', '')}")
            if dieu.get("label"):
                f.write(f"  [{dieu['label']}]")
            f.write("\n\n")

            for khoan in dieu.get("children", []):
                f.write(f"  {khoan.get('number', '')}.\n")
                f.write(f"  {khoan.get('content', '')}\n\n")

    return json_path


# =========================================================================
# PROGRESS – ĐÃ CHUYỂN SANG utils/db_queue.py (SQLite)
# =========================================================================
# Các hàm load_progress(), save_progress(), reset_progress() đã bị xóa.
# Thay vào đó, hãy dùng utils.db_queue:
#   - db_queue.init_db()           → khởi tạo DB khi app start
#   - db_queue.enqueue_url(url)    → thêm URL vào hàng chờ
#   - db_queue.mark_done(url)      → đánh dấu đã cào xong
#   - db_queue.is_done(url)        → kiểm tra đã cào chưa
#   - db_queue.get_stats()         → thống kê pending/done/error
