import os
from pathlib import Path
from mistralai import Mistral
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
api_key = "joqMh4RpBz5YVBiPOTHPlbCPvt3ZDylA"
client = Mistral(api_key=api_key)

def upload_pdf(file_path):
    """Upload a PDF file to Mistral"""
    with open(file_path, "rb") as f:
        content = f.read()
        filename = os.path.basename(file_path)
        uploaded_file = client.files.upload(
            file={"file_name": filename, "content": content},
            purpose="ocr",
        )
        signed_url = client.files.get_signed_url(file_id=uploaded_file.id)
        return signed_url.url

def process_ocr(document_source):
    """Process document with Mistral OCR"""
    return client.ocr.process(
        model="mistral-ocr-latest",
        document=document_source,
        include_image_base64=True
    )
signed_url = upload_pdf("C:/Users/Lenovo/Downloads/VanBanGoc_220.2025.ND-CP.pdf")
document_source = {"type": "document_url", "document_url": signed_url}
        
# Process with OCR
ocr_response = process_ocr(document_source)
print("OCR Response:", ocr_response.pages)