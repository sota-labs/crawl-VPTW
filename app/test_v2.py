import aiohttp
from bs4 import BeautifulSoup
import asyncio
import os
from urllib.parse import urljoin
from datetime import datetime
import random


class CrawlerServiceV2:
    def __init__(self, base_url: str, ocr_service):
        self.base_url = base_url
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
        soup = BeautifulSoup(html, "html.parser")
        table_content = soup.find("table", class_="table search-result")
        if not table_content:
            return []
        links = []
        for a_tag in table_content.find_all("a", href=True):
            if a_tag.has_attr("download"):
                links.append(a_tag["href"])
        return links
    
    async def _extract_attachment_links(self, html: str) -> list[str]:
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
                async with self.session.get(detail_url) as resp:
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
                attach_val, attach_td = details.get("Tài liệu đính kèm", (None, None))
                if attach_td:
                    a = attach_td.find("a", title="Tải về", href=True)
                    if a:
                        file_url = urljoin(self.base_url, a["href"])
                        results.append({
                            "title": details.get("Số ký hiệu", (None, None))[0],
                            "source_url": file_url,
                            "view_url": file_url,
                            "valid_date": eff_date,
                            "public_date": details.get("Ngày ban hành", (None, None))[0],
                            "abstract": details.get("Trích yếu", (None, None))[0],
                        })
        return results

    async def fetch_page(self, page: int, hidden_fields: dict | None = None) -> str:
        if not self.session:
            raise RuntimeError("Session chưa được khởi tạo. Hãy dùng 'async with'.")

        if page == 1 or hidden_fields is None:
            async with self.session.get(self.base_url) as resp:
                resp.raise_for_status()
                return await resp.text()
        else:
            data = {
                "__EVENTTARGET": "ctrl_191017_163$gvnDocument",
                "__EVENTARGUMENT": f"Page${page}",
            }
            data.update(hidden_fields)

            async with self.session.post(self.base_url, data=data) as resp:
                resp.raise_for_status()
                return await resp.text()

    async def crawl_all(self, n: int = 10) -> list[str]:
        hidden_fields = None

        # B1: Lấy toàn bộ url pdf
        items = []
        page_start = int(os.getenv("PAGE_START", 4))
        for page in range(page_start, n + 1):
            html = await self.fetch_page(page, hidden_fields)
            hidden_fields = self.get_hidden_fields(html)
            _items = await self._extract_attachment_links(html)
            items.extend(_items)
        # print('---------------------items', items)

        # B2: Upload pdf
        upload_url_tasks = [
            self.ocr_service.upload_pdf_from_url(item["source_url"], random.choice(proxies))
            for item in items[:2]
        ]
        upload_urls = await asyncio.gather(*upload_url_tasks)
        for item, upload_url in zip(items, upload_urls):
            item["source_url"] = upload_url
        print('---------------------items', items)

        # B3: OCR
        ocr_results = []
        ocr_results = await self.ocr_service.run_ocr_for_items(items)

        for item, ocr_result in zip(items, ocr_results):
            item["content"] = ocr_result["content"]
            # item.pop("file_url", None)
            item.pop("source_url", None)
            item["source_url"] = item.pop("view_url")
        print('---------------------ocr_results', ocr_results)
        return ocr_results
    


import os
import asyncio
import aiohttp
from mistralai import Mistral
import tempfile


