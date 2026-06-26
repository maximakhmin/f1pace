from fastapi import APIRouter
from live.schemas import TrackMapSchema, RealTimeLapsSchema, TrackCornerSchema, LiveTimestampSchema, RealTimeMessageSchema, RealTimePositionSchema
from live.predict import predict_future_laps
from db import get_db, get_current_session_id
from typing import List
from fastapi import Depends, HTTPException, status, WebSocket, WebSocketDisconnect
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import asyncio


logger = logging.getLogger("Server Live")

router = APIRouter(
    prefix="/live",
    tags=["Live"]
)


@router.get(
    "/positions", 
    response_model=List[RealTimePositionSchema],
    summary="Получить текущие координаты болидов на трассе",
    status_code=status.HTTP_200_OK
)
async def get_real_time_positions(delay_seconds: int = 10, db: AsyncSession = Depends(get_db)):
    current_session_id = get_current_session_id()
    logger.info(f"Получен запрос на live-координаты. Используется внутренняя сессия: {current_session_id}")
    
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
        result = await db.execute(query_select, {"session_id": current_session_id, "delay_seconds": delay_seconds})
        rows = result.mappings().all()
        
        # Выполняем DELETE (динамически передаем delay_seconds для гибкости)
        delete_result = await db.execute(query_delete, {"delay_seconds": delay_seconds})
        await db.commit()
        
        logger.info(f"Успешно возвращено {len(rows)} точек позиционирования для сессии {current_session_id}, Удалено устаревших строк: {delete_result.rowcount}")
        return rows
        
    except Exception as e:
        await db.rollback()
        logger.exception(f"Ошибка при получении live-координат для сессии {current_session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )
    

@router.websocket("/positions/ws")
async def websocket_real_time_positions(
    websocket: WebSocket,
    delay_seconds: int = 10,
    refresh_interval: float = 1.0,  # Частота обновления данных (в секундах)
    db: AsyncSession = Depends(get_db)
):
    # 1. Принимаем WebSocket соединение
    await websocket.accept()
    current_session_id = get_current_session_id()
    logger.info(f"WebSocket подключение установлено. Сессия: {current_session_id}, delay: {delay_seconds}s")
    
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
            driver_number, abbr, color, time_utc, status, x, y, z
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
        # 2. Запускаем бесконечный цикл отправки данных
        while True:
            # Выполняем SELECT
            result = await db.execute(query_select, {"session_id": current_session_id, "delay_seconds": delay_seconds})
            rows = result.mappings().all()
            
            # Выполняем CLEANUP (DELETE)
            delete_result = await db.execute(query_delete)
            await db.commit()
            
            # Конвертируем JSON/DateTime в строки/примитивы, чтобы Pydantic/FastAPI корректно проглотил
            # Используем ваш существующий RealTimePositionSchema для валидации каждой строки
            validated_positions = [
                RealTimePositionSchema.model_validate(dict(row)).model_dump(mode="json")
                for row in rows
            ]
            
            # Отправляем пачку координат клиенту (Streamlit)
            await websocket.send_json(validated_positions)
            
            # Засыпаем на указанный интервал (например, 1 секунда), чтобы не спамить базу данных
            await asyncio.sleep(refresh_interval)
            
    except WebSocketDisconnect:
        logger.info(f"Клиент отключился от WebSocket (сессия: {current_session_id})")
        
    except Exception as e:
        await db.rollback()
        logger.exception(f"Ошибка в WebSocket-стриме координат для сессии {current_session_id}: {str(e)}")
        # Закрываем соединение с кодом ошибки, если что-то пошло не так
        await websocket.close(code=1011)
    

@router.get(
    "/track-corners", 
    response_model=List[TrackCornerSchema],
    summary="Получить координаты и параметры поворотов трассы для текущей сессии",
    status_code=status.HTTP_200_OK
)
async def get_track_corners(db: AsyncSession = Depends(get_db)):
    current_session_id = get_current_session_id()
    logger.info(f"Получен запрос на конфигурацию поворотов для внутренней сессии: {current_session_id}")
    
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
        result = await db.execute(query, {"session_id": current_session_id})
        rows = result.mappings().all()
        
        if not rows:
            logger.warning(f"Повороты трассы для сессии {current_session_id} не найдены")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Track corners for session {current_session_id} not found"
            )
            
        logger.info(f"Успешно возвращено {len(rows)} поворотов для сессии {current_session_id}")
        return rows
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Ошибка при получении поворотов трассы для сессии {current_session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )
    

@router.get(
    "/track-map", 
    response_model=List[TrackMapSchema],
    summary="Получить координаты для карты трассы для текущей сессии",
    status_code=status.HTTP_200_OK
)
async def get_track_map(db: AsyncSession = Depends(get_db)):
    current_session_id = get_current_session_id()
    logger.info(f"Получен запрос на карту трассы для внутренней сессии: {current_session_id}")
    
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
        result = await db.execute(query, {"session_id": current_session_id})
        rows = result.mappings().all()
        
        if not rows:
            logger.warning(f"Карта трассы для сессии {current_session_id} не найдены")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Track map for session {current_session_id} not found"
            )
            
        logger.info(f"Успешно возвращено {len(rows)} точек для карты трассы session_id={current_session_id}")
        return rows
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Ошибка при получении карты трассы для сессии {current_session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )


@router.get(
    "/messages", 
    response_model=List[RealTimeMessageSchema],
    summary="Получить хронологический лог сообщений гонки",
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
    summary="Получить текущее внутреннее время трансляции сервера",
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


@router.websocket("/current-live-timestamp/ws")
async def websocket_current_live_timestamp(
    websocket: WebSocket,
    refresh_interval: float = 0.5
):
    logger.info(f"Получен websocket /current-live-timestamp/ws с интервалом {refresh_interval}s")
    await websocket.accept()
    
    async for db in get_db(): 
        try:
            while True:
                query = text("SELECT time FROM real_time LIMIT 1")
                result = await db.execute(query)
                row = result.mappings().first()
                
                if row:
                    validated_data = LiveTimestampSchema.model_validate(dict(row)).model_dump(mode="json")
                    await websocket.send_json(validated_data)
                
                # Используем переданную частоту в asyncio.sleep
                await asyncio.sleep(refresh_interval)
        except WebSocketDisconnect:
            logger.info("Клиент отключился от вебсокета времени")
            break
        except Exception as e:
            logger.exception(f"Ошибка в цикле вебсокета времени: {e}")
            break


@router.get(
    "/laps", 
    response_model=List[RealTimeLapsSchema],
    summary="Получить времена кругов с предсказаниями",
    status_code=status.HTTP_200_OK
)
async def get_real_time_laps(number_of_predictions: int = 5):
    current_session_id = get_current_session_id()
    logger.info(f"Получен запрос на live времена кругов. Количество предсказаний: {number_of_predictions}")
     
    try:
        result_df = predict_future_laps(current_session_id, number_of_predictions)
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