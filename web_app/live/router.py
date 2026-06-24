from fastapi import APIRouter
from live.schemas import TrackMapSchema, RealTimeLapsSchema, TrackCornerSchema, LiveTimestampSchema, RealTimeMessageSchema, RealTimePositionSchema
from live.predict import predict_future_laps
from db import get_db, CURRENT_SESSION_ID
from typing import List
from fastapi import Depends, HTTPException, status
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


logger = logging.getLogger("Server Live")

router = APIRouter(
    prefix="/live",
    tags=["Live"]
)


@router.get(
    "/positions", 
    response_model=List[RealTimePositionSchema],
    summary="Получить текущие координаты болидов на трассе (live)",
    status_code=status.HTTP_200_OK
)
async def get_real_time_positions(delay_seconds: int = 10, db: AsyncSession = Depends(get_db)):
    logger.info(f"Получен запрос на live-координаты. Используется внутренняя сессия: {CURRENT_SESSION_ID}")
    
    query_select = text("""
        WITH target_time AS (
            SELECT time AS t_time FROM real_time LIMIT 1
        ),
        ranked_positions AS (
            SELECT 
                rtp.driver_number, 
                d.abbr, 
                si.color, 
                rtp.time_utc, 
                rtp.status, 
                rtp.x, 
                rtp.y, 
                rtp.z,
                ROW_NUMBER() OVER (
                    PARTITION BY rtp.driver_number 
                    ORDER BY ABS(EXTRACT(EPOCH FROM rtp.time_utc) - EXTRACT(EPOCH FROM (tt.t_time - :delay_seconds * INTERVAL '1 second'))) ASC
                ) as rn
            FROM real_time_position rtp
            CROSS JOIN target_time tt
            LEFT JOIN style_info si ON si.number = rtp.driver_number 
            LEFT JOIN drivers d ON si.driver_id = d.id
            WHERE si.session_id = :session_id
        )
        SELECT 
            driver_number, 
            abbr, 
            color, 
            time_utc, 
            status, 
            x, 
            y, 
            z,
            rn
        FROM ranked_positions
        WHERE rn = 1;
    """)

    query_delete = text("""
        WITH target_time AS (
            SELECT time AS t_time FROM real_time LIMIT 1
        )
        DELETE FROM real_time_position rtp
        USING target_time tt
        WHERE rtp.time_utc < (tt.t_time - 30 * INTERVAL '1 second')
    """)
    
    try:
        # Выполняем SELECT
        result = await db.execute(query_select, {"session_id": CURRENT_SESSION_ID, "delay_seconds": delay_seconds})
        rows = result.mappings().all()
        
        # Выполняем DELETE (динамически передаем delay_seconds для гибкости)
        delete_result = await db.execute(query_delete, {"delay_seconds": delay_seconds})
        await db.commit()
        
        logger.info(f"Успешно возвращено {len(rows)} точек позиционирования для сессии {CURRENT_SESSION_ID}, Удалено устаревших строк: {delete_result.rowcount}")
        return rows
        
    except Exception as e:
        await db.rollback()
        logger.exception(f"Ошибка при получении live-координат для сессии {CURRENT_SESSION_ID}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )
    

@router.get(
    "/track-corners", 
    response_model=List[TrackCornerSchema],
    summary="Получить координаты и параметры поворотов трассы для текущей сессии (live)",
    status_code=status.HTTP_200_OK
)
async def get_track_corners(db: AsyncSession = Depends(get_db)):
    logger.info(f"Получен запрос на конфигурацию поворотов для внутренней сессии: {CURRENT_SESSION_ID}")
    
    # Ваш SQL-запрос с подзапросом, адаптированный под bind-параметр :session_id
    query = text("""
        SELECT x, y, angle, number, distance, rotation 
        FROM track_corners 
        WHERE event_id = (
            SELECT e.id FROM events e
            JOIN sessions s ON e.id = s.event_id
            WHERE s.id = :session_id 
            LIMIT 1
        )
        ORDER BY number
    """)
    
    try:
        result = await db.execute(query, {"session_id": CURRENT_SESSION_ID})
        rows = result.mappings().all()
        
        if not rows:
            logger.warning(f"Повороты трассы для сессии {CURRENT_SESSION_ID} не найдены")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Track corners for session {CURRENT_SESSION_ID} not found"
            )
            
        logger.info(f"Успешно возвращено {len(rows)} поворотов для сессии {CURRENT_SESSION_ID}")
        return rows
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Ошибка при получении поворотов трассы для сессии {CURRENT_SESSION_ID}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )
    

