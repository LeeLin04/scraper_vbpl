"""
scraper/api_client.py – Tìm kiếm văn bản trên VBPL bằng cách bắt API Next.js.

Xử lý toàn bộ logic tương tác với giao diện tìm kiếm (Ant Design) và
parse dữ liệu streaming JSON trả về từ server VBPL.

FIX: Lỗi bỏ sót dòng index 2 chữ số (10:, 11:...) đã được sửa bằng Regex.
FIX: Lỗi chồng chất event listener (Listener Stacking) đã được sửa bằng remove_listener.
NEW: search_documents() giờ trả về field `hieu_luc` (từ effStatus) cho mỗi văn bản.
"""

import json
import re
import time
import random

from config import BASE_URL, MAX_SEARCH_PAGES
from utils.text_utils import clean_text


# Ánh xạ tên hiệu lực trong API sang giá trị chuẩn hóa
_EFF_STATUS_MAP = {
    "còn hiệu lực":             "Còn hiệu lực",
    "hết hiệu lực một phần":   "Hết hiệu lực một phần",
    "hết hiệu lực":           "Hết hiệu lực",
    "chưa có hiệu lực":       "Chưa có hiệu lực",
    "không xác định":          "Không xác định",
}


def _normalize_hieu_luc(raw: str) -> str:
    """Chuẩn hóa giá trị hiệu lực từ API, giữ nguyên nếu không khớp."""
    if not raw:
        return ""
    return _EFF_STATUS_MAP.get(raw.strip().lower(), raw.strip())


