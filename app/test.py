import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
import time
import re

BASE_URL = "https://vbpl.vn"
DATE_THRESHOLD = datetime.strptime("01/07/2025", "%d/%m/%Y")


async def fetch(session, url):
    async with session.get(url) as resp:
        resp.raise_for_status()
        return await resp.text()


async def parse_page(html):
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
                valid_date_text = p.get_text(strip=True).replace(label.get_text(strip=True), "").strip()
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
            public_date_text = first_p.get_text(strip=True).replace(label.get_text(strip=True), "").strip()
        else:
            public_date_text = first_p.get_text(strip=True)

        # --- file_path (title) ---
        title_tag = title_div.find("a") 
        if not title_tag: 
            continue

        # --- detail_url ---
        detail_a = title_div.find("a", href=True)
        if not detail_a:
            continue
        detail_url = BASE_URL + detail_a["href"]

        items.append({
            "title": title_tag.get_text(strip=True),
            "content": [],
            "valid_date": valid_date.strftime("%d/%m/%Y"),
            "public_date": public_date_text,
            "detail_url": detail_url
        })

    return items

async def extract_source_url_with_semaphore(session, detail_url: str, semaphore):
    async with semaphore:
        return await extract_source_url(session, detail_url)    

async def extract_source_url(session, detail_url: str) -> str | None:
    html = await fetch(session, detail_url)
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


async def crawl_all(url):
    async with aiohttp.ClientSession() as session:
        start_time = time.time()
        # Lấy số page
        first_html = await fetch(session, url)
        soup = BeautifulSoup(first_html, "html.parser")
        last_page_tag = soup.find("a", string=lambda t: t and "Cuối" in t)
        total_page = int(last_page_tag["href"].split("Page=")[-1])
        print(f"Tổng số page: {total_page}")

        # B1: tải tất cả page song song
        page_tasks = [fetch(session, url)
                      for i in range(1, total_page + 1)]
        pages_html = await asyncio.gather(*page_tasks)

        # B2: parse tất cả page song song
        parse_tasks = [parse_page(html) for html in pages_html]
        parsed_pages = await asyncio.gather(*parse_tasks)
        items = [item for page in parsed_pages for item in page]  # flatten

        # B3: extract source_url song song
        semaphore = asyncio.Semaphore(10)
        src_tasks = [
            extract_source_url_with_semaphore(session, item["detail_url"], semaphore)
            for item in items
        ]
        source_urls = await asyncio.gather(*src_tasks)
        enriched_items = []
        for item, src in zip(items, source_urls):
            if src:
                enriched_items.append({**item, "source_url": src})

        # Biến src thành upload_url
        upload_url_tasks = [
            upload_pdf_from_url(item["source_url"])
            for item in enriched_items
        ]
        upload_urls = await asyncio.gather(*upload_url_tasks)
        for item, upload_url in zip(enriched_items, upload_urls):
            item["source_url"] = upload_url

        # B4: OCR song song
        ocr_results = await run_ocr_for_items(enriched_items)
        print(f"OCR done in {time.time() - start_time:.2f} seconds")

        # B5: Ghép kết quả OCR vào field content
        for item, ocr_result in zip(enriched_items, ocr_results):
            item["content"] = ocr_result["content"]
            item.pop("detail_url", None)

        return enriched_items


import os
from mistralai import Mistral
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
api_key = "joqMh4RpBz5YVBiPOTHPlbCPvt3ZDylA"
client = Mistral(api_key=api_key)

import tempfile


async def download_file(url: str) -> str:
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


async def upload_pdf(file_path: str) -> str:
    def _sync_upload():
        with open(file_path, "rb") as f:
            content = f.read()
            filename = os.path.basename(file_path)
            uploaded_file = client.files.upload(
                file={"file_name": filename, "content": content},
                purpose="ocr",
            )
            signed_url = client.files.get_signed_url(file_id=uploaded_file.id)
            return signed_url.url
    return await asyncio.to_thread(_sync_upload)
    
async def upload_pdf_from_url(url: str) -> str:
    local_path = await download_file(url)
    return await upload_pdf(local_path)


async def process_ocr(document_source):
    ocr_result = await client.ocr.process_async(
        model="mistral-ocr-latest",
        document=document_source,
        include_image_base64=True
    )
    return {
        "ocr_result": ocr_result.pages,
        "document_source": document_source
    }


async def run_ocr_for_items(items):
    semaphore = asyncio.Semaphore(5)
    async def ocr_task(item):
        async with semaphore:
            document_source = {"type": "document_url", "document_url": item["source_url"]}
            ocr = await process_ocr(document_source)
            return {**item, "content": ocr["ocr_result"]}

    tasks = [ocr_task(item) for item in items]
    results = await asyncio.gather(*tasks)
    return results


if __name__ == "__main__":
    url = "https://vbpl.vn/TW/Pages/vanban.aspx?idLoaiVanBan=20&dvid=13&Page=1"
    data = asyncio.run(crawl_all(url))
    print(f"Tổng số văn bản thỏa mãn: {len(data)}")
    print(data[:2])