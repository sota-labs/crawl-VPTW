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
        text = await resp.text(encoding="utf-8", errors="ignore")
        return text


async def parse_page(html):
    results = []
    soup = BeautifulSoup(html, "html.parser")

    content_div = soup.find("div", {"id":"tabVB_lv1"})

    if not content_div:
        return results

    ul_tag = content_div.find("ul", {"class":"listLaw"})
    if not ul_tag:
        return results

    for li in ul_tag.find_all("li"):
        item_div = li.find("div", class_="item")
        if not item_div:
            continue
        
        title_div = item_div.find("p", class_="title")
        left_div = item_div.find("div", class_="left")
        right_div = item_div.find("div", class_="right")

        if not (left_div and right_div):
            continue

        p_tags = right_div.find_all("p")
        if len(p_tags) > 2:
            continue

        valid_date_text = None
        for p in p_tags:
            label = p.find("label")
            if label and "Hiệu lực" in label.get_text(strip=True):
                # lấy text còn lại ngoài label
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

        title_tag = title_div.find("a")
        if not title_tag:
            continue

        first_p = p_tags[0]
        label = first_p.find("label")
        if label:
            public_date_text = first_p.get_text(strip=True).replace(label.get_text(strip=True), "").strip()
        else:
            public_date_text = first_p.get_text(strip=True)

        results.append({
            "title": title_tag.get_text(strip=True),
            "content": [],
            "source_url": "",
            "valid_date": valid_date.strftime("%d/%m/%Y"),
            "public_date": public_date_text
        })

    return results


async def crawl_laws(url: str):
    async with aiohttp.ClientSession() as session:
        start_time = time.time()
        # B1: lấy số page
        html = await fetch(session, url)
        soup = BeautifulSoup(html, "html.parser")

        last_page_tag = soup.select_one('a[title="Cuối"]')
        if not last_page_tag:
            last_page_tag = soup.find("a", string=lambda t: t and "Cuối" in t)

        last_href = last_page_tag["href"]
        total_page = int(last_href.split("Page=")[-1])
        total_page = max(1, 20)
        print(f"Tổng số page: {total_page}")

        # B2: tạo danh sách task
        tasks = []
        for page in range(1, total_page + 1):
            page_url = f"https://vbpl.vn/TW/Pages/vanban.aspx?idLoaiVanBan=20&dvid=13&Page={page}"
            tasks.append(fetch(session, page_url))

        # B3: chạy song song
        pages_html = await asyncio.gather(*tasks)
        # B4: parse song song
        parse_tasks = [parse_page(html) for html in pages_html]
        all_results = await asyncio.gather(*parse_tasks)
        # flatten list
        results = [item for sublist in all_results for item in sublist]

        print(f"Extracting urls took {time.time() - start_time:.2f} seconds")
        return results


if __name__ == "__main__":
    url = "https://vbpl.vn/TW/Pages/vanban.aspx?idLoaiVanBan=20&dvid=13&Page=1"
    data = asyncio.run(crawl_laws(url))
    print(f"Tổng số văn bản thỏa mãn: {len(data)}")
    print(data[:3])



import os
from mistralai import Mistral
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
api_key = "joqMh4RpBz5YVBiPOTHPlbCPvt3ZDylA"
client = Mistral(api_key=api_key)

import requests
import tempfile

def download_file(url: str) -> str:
    response = requests.get(url, stream=True)
    response.raise_for_status()

    # Lấy tên file từ URL hoặc dùng tên tạm
    filename = url.split("/")[-1] or "downloaded.pdf"

    # Lưu trong thư mục tạm
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, filename)

    with open(file_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    return file_path

def upload_pdf(file_path):
    with open(file_path, "rb") as f:
        content = f.read()
        filename = os.path.basename(file_path)
        uploaded_file = client.files.upload(
            file={"file_name": filename, "content": content},
            purpose="ocr",
        )
        signed_url = client.files.get_signed_url(file_id=uploaded_file.id)
        return signed_url.url
    
def upload_pdf_from_url(url: str):
    local_path = download_file(url)
    return upload_pdf(local_path)

def process_ocr(document_source):
    ocr_result = client.ocr.process(
        model="mistral-ocr-latest",
        document=document_source,
        include_image_base64=True
    )
    markdown_text = concat_ocr_markdown(ocr_result)
    return {
        "markdown": markdown_text,
        "document_source": document_source
    }

def concat_ocr_markdown(ocr_response) -> str:
    all_pages = []
    for page in ocr_response.pages:
        # page là OCRPageObject
        md = getattr(page, "markdown", "")
        all_pages.append(md.strip())

    return "\n\n".join(all_pages)