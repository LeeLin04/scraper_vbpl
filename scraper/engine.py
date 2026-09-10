"""
scraper/engine.py – Động cơ Playwright điều khiển quá trình cào dữ liệu VBPL.

Chứa toàn bộ logic:
  - Bước 1 (Pass 1): Mở trang nhẹ nhàng để tạo session / vượt chống bot.
  - Bước 2 (Pass 2): Mở đầy đủ giao diện, click switch & Modal Ant Design,
                     đọc nội dung sửa đổi và bóc tách dữ liệu.

FIX: Lỗi luôn lấy trùng Modal #1 đã được sửa: dùng Playwright Locator trực tiếp
     thay vì parse page.content() qua BeautifulSoup.
"""

import re
import time

from bs4 import BeautifulSoup

from config import USER_AGENTS
from utils.text_utils import clean_text, extract_document_number, slugify_key
from scraper.parser import build_document
from utils.storage import save_document


# =========================================================================
# FETCH PAGE – Điều khiển trình duyệt, click expand & Modal
# =========================================================================

def _open_session_pass(page, url: str) -> bool:
    """
    Pass 1: Chỉ mở URL để tạo session / cookie / vượt kiểm tra chống bot.
    Không trích xuất bất kỳ dữ liệu nào.
    """
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    return True


