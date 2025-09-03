import os
from fastapi import APIRouter, Depends, HTTPException
from app.schemas.res import Decrees

router = APIRouter()


@router.post(
    "/crawl",
    response_model=Decrees,
)
async def crawl(
) -> Decrees:
    return Decrees(data=[])