def search_documents(page, keyword: str, log_fn=None) -> list[dict]:
    """
    Tìm kiếm văn bản trên VBPL theo từ khóa:
        1. Mở trang chủ VBPL.
        2. Nhập từ khóa vào ô tìm kiếm.
        3. Mở Tìm kiếm nâng cao → lọc "Còn hiệu lực".
        4. Bấm Tìm kiếm.
        5. Bắt API response JSON Next.js streaming (sửa lỗi index 2 chữ số).
        6. Chuyển sang 100 kết quả/trang và phân trang tối đa MAX_SEARCH_PAGES.

    Trả về: Danh sách dict gồm { "title", "url", "status", "hieu_luc" }
    """

    def log(msg):
        if log_fn:
            log_fn(msg)

    log(f"🔍 Bắt đầu tìm kiếm: '{keyword}'")

    api_data_list: list = []

    def capture_api(response):
        """
        Bắt và parse API response JSON Next.js streaming.
        FIX: Dùng Regex ^\d+: để cắt index bất kỳ độ dài (0: đến 999: đều đúng).
        """
        try:
            content_type = response.headers.get("content-type", "").lower()
            if "json" not in content_type and "x-component" not in content_type:
                return

            text_data = response.text()
            for line in text_data.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if '"items":[' not in line or '"total":' not in line:
                    continue

                # FIX: Regex cắt tiền tố index (0:, 1:, 10:, 99: đều đúng)
                json_str = re.sub(r"^\d+:\s*", "", line)
                try:
                    parsed = json.loads(json_str)
                    if isinstance(parsed, dict) and "items" in parsed:
                        api_data_list.append(parsed)
                except json.JSONDecodeError:
                    continue
        except Exception:
            pass

    # FIX: Gỡ bỏ listener cũ trước khi đăng ký mới để tránh chồng chất
    try:
        page.remove_listener("response", capture_api)
    except Exception:
        pass
    page.on("response", capture_api)

    try:
        page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=120000)
    except Exception as e:
        log(f"❌ Không mở được trang chủ VBPL: {e}")
        return []

    # Nhập từ khóa
    try:
        search_input = page.locator("input[type='text']").first
        search_input.wait_for(state="visible", timeout=15000)
        search_input.fill(keyword)
    except Exception as e:
        log(f"❌ Không tìm thấy ô tìm kiếm: {e}")
        return []

    # Tìm kiếm nâng cao → Còn hiệu lực
    try:
        adv_btn = page.locator("button:has-text('Tìm kiếm nâng cao')")
        adv_btn.wait_for(state="visible", timeout=8000)
        adv_btn.click(force=True)
        page.wait_for_timeout(2000)

        tinh_trang = page.locator(".ant-select").filter(
            has=page.locator("#effStatus")
        )
        tinh_trang.locator(".ant-select-selector").click(force=True, timeout=8000)
        page.wait_for_timeout(1000)

        dropdown_selectors = [
            "#effStatus_list",
            ".ant-select-dropdown:not(.ant-select-dropdown-hidden)",
            ".rc-virtual-list-holder-inner .ant-select-item",
        ]
        for sel in dropdown_selectors:
            try:
                page.wait_for_selector(sel, state="visible", timeout=10000)
                log(f"   ├── Dropdown hiện: {sel}")
                break
            except Exception:
                continue

        clicked = False
        for opt in [
            "text='Còn hiệu lực'",
            ".ant-select-item-option[title='Còn hiệu lực']",
            ".ant-select-item-option:has-text('Còn hiệu lực')",
        ]:
            try:
                page.locator(opt).first.click(force=True, timeout=3000)
                clicked = True
                break
            except Exception:
                continue
        if not clicked:
            page.keyboard.press("ArrowDown")
            page.wait_for_timeout(300)
            page.keyboard.press("Enter")

        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)
        log("   ├── Bộ lọc: Còn hiệu lực")
    except Exception as e:
        log(f"⚠️ Không áp được bộ lọc hiệu lực: {e}")

    # Bấm Tìm kiếm
    try:
        api_data_list.clear()
        log("🖱️ Đang ấn Tìm kiếm...")
        page.get_by_role("button", name="Tìm kiếm", exact=True).first.click(force=True)
        page.wait_for_timeout(5000)
    except Exception as e:
        log(f"❌ Không bấm được nút Tìm kiếm: {e}")
        return []

    # Chuyển sang 100 kết quả/trang
    try:
        size_changer = page.locator(
            ".ant-pagination-options-size-changer, div[aria-label='kích thước trang']"
        ).first
        if size_changer.is_visible():
            size_changer.click(force=True)
            page.wait_for_timeout(500)
            option_100 = page.locator(
                ".ant-select-item-option-content, [title='100 / trang']"
            ).filter(has_text="100 / trang").first
            option_100.click(force=True)
            log("🔄 Đã đổi sang 100 kết quả/trang.")
            api_data_list.clear()
            page.wait_for_timeout(5000)
    except Exception as e:
        log(f"⚠️ Không đổi được 100/trang: {e}")

    # Phân trang
    documents: list[dict] = []
    unique_urls: set[str] = set()
    current_page = 1

    while current_page <= MAX_SEARCH_PAGES:
        log(f"⏳ Chờ dữ liệu trang {current_page}...")
        page.wait_for_timeout(5000)
        new_count = 0

        for data in api_data_list:
            for item in data.get("items", []):
                if not isinstance(item, dict):
                    continue
                doc_id = str(item.get("id", "")).strip()
                title = clean_text(item.get("title", ""))
                eff = item.get("effStatus", {})
                status = clean_text(eff.get("name", "")) if isinstance(eff, dict) else ""
                if not doc_id or not title:
                    continue
                url = f"{BASE_URL}/van-ban/chi-tiet/{doc_id}"
                if url in unique_urls:
                    continue
                unique_urls.add(url)
                hieu_luc = _normalize_hieu_luc(status)
                documents.append({
                    "title": title,
                    "url": url,
                    "status": status,
                    "hieu_luc": hieu_luc,
                })
                new_count += 1

        log(f"📌 Bắt được {new_count} văn bản ở trang {current_page}.")
        api_data_list.clear()

        if new_count == 0:
            break

        # Chuyển trang
        clicked = False
        for sel in [
            ".ant-pagination-next:not(.ant-pagination-disabled)",
            "li.ant-pagination-next:not(.ant-pagination-disabled) button",
            "a:text-is('>')",
        ]:
            elems = page.locator(sel)
            if elems.count() > 0:
                try:
                    if elems.first.is_visible():
                        elems.first.click(force=True)
                        clicked = True
                        break
                except Exception:
                    continue
        if clicked:
            current_page += 1
            log(f"➡️ Chuyển trang {current_page}...")
            page.wait_for_timeout(1500)
        else:
            log("🏁 Đã đến trang cuối.")
            break

    # FIX: Gỡ listener để tránh stacking khi gọi search cho keyword tiếp theo
    try:
        page.remove_listener("response", capture_api)
    except Exception:
        pass

    log(f"📌 Tổng: {len(documents)} văn bản cho '{keyword}'.")
    return documents