def _fetch_content_pass(page, url: str, log_fn=None) -> tuple | None:
    """
    Pass 2: Tải đầy đủ nội dung trang, click các nút expand / ant-switch,
    tuần tự mở từng Modal sửa đổi và đọc nội dung.

    Trả về: (page_text: str, soup: BeautifulSoup, modified_texts: list)
            hoặc None nếu trang trống.

    FIX: Đọc nội dung Modal bằng page.locator(".ant-modal-body").last.inner_text()
         thay vì page.content() + select_one() để tránh luôn lấy trùng Modal #1.
    """

    def log(msg):
        if log_fn:
            log_fn(msg)

    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)

    # --- Click các nút expand thông thường ---
    try:
        expand_selectors = [
            ".btn-expand", ".btn-more", ".show-more", ".toggle-content",
            "[data-toggle='collapse']", ".prov-expand", ".icon-expand",
            "a.view-more", "button.btn-show",
        ]
        for sel in expand_selectors:
            for btn in page.query_selector_all(sel):
                try:
                    if btn.is_visible():
                        btn.click(force=True)
                        page.wait_for_timeout(300)
                except Exception:
                    pass
    except Exception:
        pass

    # --- Bật switch "Hiển thị chi tiết cập nhật" ---
    try:
        for sw in page.query_selector_all(".ant-switch, [role='switch']"):
            try:
                if not sw.is_visible():
                    continue
                if sw.get_attribute("aria-checked") != "true":
                    sw.scroll_into_view_if_needed()
                    sw.hover()
                    sw.click(force=True)
                    page.wait_for_timeout(300)
            except Exception:
                pass
    except Exception:
        pass

    # --- Tuần tự mở từng nút "Điều khoản được sửa đổi, bổ sung" ---
    modified_texts = []
    try:
        all_buttons = page.query_selector_all("button")
        button_index = 0

        for btn in all_buttons:
            try:
                if not btn.is_visible():
                    continue
                btn_text = btn.inner_text().strip().lower()
                if (
                    "điều khoản được sửa đổi" not in btn_text
                    and "sửa đổi, bổ sung" not in btn_text
                ):
                    continue

                button_index += 1

                # Lấy ngữ cảnh Điều/Khoản/Điểm gần nhất qua DOM traversal
                context_info = btn.evaluate("""
                    (element) => {
                        let curr = element;
                        let item_text = null, clause_text = null, article_text = null;
                        while (curr && curr !== document.body) {
                            let sib = curr.previousElementSibling;
                            while (sib) {
                                if (!item_text && !clause_text && !article_text
                                        && sib.matches('p.prov-item'))
                                    item_text = sib.innerText.trim();
                                if (!clause_text && !article_text
                                        && sib.matches('p.prov-clause'))
                                    clause_text = sib.innerText.trim();
                                if (!article_text && sib.matches('p.prov-article')) {
                                    article_text = sib.innerText.trim();
                                    break;
                                }
                                sib = sib.previousElementSibling;
                            }
                            if (article_text) break;
                            curr = curr.parentElement;
                        }
                        return { item: item_text, clause: clause_text, article: article_text };
                    }
                """)

                doc_title = page.title()
                nghi_dinh = extract_document_number(doc_title) or doc_title
                document_key = slugify_key(nghi_dinh)
                target_key = document_key

                article_text = context_info.get("article", "")
                clause_text = context_info.get("clause", "")
                item_text = context_info.get("item", "")

                if article_text:
                    m = re.match(r"Điều\s+(\d+[a-zA-Z]?)", article_text, flags=re.IGNORECASE)
                    if m:
                        target_key += f"_Dieu_{slugify_key(m.group(1))}"
                if clause_text:
                    m = re.match(r"^(\d+)\.\s*", clause_text)
                    if m:
                        target_key += f"_Khoan_{m.group(1)}"
                if item_text:
                    m = re.match(r"^([a-zđĐ])\)\s+", item_text)
                    if m:
                        target_key += f"_Diem_{slugify_key(m.group(1))}"

                btn.scroll_into_view_if_needed()
                btn.hover()
                btn.click(force=True)

                try:
                    page.wait_for_selector(".ant-modal", state="visible", timeout=10000)
                except Exception:
                    pass
                page.wait_for_timeout(300)

                # Chọn dropdown ngày sửa đổi (nếu có)
                try:
                    select_elem = page.wait_for_selector(
                        ".ant-modal-body .ant-select", timeout=5000
                    )
                    if select_elem:
                        select_elem.scroll_into_view_if_needed()
                        select_elem.hover()
                        select_elem.click()
                        page.wait_for_timeout(300)
                        option_elem = page.wait_for_selector(
                            ".ant-select-dropdown "
                            ":not(.ant-select-item-option-disabled)"
                            ".ant-select-item-option",
                            timeout=5000,
                        )
                        if option_elem:
                            option_elem.click()
                            page.wait_for_timeout(400)
                except Exception as e_sel:
                    log(f"   ℹ️ Không có dropdown ngày ở nút #{button_index}: {e_sel}")

                # FIX: Đọc nội dung Modal trực tiếp bằng Playwright Locator
                # thay vì page.content() + BeautifulSoup.select_one()
                # Đảm bảo luôn đọc đúng Modal đang mở (visible), không nhầm Modal cũ.
                try:
                    modal_body = page.locator(".ant-modal-body").last
                    if modal_body.is_visible():
                        modal_text = clean_text(modal_body.inner_text())
                    else:
                        modal_text = ""

                    if modal_text:
                        # Tinh chỉnh target_key từ nội dung thực tế của Modal
                        content_for_key = re.sub(
                            r"^.*?Chi tiết thay đổi\s*", "", modal_text,
                            flags=re.IGNORECASE | re.DOTALL,
                        ).strip()

                        base_key = document_key
                        if article_text:
                            m = re.match(
                                r"Điều\s+(\d+[a-zA-Z]?)", article_text,
                                flags=re.IGNORECASE,
                            )
                            if m:
                                base_key = f"{document_key}_Dieu_{slugify_key(m.group(1))}"

                        ck = re.match(r"^(\d+)\.\s*", content_for_key)
                        cd = re.match(r"^([a-zđĐ])\)\s*", content_for_key)
                        if ck:
                            target_key = f"{base_key}_Khoan_{ck.group(1)}"
                        elif cd and clause_text:
                            pk = re.match(r"^(\d+)\.\s*", clause_text)
                            if pk:
                                target_key = f"{base_key}_Khoan_{pk.group(1)}_Diem_{slugify_key(cd.group(1))}"
                            else:
                                target_key = f"{base_key}_Diem_{slugify_key(cd.group(1))}"
                        elif cd:
                            target_key = f"{base_key}_Diem_{slugify_key(cd.group(1))}"

                        modified_texts.append({
                            "target_key": target_key,
                            "btn_idx": button_index,
                            "content": modal_text,
                        })
                        log(f"   📌 Đã lấy Box sửa đổi #{button_index}")

                except Exception as e_modal:
                    log(f"   ⚠️ Lỗi đọc Modal #{button_index}: {e_modal}")

                # Đóng Modal
                try:
                    close_btn = page.query_selector(
                        ".ant-modal-close, .ant-modal-footer button"
                    )
                    if close_btn and close_btn.is_visible():
                        close_btn.click(force=True)
                    else:
                        page.keyboard.press("Escape")
                except Exception:
                    page.keyboard.press("Escape")

                page.wait_for_timeout(500)

            except Exception as e_btn:
                log(f"⚠️ Lỗi nút #{button_index}: {e_btn}")
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass

    except Exception as e:
        log(f"⚠️ Lỗi khi duyệt các nút sửa đổi: {e}")

    page.wait_for_timeout(1000)

    soup = BeautifulSoup(page.content(), "lxml")
    page_text = soup.get_text("\n", strip=True)

    if len(page_text) < 100:
        return None

    return page_text, soup, modified_texts


