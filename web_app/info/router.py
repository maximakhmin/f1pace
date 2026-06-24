from fastapi import APIRouter
from info.schemas import TyreSchema, TrackStatusSchema
from db import get_db
from typing import List
from fastapi import Depends, HTTPException, status
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


logger = logging.getLogger("Server Info")

router = APIRouter(
    prefix="/info",
    tags=["Info"]
)

@router.get(
    "/tyres", 
    response_model=List[TyreSchema],
    summary="Получить справочную информацию по шинам (info)",
    status_code=status.HTTP_200_OK,
)
async def get_tyres(db: AsyncSession = Depends(get_db)):
    logger.info("Получен запрос на список типов шин")
    try:
        result = await db.execute(text("SELECT id, name, color FROM tyres ORDER BY id"))
        rows = result.mappings().all()
        logger.info(f"Успешно возвращено {len(rows)} типов шин")
        return rows
    except Exception as e:
        logger.exception(f"Ошибка при получении типов шин: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )


# 4. Получение статусов трека
@router.get(
    "/track-statuses", 
    response_model=List[TrackStatusSchema],
    summary="Получить справочную информацию по статусам (info)",
    status_code=status.HTTP_200_OK,
)
async def get_track_statuses(db: AsyncSession = Depends(get_db)):
    logger.info("Получен запрос на список статусов трека")
    try:
        result = await db.execute(text("SELECT id, name, color FROM track_statuses ORDER BY id"))
        rows = result.mappings().all()
        logger.info(f"Успешно возвращено {len(rows)} статусных кодов трека")
        return rows
    except Exception as e:
        logger.exception(f"Ошибка при получении статусов трека: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )