"""
utils/db_queue.py – Quản lý hàng chờ URL và trạng thái cào bằng SQLite.

Thay thế hoàn toàn progress.json. Một file DB duy nhất (vbpl_queue.db) lưu:
  - Danh sách URL cần cào (từ search hoặc direct).
  - Trạng thái xử lý từng URL: pending / processing / done / error / skipped.
  - Thông tin phụ: keyword, title, file_path, hiệu_lực, error_msg.

UNIQUE constraint trên cột `url` đảm bảo tự động chống trùng lặp —
  enqueue_url() dùng INSERT OR IGNORE, không bao giờ tạo bản ghi trùng.

Chiến lược Resume sau crash:
  - Khi khởi động, gọi reset_processing() để reset các URL bị stuck
    ở trạng thái 'processing' (do crash giữa chừng) về lại 'pending'.
"""

import sqlite3
import threading
from datetime import datetime, timezone
from contextlib import contextmanager

from config import DB_PATH


# --------------------------------------------------------------------------
# THREAD-SAFETY: Mỗi thread dùng connection riêng qua threading.local()
# --------------------------------------------------------------------------
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Trả về SQLite connection cho thread hiện tại, tạo mới nếu chưa có."""
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # WAL mode cho phép đọc/ghi đồng thời từ nhiều thread
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
    return _local.conn


@contextmanager
def _cursor():
    """Context manager cấp cursor, tự commit hoặc rollback."""
    conn = _get_conn()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# --------------------------------------------------------------------------
# KHỞI TẠO DB
# --------------------------------------------------------------------------

def init_db() -> None:
    """
    Tạo bảng url_queue nếu chưa tồn tại.
    Gọi một lần khi khởi động ứng dụng.
    """
    with _cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS url_queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                url         TEXT    NOT NULL UNIQUE,
                keyword     TEXT    DEFAULT '',
                title       TEXT    DEFAULT '',
                status      TEXT    NOT NULL DEFAULT 'pending',
                hieu_luc    TEXT    DEFAULT '',
                file_path   TEXT    DEFAULT '',
                error_msg   TEXT    DEFAULT '',
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            )
        """)
        # Index để fetch pending nhanh
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_status ON url_queue(status)
        """)


# --------------------------------------------------------------------------
# ENQUEUE
# --------------------------------------------------------------------------

def enqueue_url(url: str, keyword: str = "", title: str = "",
                hieu_luc: str = "") -> bool:
    """
    Thêm một URL vào hàng chờ.
    Nếu URL đã tồn tại (bất kể status), bỏ qua — trả về False.
    Nếu thêm thành công, trả về True.

    Args:
        url:      URL đầy đủ của văn bản.
        keyword:  Từ khóa tìm thấy URL này.
        title:    Tiêu đề từ search API (để hiển thị trên GUI).
        hieu_luc: Trạng thái hiệu lực từ search API ('Còn hiệu lực', ...).
                  Nếu không còn hiệu lực, status sẽ là 'skipped'.
    """
    now = _now()
    # Xác định status ban đầu dựa trên hiệu lực
    initial_status = "pending"
    if hieu_luc and hieu_luc.strip().lower() not in ("còn hiệu lực", ""):
        initial_status = "skipped"

    try:
        with _cursor() as cur:
            cur.execute(
                """
                INSERT OR IGNORE INTO url_queue
                    (url, keyword, title, status, hieu_luc, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (url, keyword, title, initial_status, hieu_luc, now, now),
            )
            return cur.rowcount > 0
    except Exception:
        return False