# =========================================================================
# SCRAPE URL – Cào một văn bản từ URL cụ thể
# =========================================================================

def scrape_url(url: str, keyword: str = "Direct_URL", log_fn=None) -> str | None:
    """
    Cào một văn bản VBPL từ URL, lưu file JSON + TXT và trả về đường dẫn file.

    Quy trình 2 bước:
      - Pass 1: Mở trang nhẹ để tạo session / vượt chống bot.
      - Pass 2: Mở đầy đủ, click Modal, đọc & xử lý dữ liệu.
    """
    from playwright.sync_api import sync_playwright

    def log(msg):
        if log_fn:
            log_fn(msg)

    try:
        log(f"🎯 Bắt đầu cào: {url}")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page(user_agent=USER_AGENTS[0])

            # Pass 1
            log("🛡️ Pass 1: Tạo session / vượt chống bot...")
            try:
                _open_session_pass(page, url)
            except Exception as e:
                log(f"❌ Pass 1 thất bại: {e}")
                browser.close()
                return None

            log("✅ Pass 1 xong. Chờ 2 giây...")
            time.sleep(2)

            # Pass 2
            log("💾 Pass 2: Cào chính thức...")
            result = _fetch_content_pass(page, url, log_fn=log_fn)
            if not result:
                log("❌ Pass 2 thất bại (trang trống).")
                browser.close()
                return None

            page_text, soup, modified_texts = result

            # Metadata
            h1 = soup.find("h1")
            title = clean_text(h1.get_text(" ", strip=True)) if h1 else "Chưa rõ Tiêu đề"

            from utils.text_utils import detect_status, extract_issued_date, extract_effective_date
            doc_info = {
                "title": title,
                "keyword": keyword,
                "status": detect_status(page_text),
                "issued_date": extract_issued_date(page_text),
                "effective_date": extract_effective_date(page_text),
                "source_url": url,
            }

            # Build + Save
            document = build_document(soup, page_text, doc_info, modified_texts)
            file_path = save_document(document)

            content_tree = document.get("content_tree", [])
            khoan_count = sum(len(d.get("children", [])) for d in content_tree)

            log(f"🎉 HOÀN THÀNH: [{title[:60]}...]")
            log(f"   ├── File     : {file_path}")
            log(f"   ├── Số Điều  : {len(content_tree)}")
            log(f"   ├── Số Khoản : {khoan_count}")
            log(f"   └── Sửa đổi  : {len(modified_texts)} modal đã đọc")

            browser.close()
            return file_path

    except Exception as e:
        log(f"❌ Lỗi khi cào {url}: {e}")
        return None
