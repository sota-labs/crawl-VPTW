import os
from fastapi import APIRouter, Depends

from app.services.ocr_service import OCRService
from app.services import get_ocr_service
from app.services.crawl_service import CrawlService, CrawlerServiceV2



router = APIRouter()

@router.get(
    "/crawl",
)
async def crawl(
    ocr_service: OCRService = Depends(get_ocr_service)
):
    # service = CrawlService(ocr_service, max_concurrency=10)
    async with CrawlerServiceV2(ocr_service) as crawler:
        return await crawler.crawl_all()