class OCRService:
    def __init__(self, api_key, model="mistral-ocr-latest", max_concurrency=5):
        self.client = Mistral(api_key=api_key)
        self.model = model
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def process_ocr(self, document_source) -> dict:
        try:
            ocr_result = await self.client.ocr.process_async(
                model="mistral-ocr-latest",
                document=document_source,
                include_image_base64=True
            )

            return {
                "ocr_result": [
                    {
                        "page": page.index + 1,
                        "page_content": page.markdown,
                    }
                    for page in ocr_result.pages
                ],
                "document_source": document_source
            }

        except Exception as e:
            return {
                "error": str(e),
                "ocr_result": [],
                "document_source": document_source
            }

    async def download_file(self, url: str, proxy) -> str:
        try:
            async with self.semaphore:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        response.raise_for_status()
                        filename = url.split("/")[-1] or "downloaded.pdf"

                        temp_dir = tempfile.gettempdir()
                        file_path = os.path.join(temp_dir, filename)

                        with open(file_path, "wb") as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)

                        return file_path
        except Exception as e:
            return str(e)

    async def upload_pdf(self, file_path: str) -> str:
        try:
            async with self.semaphore:
                def _sync_upload():
                    with open(file_path, "rb") as f:
                        content = f.read()
                        filename = os.path.basename(file_path)
                        uploaded_file = self.client.files.upload(
                            file={"file_name": filename, "content": content},
                            purpose="ocr",
                        )
                        signed_url = self.client.files.get_signed_url(file_id=uploaded_file.id)
                        return signed_url.url
                return await asyncio.to_thread(_sync_upload)
        except Exception as e:
            return str(e)
        
    async def upload_pdf_from_url(self, url: str, proxy) -> str:
        local_path = await self.download_file(url, proxy)
        return await self.upload_pdf(local_path)

    async def run_ocr_for_items(self, items) -> list[dict]:
        async def ocr_task(item):
            async with self.semaphore:
                document_source = {
                    "type": "document_url",
                    "document_url": item["source_url"]
                }
                ocr = await self.process_ocr(document_source)
                return {**item, "content": ocr["ocr_result"]}

        tasks = [ocr_task(item) for item in items]
        results = await asyncio.gather(*tasks)
        return results
    



async def main():
    base_url = "https://vanban.chinhphu.vn/he-thong-van-ban?classid=1&mode=1&typegroupid=4"
    ocr_service = OCRService(api_key="joqMh4RpBz5YVBiPOTHPlbCPvt3ZDylA")
    async with CrawlerServiceV2(base_url, ocr_service) as crawler:
        urls = await crawler.crawl_all(10)
        print(f"Đã lấy {len(urls)} urls")
        print(urls)


proxies = [
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.12:4129",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.33:9933",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.34:5277",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.39:3682",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.4:20191",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.40:5795",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.44:1668",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.47:8336",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.5:18986",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.55:3307",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.57:2119",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.59:9449",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.6:31160",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.63:6059",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.64:8187",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.67:2907",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.7:30883",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.72:5576",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.74:5821",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.75:5002",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.8:40847",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.84:4266",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.89:3254",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.9:10075",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.99:6088",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.10:14007",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.100:7136",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.101:7437",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.11:20560",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.13:10554",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.14:12482",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.15:39818",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.16:24670",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.17:23675",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.18:23715",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.19:28693",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.20:19823",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.21:21135",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.22:32231",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.23:16558",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.24:16395",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.25:11234",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.26:30780",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.27:36392",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.28:33044",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.29:28489",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.30:29847",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.31:21788",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.32:40617",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.35:22312",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.36:33741",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.37:19495",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.38:41074",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.41:25481",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.42:31008",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.43:23314",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.45:36142",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.46:34760",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.48:17935",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.49:11975",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.50:30105",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.51:18432",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.52:24339",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.53:27463",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.54:27395",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.56:24113",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.58:13861",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.60:20081",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.61:39304",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.62:29896",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.65:26486",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.66:40573",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.68:37335",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.69:28676",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.70:39458",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.71:11818",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.73:35158",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.76:10236",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.77:26632",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.78:34388",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.79:35663",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.80:32127",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.81:10821",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.82:39225",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.83:18955",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.85:36240",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.86:14493",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.87:16504",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.88:17365",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.90:13047",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.91:25393",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.92:13639",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.93:23812",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.94:16983",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.95:16789",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.96:25230",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.97:27511",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.98:16602",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.102:21687",
    "http://Lw3vJO176G:olLz7LDRs5@77.93.143.103:34819",
]



if __name__ == "__main__":
    asyncio.run(main())