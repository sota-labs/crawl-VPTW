from mistralai import Mistral


class OCRClient:
    def __init__(self, api_key, model="mistral-ocr-latest"):
        self.client = Mistral(api_key=api_key)
        self.model = model

    def from_url(self, image_url: str):
        ocr_result = self.client.ocr.process(
            model=self.model,
            document={"type": "image_url", "image_url": image_url},
            include_image_base64=True,
        )
        markdown_text = self.concat_ocr_markdown(ocr_result)
        return markdown_text

    def concat_ocr_markdown(self, ocr_response) -> str:
        all_pages = []
        for page in ocr_response.pages:
            # page là OCRPageObject
            md = getattr(page, "markdown", "")
            all_pages.append(md.strip())

        return "\n\n".join(all_pages)
