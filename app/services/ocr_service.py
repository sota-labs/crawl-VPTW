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

    async def download_file(self, url: str) -> str:
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

        
    async def upload_pdf_from_url(self, url: str) -> str:
        try:
            local_path = await self.download_file(url)
            return await self.upload_pdf(local_path)
        except Exception as e:
            return str(e)

    async def run_ocr_for_items(self, items) -> list[dict]:
        async def ocr_task(item):
            try:
                async with self.semaphore:
                    document_source = {
                        "type": "document_url",
                        "document_url": item["source_url"]
                    }
                    ocr = await self.process_ocr(document_source)
                    return {**item, "content": ocr["ocr_result"]}
            except Exception as e:
                return {**item, "error": str(e)}

        tasks = [ocr_task(item) for item in items]
        results = await asyncio.gather(*tasks)
        return results
    