@router.get(
    "/track-map", 
    response_model=List[TrackMapSchema],
    summary="Получить координаты для карты трассы для текущей сессии (live)",
    status_code=status.HTTP_200_OK
)
async def get_track_map(db: AsyncSession = Depends(get_db)):
    logger.info(f"Получен запрос на карту трассы для внутренней сессии: {CURRENT_SESSION_ID}")
    
    # Ваш SQL-запрос с подзапросом, адаптированный под bind-параметр :session_id
    query = text("""
        SELECT x, y FROM track_map 
        WHERE event_id = (
            SELECT e.id FROM events e
            JOIN sessions s ON e.id = s.event_id
            WHERE s.id = :session_id
            LIMIT 1
        )
        order by idx
    """)
    
    try:
        result = await db.execute(query, {"session_id": CURRENT_SESSION_ID})
        rows = result.mappings().all()
        
        if not rows:
            logger.warning(f"Карта трассы для сессии {CURRENT_SESSION_ID} не найдены")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Track map for session {CURRENT_SESSION_ID} not found"
            )
            
        logger.info(f"Успешно возвращено {len(rows)} точек для карты трассы session_id={CURRENT_SESSION_ID}")
        return rows
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Ошибка при получении карты трассы для сессии {CURRENT_SESSION_ID}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )


@router.get(
    "/messages", 
    response_model=List[RealTimeMessageSchema],
    summary="Получить хронологический лог сообщений гонки (live)",
    status_code=status.HTTP_200_OK
)
async def get_real_time_messages(db: AsyncSession = Depends(get_db)):
    logger.info("Получен запрос на чтение лога сообщений гонки")
    
    # Ваш SQL-запрос с сортировкой по времени
    query = text("""
        SELECT time_utc, lap, message 
        FROM real_time_messages 
        ORDER BY time_utc DESC
    """)
    
    try:
        result = await db.execute(query)
        rows = result.mappings().all()
        
        logger.info(f"Успешно возвращено {len(rows)} сообщений гонки")
        return rows
        
    except Exception as e:
        logger.exception(f"Ошибка при получении сообщений гонки: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )




@router.get(
    "/current-live-timestamp", 
    response_model=LiveTimestampSchema,
    summary="Получить текущее внутреннее время трансляции сервера (live)",
    status_code=status.HTTP_200_OK
)
async def get_current_live_timestamp(db: AsyncSession = Depends(get_db)):
    # Просто логируем и отдаем значение нашей глобальной переменной
    logger.info(f"Запрошено текущее live-время сервера")

    query = text("""
        SELECT time FROM real_time LIMIT 1
    """)
    
    try:
        result = await db.execute(query)
        rows = result.mappings().first()
        
        logger.info(f"Успешно возвращено текущее live-время сервера")
        return rows
        
    except Exception as e:
        logger.exception(f"Ошибка при получении текущего live-время сервера: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )
    


@router.get(
    "/laps", 
    response_model=List[RealTimeLapsSchema],
    summary="Получить времена кругов с предсказаниями (live)",
    status_code=status.HTTP_200_OK
)
async def get_real_time_laps(number_of_predictions: int = 5):
    logger.info(f"Получен запрос на live времена кругов. Количество предсказаний: {number_of_predictions}")
     
    try:
        result_df = predict_future_laps(CURRENT_SESSION_ID, number_of_predictions)
        print(result_df)
        rows = result_df.to_dict(orient='records')
        logger.info(f"Успешно возвращено {len(rows)} live времена кругов")
        return rows
        
    except Exception as e:
        logger.exception(f"Ошибка при получении live времена кругов : {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )