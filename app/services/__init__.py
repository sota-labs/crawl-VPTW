import os

from app.services.ocr_service import OCRService

def get_ocr_service() -> OCRService:
    return OCRService(api_key=os.getenv("MISTRAL_API_KEY"), model="mistral-ocr-latest", max_concurrency=5)