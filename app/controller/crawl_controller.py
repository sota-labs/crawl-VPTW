import os
from fastapi import APIRouter, Depends, HTTPException
from app.schemas.res import Decrees
from app.services.ocr_service import OCRService
from app.services.crawl_service import CrawlService

router = APIRouter()

def get_ocr_service() -> OCRService:
    return OCRService(api_key=os.getenv("MISTRAL_API_KEY"), model="mistral-ocr-latest")


@router.get(
    "/crawl",
)
async def crawl(
    ocr_service: OCRService = Depends(get_ocr_service)
):
    service = CrawlService(ocr_service)
    return await service.crawl_all(os.getenv("START_URL"))