def enqueue_many(items: list[dict]) -> int:
    """
    Batch enqueue nhiều URL cùng lúc.

    Args:
        items: list of dict với keys: url, keyword, title, hieu_luc.

    Returns:
        Số URL được thêm mới (không tính trùng).
    """
    if not items:
        return 0
    now = _now()
    rows = []
    for item in items:
        url = item.get("url", "").strip()
        if not url:
            continue
        hieu_luc = item.get("hieu_luc", "")
        initial_status = "pending"
        if hieu_luc and hieu_luc.strip().lower() not in ("còn hiệu lực", ""):
            initial_status = "skipped"
        rows.append((
            url,
            item.get("keyword", ""),
            item.get("title", ""),
            initial_status,
            hieu_luc,
            now, now,
        ))

    if not rows:
        return 0

    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT OR IGNORE INTO url_queue
                (url, keyword, title, status, hieu_luc, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        count = cur.rowcount
        conn.commit()
        cur.close()
        return count
    except Exception:
        return 0


# --------------------------------------------------------------------------
# FETCH (lấy URL để worker xử lý)
# --------------------------------------------------------------------------

def fetch_next_pending() -> dict | None:
    """
    Lấy một URL có status='pending', đổi ngay sang 'processing' (atomic).
    Trả về dict {id, url, keyword, title} hoặc None nếu hàng chờ trống.
    """
    conn = _get_conn()
    try:
        # Dùng transaction để tránh race condition giữa 2 thread
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, url, keyword, title FROM url_queue
            WHERE status = 'pending'
            ORDER BY id ASC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if row is None:
            conn.rollback()
            cur.close()
            return None
        now = _now()
        cur.execute(
            "UPDATE url_queue SET status='processing', updated_at=? WHERE id=?",
            (now, row["id"]),
        )
        conn.commit()
        cur.close()
        return dict(row)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return None


# --------------------------------------------------------------------------
# CẬP NHẬT TRẠNG THÁI
# --------------------------------------------------------------------------

def mark_done(url: str, file_path: str = "", hieu_luc: str = "") -> None:
    """Đánh dấu URL đã cào thành công."""
    with _cursor() as cur:
        cur.execute(
            """
            UPDATE url_queue
            SET status='done', file_path=?, hieu_luc=?, updated_at=?
            WHERE url=?
            """,
            (file_path, hieu_luc, _now(), url),
        )


def mark_error(url: str, error_msg: str = "") -> None:
    """Đánh dấu URL cào thất bại (sau tất cả retry)."""
    with _cursor() as cur:
        cur.execute(
            """
            UPDATE url_queue
            SET status='error', error_msg=?, updated_at=?
            WHERE url=?
            """,
            (error_msg[:500], _now(), url),
        )


def mark_skipped(url: str, reason: str = "") -> None:
    """Đánh dấu URL bị bỏ qua (hết hiệu lực hoặc lý do khác)."""
    with _cursor() as cur:
        cur.execute(
            """
            UPDATE url_queue
            SET status='skipped', error_msg=?, updated_at=?
            WHERE url=?
            """,
            (reason[:200], _now(), url),
        )


def reset_processing() -> int:
    """
    Reset tất cả URL đang ở trạng thái 'processing' về 'pending'.
    Gọi khi khởi động lại để xử lý các URL bị stuck do crash.
    Trả về số lượng URL được reset.
    """
    with _cursor() as cur:
        cur.execute(
            """
            UPDATE url_queue SET status='pending', updated_at=?
            WHERE status='processing'
            """,
            (_now(),),
        )
        return cur.rowcount


# --------------------------------------------------------------------------
# KIỂM TRA / TRUY VẤN
# --------------------------------------------------------------------------

def is_done(url: str) -> bool:
    """Kiểm tra nhanh xem URL đã được cào thành công chưa."""
    with _cursor() as cur:
        cur.execute("SELECT 1 FROM url_queue WHERE url=? AND status='done'", (url,))
        return cur.fetchone() is not None


def url_exists(url: str) -> bool:
    """Kiểm tra URL có trong queue chưa (bất kể status)."""
    with _cursor() as cur:
        cur.execute("SELECT 1 FROM url_queue WHERE url=?", (url,))
        return cur.fetchone() is not None


def get_stats() -> dict:
    """
    Trả về thống kê hàng chờ:
        { pending, processing, done, error, skipped, total }
    """
    with _cursor() as cur:
        cur.execute(
            """
            SELECT status, COUNT(*) AS cnt
            FROM url_queue
            GROUP BY status
            """
        )
        rows = cur.fetchall()
    stats = {
        "pending": 0, "processing": 0,
        "done": 0, "error": 0, "skipped": 0, "total": 0,
    }
    for row in rows:
        s = row["status"]
        c = row["cnt"]
        if s in stats:
            stats[s] = c
        stats["total"] += c
    return stats


def count_pending() -> int:
    """Đếm nhanh số URL đang chờ xử lý."""
    with _cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM url_queue WHERE status='pending'")
        return cur.fetchone()[0]


# --------------------------------------------------------------------------
# HELPER
# --------------------------------------------------------------------------

def _now() -> str:
    """Trả về timestamp UTC dạng ISO 8601."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
