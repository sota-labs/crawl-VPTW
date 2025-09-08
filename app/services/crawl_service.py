import asyncio
import os
import re
import tempfile
import time
from datetime import datetime
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from app.config.logging import log
from app.services.ocr_service import OCRService

BASE_URL = os.getenv("BASE_URL", "https://vbpl.vn")
DATE_THRESHOLD = datetime.strptime(
    os.getenv("DATE_THRESHOLD", "01/07/2025"), "%d/%m/%Y"
)


class CrawlService:
    def __init__(self, ocr_service: OCRService, max_concurrency=10):
        self.ocr_service = ocr_service
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def fetch(self, session, url) -> str:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def download_file(self, url: str) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                filename = url.split("/")[-1] or "downloaded.pdf"

                # Lưu trong thư mục tạm
                temp_dir = tempfile.gettempdir()
                file_path = os.path.join(temp_dir, filename)

                with open(file_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                return file_path

    async def crawl_all(self) -> list[dict]:
        async with aiohttp.ClientSession() as session:
            try:
                start_time = time.time()
                start_url = os.getenv(
                    "START_URL",
                    (
                        "https://vbpl.vn/TW/Pages/vanban.aspx?"
                        "idLoaiVanBan=20&dvid=13&Page=1"
                    ),
                )
                # Lấy số page
                first_html = await self.fetch(session, start_url)
                soup = BeautifulSoup(first_html, "html.parser")
                last_page_tag = soup.find("a", string=lambda t: t and "Cuối" in t)
                total_page = int(last_page_tag["href"].split("Page=")[-1])
                max_page = int(os.getenv("MAX_PAGE", 20))
                if total_page >= max_page:
                    total_page = max_page
                print(f"Tổng số page: {total_page}")

                # B1: tải tất cả page song song
                page_tasks = []
                for page in range(1, total_page + 1):
                    page_url = (
                        f"https://vbpl.vn/TW/Pages/vanban.aspx?"
                        f"idLoaiVanBan=20&dvid=13&Page={page}"
                    )
                    # print(f"Fetching page: {page_url}")
                    page_tasks.append(self.fetch(session, page_url))
                pages_html = await asyncio.gather(*page_tasks)

                # B2: parse tất cả page song song
                parse_tasks = [self.parse_page(html) for html in pages_html]
                parsed_pages = await asyncio.gather(*parse_tasks)
                print(f"Step 2 done in {time.time() - start_time:.2f} seconds")

                # B3: extract source_url song song
                items = [item for page in parsed_pages for item in page]  # flatten
                print("Số văn bản: ", len(items))
                max_doc = int(os.getenv("MAX_DOC", 40))
                if len(items) >= max_doc:
                    items = items[:max_doc]

                src_tasks = [
                    self.extract_source_url(session, item["file_url"]) for item in items
                ]
                source_urls = await asyncio.gather(*src_tasks)
                enriched_items = []
                for item, src in zip(items, source_urls):
                    if src:
                        enriched_items.append(
                            {**item, "source_url": src, "view_url": src}
                        )
                print(f"Extract done in {time.time() - start_time:.2f} seconds")

                # B4: Upload file lên mistral cloud
                upload_url_tasks = [
                    self.ocr_service.upload_pdf_from_url(item["source_url"])
                    for item in enriched_items
                ]
                upload_urls = await asyncio.gather(*upload_url_tasks)
                for item, upload_url in zip(enriched_items, upload_urls):
                    item["source_url"] = upload_url
                print(f"Upload done in {time.time() - start_time:.2f} seconds")
                print("enriched_items", enriched_items)

                # B5: OCR song song
                ocr_results = await self.ocr_service.run_ocr_for_items(enriched_items)
                print(f"OCR done in {time.time() - start_time:.2f} seconds")

                # B6: Ghép kết quả OCR vào field content
                for item, ocr_result in zip(enriched_items, ocr_results):
                    item["content"] = ocr_result["content"]
                    item.pop("file_url", None)
                    item.pop("source_url", None)
                    item["source_url"] = item.pop("view_url")
                print(f"Total time: {time.time() - start_time:.2f} seconds")

                return enriched_items

            except Exception as e:
                log.error(f"Crawl website {os.getenv('START_URL')} error: {e}")
                return []

    async def parse_page(self, html) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        content_div = soup.find("div", {"id": "tabVB_lv1"})
        if not content_div:
            return []

        ul_tag = content_div.find("ul", {"class": "listLaw"})
        if not ul_tag:
            return []

        items = []
        for li in ul_tag.find_all("li"):
            item_div = li.find("div", class_="item")
            if not item_div:
                continue

            title_div = item_div.find("p", class_="title")
            left_div = item_div.find("div", class_="left")
            right_div = item_div.find("div", class_="right")

            if not (left_div and right_div and title_div):
                continue

            p_tags = right_div.find_all("p")
            if len(p_tags) > 2:
                continue

            # --- valid_date ---
            valid_date_text = None
            for p in p_tags:
                label = p.find("label")
                if label and "Hiệu lực" in label.get_text(strip=True):
                    valid_date_text = (
                        p.get_text(strip=True)
                        .replace(label.get_text(strip=True), "")
                        .strip()
                    )
                    break
            if not valid_date_text:
                continue

            try:
                valid_date = datetime.strptime(valid_date_text, "%d/%m/%Y")
            except ValueError:
                continue

            if valid_date < DATE_THRESHOLD:
                continue

            # --- public_date ---
            first_p = p_tags[0]
            label = first_p.find("label")
            if label:
                public_date_text = (
                    first_p.get_text(strip=True)
                    .replace(label.get_text(strip=True), "")
                    .strip()
                )
            else:
                public_date_text = first_p.get_text(strip=True)

            # --- file_path (title) ---
            title_tag = title_div.find("a")
            if not title_tag:
                continue

            # --- file_url ---
            detail_a = title_div.find("a", href=True)
            if not detail_a:
                continue
            file_url = BASE_URL + detail_a["href"]

            items.append(
                {
                    "title": title_tag.get_text(strip=True),
                    "content": [],
                    "valid_date": valid_date.strftime("%d/%m/%Y"),
                    "public_date": public_date_text,
                    "file_url": file_url,
                }
            )

        return items

    async def extract_source_url(self, session, file_url: str) -> str | None:
        async with self.semaphore:
            try:
                html = await self.fetch(session, file_url)
                soup = BeautifulSoup(html, "html.parser")

                # Rule 1: tìm vbProperties -> object[data]
                vb_props = soup.find("div", class_="vbProperties")
                if vb_props:
                    obj = vb_props.find("object")
                    if obj and obj.has_attr("data"):
                        return BASE_URL + obj["data"]

                # Rule 2: fallback sang vbFile
                vb_file = soup.find("div", class_="vbFile")
                if vb_file:
                    candidates = []
                    for a in vb_file.find_all("a", href=True):
                        match = re.search(r"downloadfile\([^,]+,'([^']+)'\)", a["href"])
                        if match:
                            candidates.append(match.group(1))

                    if candidates:
                        # Ưu tiên pdf
                        for c in candidates:
                            if c.lower().endswith(".pdf"):
                                return BASE_URL + c
                        # fallback sang docx
                        for c in candidates:
                            if c.lower().endswith(".docx"):
                                return BASE_URL + c
                return None

            except Exception as e:
                log.error(f"Extract source url from {file_url} error: {e}")
                return None


class CrawlerServiceV2:
    def __init__(self, ocr_service):
        self.base_url = os.getenv(
            "BASE_URL_V2",
            (
                "https://vanban.chinhphu.vn/he-thong-van-ban?"
                "classid=1&mode=1&typegroupid=4"
            ),
        )
        self.session: aiohttp.ClientSession | None = None
        self.ocr_service = ocr_service

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    @staticmethod
    def get_hidden_fields(html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        fields = {}
        for inp in soup.find_all("input", {"type": "hidden"}):
            if inp.get("name") and inp.get("value") is not None:
                fields[inp["name"]] = inp["value"]
        return fields

    @staticmethod
    def extract_attachment_links(html: str) -> list[str]:
        try:
            soup = BeautifulSoup(html, "html.parser")
            table_content = soup.find("table", class_="table search-result")
            if not table_content:
                return []
            links = []
            for a_tag in table_content.find_all("a", href=True):
                if a_tag.has_attr("download"):
                    links.append(a_tag["href"])
            return links
        except Exception as e:
            log.error(f"Extract attachment links error: {e}")
            return []

    def get_header(self) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/139.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": self.base_url,
        }

    @staticmethod
    def extract_event_target(html: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        # Tìm tất cả href có chứa __doPostBack
        links = soup.find_all("a", href=True)
        for link in links:
            m = re.search(r"__doPostBack\('([^']+)'", link["href"])
            if m:
                return m.group(1)
        return None

    async def _extract_attachment_links(self, html: str) -> list[str]:
        try:
            if not self.session:
                raise RuntimeError("Session chưa được khởi tạo..")

            soup = BeautifulSoup(html, "html.parser")
            table = soup.find("table", class_="table search-result")
            if not table:
                return []

            results = []
            rows = table.find_all("tr")
            for row in rows[1:]:
                cols = row.find_all("td")
                if not cols:
                    continue

                a_tag = cols[0].find("a", href=True)
                if not a_tag:
                    continue

                href = a_tag["href"]
                if href.startswith("javascript:"):
                    continue

                detail_url = urljoin(self.base_url, href)

                # tải trang chi tiết
                try:
                    async with self.session.get(
                        detail_url, headers=self.get_header()
                    ) as resp:
                        resp.raise_for_status()
                        detail_html = await resp.text()
                except Exception as e:
                    print(f"[ERROR] Không tải được {detail_url}: {e}")
                    continue

                detail_soup = BeautifulSoup(detail_html, "html.parser")
                content_div = detail_soup.find("div", class_="Content")
                if not content_div:
                    continue

                detail_table = content_div.find("table")
                if not detail_table:
                    continue

                details = {}
                for tr in detail_table.find_all("tr"):
                    tds = tr.find_all(["td", "th"])
                    if len(tds) >= 2:
                        key = tds[0].get_text(strip=True)
                        val = tds[1].get_text(strip=True)
                        details[key] = (val, tds[1])

                # kiểm tra "Ngày có hiệu lực"
                eff_date_str, _ = details.get("Ngày có hiệu lực", (None, None))
                if not eff_date_str:
                    continue

                try:
                    eff_date = datetime.strptime(eff_date_str, "%d-%m-%Y")
                except ValueError:
                    print(f"[WARN] Không parse được ngày: {eff_date_str}")
                    continue

                if eff_date >= datetime(2025, 7, 1):
                    attach_val, attach_td = details.get(
                        "Tài liệu đính kèm", (None, None)
                    )
                    if attach_td:
                        a = attach_td.find("a", title="Tải về", href=True)
                        if a:
                            file_url = urljoin(self.base_url, a["href"])
                            results.append(
                                {
                                    "title": details.get("Số ký hiệu", (None, None))[0],
                                    "source_url": file_url,
                                    "view_url": file_url,
                                    "valid_date": eff_date_str,
                                    "public_date": details.get(
                                        "Ngày ban hành", (None, None)
                                    )[0],
                                    "abstract": details.get("Trích yếu", (None, None))[
                                        0
                                    ],
                                }
                            )
            return results
        except Exception as e:
            log.error(f"Extract attachment links error: {e}")
            return []

    async def fetch_page(
        self, page_number: int, hidden_fields: dict | None = None
    ) -> str:
        if not self.session:
            raise RuntimeError("Session chưa được khởi tạo.")

        if page_number == 1 or hidden_fields is None:
            async with self.session.get(
                self.base_url, headers=self.get_header()
            ) as resp:
                resp.raise_for_status()
                html = await resp.text()
                return html
        else:
            # Lấy event_target từ base_url hoặc cache sẵn
            async with self.session.get(
                self.base_url, headers=self.get_header()
            ) as resp:
                resp.raise_for_status()
                base_html = await resp.text()
            event_target = (
                self.extract_event_target(base_html) or "ctrl_191017_163$grvDocument"
            )

            data = hidden_fields.copy()
            data["__EVENTTARGET"] = event_target
            data["__EVENTARGUMENT"] = f"Page${page_number}"

            async with self.session.post(
                self.base_url, data=data, headers=self.get_header()
            ) as resp:
                resp.raise_for_status()
                return await resp.text()

    async def crawl_all(self, n: int = 10) -> list[str]:
        try:
            start_time = time.time()
            # B1: Lấy toàn bộ url pdf
            items = []
            page_start = os.getenv("PAGE_START", 1)
            html = await self.fetch_page(page_start)
            hidden_fields = self.get_hidden_fields(html)
            _items = await self._extract_attachment_links(html)
            items.extend(_items)
            page_start = 1
            for page_number in range(page_start + 1, n + 1):
                html = await self.fetch_page(page_number, hidden_fields)
                hidden_fields = self.get_hidden_fields(html)
                _items = await self._extract_attachment_links(html)
                items.extend(_items)

            max_doc = int(os.getenv("MAX_DOC", 40))
            if len(items) >= max_doc:
                items = items[:max_doc]
            print(f"B1 done in {time.time() - start_time:.2f} seconds")

            # B2: Upload pdf
            # upload_url_tasks = [
            #     self.ocr_service.upload_pdf_from_url(item["source_url"])
            #     for item in items[:2]
            # ]
            # upload_urls = await asyncio.gather(*upload_url_tasks)
            # for item, upload_url in zip(items, upload_urls):
            #     item["source_url"] = upload_url
            # print(f"B2 done in {time.time() - start_time:.2f} seconds")

            # B3: OCR
            ocr_results = []
            ocr_results = await self.ocr_service.run_ocr_for_items(items)

            for item, ocr_result in zip(items, ocr_results):
                item["content"] = ocr_result["content"]
                item.pop("source_url", None)
                item["source_url"] = item.pop("view_url")
                item.pop("view_url", None)
            print(f"B3 done in {time.time() - start_time:.2f} seconds")

            return items

        except Exception as e:
            log.error(f"Crawl all error: {e}")
            return []
