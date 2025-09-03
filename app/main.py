from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.controller.crawl_controller import router as CrawlController

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(CrawlController)