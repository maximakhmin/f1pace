from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import os
from dotenv import load_dotenv
import logging

load_dotenv()
DATABASE_URL = f'postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:5432/f1pace'
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


app = FastAPI(title="f1pace API")

logger = logging.getLogger("FastApi")

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


class RaceResultSchema(BaseModel):
    position: int
    classified_position: Optional[str]
    laps: Optional[int]
    time: Optional[float]
    first_name: str
    last_name: str
    team: str
    color: str

    class Config:
        from_attributes = True


class SessionSchema(BaseModel):
    id: int
    year: int
    round: int
    session_type: str
    session_type_id: int
    country: str
    circuit_name: str

    class Config:
        from_attributes = True


class TyreSchema(BaseModel):
    id: int
    name: str
    color: str

    class Config:
        from_attributes = True


class TrackStatusSchema(BaseModel):
    id: int
    name: str
    color: str

    class Config:
        from_attributes = True


class StyleSchema(BaseModel):
    driver_id: int
    abbr: str
    color: str
    linestyle: str
    marker: str

    class Config:
        from_attributes = True


from typing import Optional

class LapSchema(BaseModel):
    driver_id: int
    position: Optional[int]
    lap_number: int
    track_status: int
    lap_time: float
    session_time_end: float
    is_pit_out_lap: bool
    tyre_type: int

    class Config:
        from_attributes = True


@app.get("/results/{session_id}", response_model=List[RaceResultSchema])
async def get_session_results(session_id: int, db: AsyncSession = Depends(get_db)):
    logger.info(f"Получен запрос на результаты сессии. session_id={session_id}")
    
    query = text("""
        SELECT r.position, r.classified_position, r.laps, r.time, 
               d.first_name, d.last_name, si.team, si.color 
        FROM results r
        JOIN drivers d ON r.driver_id = d.id
        JOIN style_info si ON si.driver_id = d.id AND si.session_id = r.session_id
        WHERE r.session_id = :session_id
        ORDER BY r.position
    """)
    
    try:
        result = await db.execute(query, {"session_id": session_id})
        rows = result.mappings().all()
        
        if not rows:
            logger.warning(f"Результаты для сессии {session_id} не найдены в базе данных")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Results for session {session_id} not found"
            )
            
        logger.info(f"Успешно возвращено {len(rows)} строк для сессии {session_id}")
        return rows
        
    except HTTPException:
        raise  # Пробрасываем 404 ошибку дальше без логирования как critical
    except Exception as e:
        logger.exception(f"Ошибка при получении результатов сессии {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )


# 2. Получение всех сессий
@app.get("/sessions", response_model=List[SessionSchema])
async def get_all_sessions(only_races: bool = False, db: AsyncSession = Depends(get_db)):
    logger.info(f"Получен запрос на список сессий. Параметр only_races={only_races}")
    
    base_query = """
        SELECT s.id, e.year, e.round, st.name as session_type, 
               st.id as session_type_id, t.country, t.circuit_name 
        FROM sessions s
        JOIN events e ON s.event_id = e.id 
        JOIN tracks t ON e.track_id = t.id
        JOIN session_types st ON s.session_type = st.id
    """
    
    if only_races:
        base_query += " WHERE s.session_type IN (5, 7)"
        
    try:
        result = await db.execute(text(base_query))
        rows = result.mappings().all()
        logger.info(f"Успешно возвращено {len(rows)} сессий (only_races={only_races})")
        return rows
        
    except Exception as e:
        logger.exception(f"Ошибка при получении списка сессий: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )


# 3. Получение шин
@app.get("/tyres", response_model=List[TyreSchema])
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
@app.get("/track-statuses", response_model=List[TrackStatusSchema])
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
    

@app.get(
    "/styles/{session_id}", 
    response_model=List[StyleSchema],
    summary="Получить стили оформления пилотов для сессии",
    status_code=status.HTTP_200_OK
)
async def get_session_styles(session_id: int, db: AsyncSession = Depends(get_db)):
    logger.info(f"Получен запрос на стили оформления. session_id={session_id}")
    
    # SQL-запрос с использованием безопасного bind-параметра :session_id
    query = text("""
        SELECT si.driver_id, d.abbr, si.color, si.linestyle, si.marker 
        FROM style_info si 
        JOIN drivers d ON si.driver_id = d.id 
        WHERE si.session_id = :session_id 
        ORDER BY si.team DESC, d.id
    """)
    
    try:
        result = await db.execute(query, {"session_id": session_id})
        rows = result.mappings().all()
        
        if not rows:
            logger.warning(f"Стили для сессии {session_id} не найдены")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Styles for session {session_id} not found"
            )
            
        logger.info(f"Успешно возвращено {len(rows)} стилей для сессии {session_id}")
        return rows
        
    except HTTPException:
        raise  # Пробрасываем 404 ошибку без записи в лог как ошибку сервера
    except Exception as e:
        logger.exception(f"Ошибка при получении стилей для сессии {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )
    

@app.get(
    "/laps/{session_id}", 
    response_model=List[LapSchema],
    summary="Получить круги сессии (посимвольный тайминг)",
    status_code=status.HTTP_200_OK
)
async def get_session_laps(
    session_id: int, 
    limit: int = 3000,       # Ограничение: максимум 1000 кругов за раз по умолчанию
    db: AsyncSession = Depends(get_db)
):
    logger.info(f"Получен запрос на круги сессии. session_id={session_id}, limit={limit}")
    
    # SQL-запрос с лимитами и безопасными bind-параметрами
    # Добавлена сортировка по driver_id и lap_number, чтобы данные шли последовательно
    query = text("""
        SELECT driver_id, position, lap_number, track_status, 
               lap_time, session_time_end, is_pit_out_lap, tyre_type 
        FROM laps_cleaned 
        WHERE session_id = :session_id
        ORDER BY driver_id, lap_number
        LIMIT :limit
    """)
    
    try:
        result = await db.execute(
            query, 
            {"session_id": session_id, "limit": limit}
        )
        rows = result.mappings().all()
        
        if not rows:
            logger.warning(f"Круги для сессии {session_id} не найдены")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Laps for session {session_id} not found"
            )
            
        logger.info(f"Успешно возвращено {len(rows)} кругов для сессии {session_id}")
        return rows
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Ошибка при получении кругов для сессии {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )