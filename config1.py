# =========================================================================
# CONFIG.PY  –  Cấu hình tập trung cho toàn bộ dự án VBPL Scraper
#
# Khi cần cập nhật cấu hình (đường dẫn file key, timeout, số lần retry...),
# bạn CHỈ CẦN sửa file này mà KHÔNG cần đụng vào bất kỳ file nào khác.
# =========================================================================

# -------------------------------------------------------------------------
# URL GỐC VBPL
# -------------------------------------------------------------------------
BASE_URL = "https://vbpl.vn"

# -------------------------------------------------------------------------
# ĐƯỜNG DẪN FILE TỪ KHOÁ / URL ĐẦU VÀO
# Cấu trúc key.json hỗ trợ:
#   {
#       "search_keywords": {
#           "nhom1": ["từ khóa 1", "từ khóa 2"],
#           "nhom2": ["từ khóa 3"]
#       },
#       "urls": ["https://vbpl.vn/...", "https://vbpl.vn/..."]
#   }
# -------------------------------------------------------------------------
KEY_PATH = r"D:\A_WORK\TGA\chatbot3\scraper_vbpl-main\key4.json"

# -------------------------------------------------------------------------
# THƯ MỤC LƯU KẾT QUẢ (JSON + TXT)
# -------------------------------------------------------------------------
OUTPUT_DIR = "PLa"

# -------------------------------------------------------------------------
# FILE THEO DÕI TIẾN ĐỘ (để Resume khi bị gián đoạn)
# -------------------------------------------------------------------------
PROGRESS_FILE = "progress.json"  # Kept for backward-compat reference only (not used)

# -------------------------------------------------------------------------
# SQLite QUEUE DATABASE – Thay thế progress.json
# Lưu toàn bộ hàng chờ URL và trạng thái cào
# -------------------------------------------------------------------------
DB_PATH = "vbpl_queue.db"

# -------------------------------------------------------------------------
# CẤU HÌNH RETRY
# -------------------------------------------------------------------------
MAX_RETRIES = 3           # Số lần thử lại tối đa khi gặp lỗi
RETRY_DELAY_SECONDS = 10  # Giây chờ giữa các lần retry

# -------------------------------------------------------------------------
# GIỚI HẠN PHÂN TRANG TÌM KIẾM
# -------------------------------------------------------------------------
MAX_SEARCH_PAGES = 10     # Số trang tối đa duyệt khi tìm kiếm theo từ khóa

# -------------------------------------------------------------------------
# CHÍNH SÁCH VĂN BẢN HẾT HIỆU LỰC
# "skip" → bỏ qua hoàn toàn, không cào, đánh dấu 'skipped' trong SQLite
# "save" → vẫn cào và lưu, ghi rõ status hết hiệu lực
# -------------------------------------------------------------------------
EXPIRED_POLICY = "skip"  # Đã chọn: skip theo quyết định của user

# -------------------------------------------------------------------------
# USER AGENTS – Xoay vòng chống bot
# -------------------------------------------------------------------------
USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
        "Gecko/20100101 Firefox/123.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) "
        "Gecko/20100101 Firefox/123.0"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
    ),
]

# -------------------------------------------------------------------------
# THỜI GIAN CHỜ (giây) GIỮA CÁC TÁC VỤ – Để tránh bị VBPL chặn
# -------------------------------------------------------------------------
WAIT_BETWEEN_KEYWORDS = (4, 8)   # random.uniform(min, max)
WAIT_BETWEEN_URLS     = (2, 6)   # random.uniform(min, max)
