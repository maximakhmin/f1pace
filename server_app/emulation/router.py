from fastapi import APIRouter
from emulation.schemas import StartEmulationRequest, EmulationStatusShema
from historical.schemas import SessionSchema
from db import get_db, get_current_session_id, set_current_session_id
from typing import List
from fastapi import Depends, HTTPException, status
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import threading
import os
import asyncio
from emulation.emulate import run_live_emulation
from emulation.process_real_time_data import watch_file
from typing import Optional
from emulation.session import Session


logger = logging.getLogger("Server Emulation")

router = APIRouter(
    prefix="/emulation",
    tags=["emulation"]
)

set_current_session_id(None)
IS_EMULATION_RUNNING: bool = False
EMULATION_THREAD: Optional[threading.Thread] = None
THREAD_LOOP: Optional[asyncio.AbstractEventLoop] = None
MAIN_EMULATION_FUTURE: Optional[asyncio.Future] = None


def thread_worker(session_filename: str, speed: float):
    global IS_EMULATION_RUNNING, CURRENT_SESSION_ID, THREAD_LOOP, MAIN_EMULATION_TASK
    
    THREAD_LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(THREAD_LOOP)
    
    logger.info("[Поток] Запущен Event Loop для эмуляции.")
    
    try:
        session = Session(speed)

        session_filename = 'emulation/testing_data/' + session_filename

        real_time_filename = "real_time.txt"
        if os.path.exists(real_time_filename):
            os.remove(real_time_filename)
        # Оборачиваем gather в явную Task, чтобы её можно было отменить извне
        MAIN_EMULATION_FUTURE = asyncio.gather(
            watch_file(real_time_filename, session),
            run_live_emulation(session_filename, real_time_filename, speed)
        )
        
        # 2. Передаем фьючерс напрямую в run_until_complete. 
        # Это заблокирует поток до завершения или отмены обеих функций.
        THREAD_LOOP.run_until_complete(MAIN_EMULATION_FUTURE)
        
    except asyncio.CancelledError:
        logger.info("[Поток] Главная задача эмуляции была отменена.")
    except Exception as e:
        logger.error(f"[Поток] Ошибка в Event Loop: {str(e)}")
    finally:
        THREAD_LOOP.run_until_complete(session.close())
        THREAD_LOOP.close()
        THREAD_LOOP = None
        MAIN_EMULATION_TASK = None
        IS_EMULATION_RUNNING = False
        set_current_session_id(None)
        logger.info("[Поток] Поток завершил работу, loop закрыт, блокировки сняты.")
    

@router.get(
    "/status", 
    summary="Получить текущий статус эмуляции",
    response_model=EmulationStatusShema,
    status_code=status.HTTP_200_OK,
)
async def get_emulation_status():
    logger.info(f"Возвращена информация о текущем статусе эмуляции")
    return {
        "is_running": IS_EMULATION_RUNNING,
        "current_session_id": get_current_session_id()
    }


@router.post(
    "/start",
    summary="Начать эмуляцию сессии по id и скорости"
)
async def start_emulation(session_id: int, speed: float = 1.0, db: AsyncSession = Depends(get_db)):
    global IS_EMULATION_RUNNING, EMULATION_THREAD
    
    if IS_EMULATION_RUNNING:
        raise HTTPException(status_code=400, detail="Эмуляция уже запущена.")
        
    # Ищем имя файла в БД
    query = text("SELECT file_name FROM emulated_sessions WHERE session_id = :session_id")
    result = await db.execute(query, {"session_id": session_id})
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Сессия не найдена.")
    file_name = row[0]
    
    IS_EMULATION_RUNNING = True
    set_current_session_id(session_id)
    
    # Запускаем функцию-воркер в отдельном системном потоке
    EMULATION_THREAD = threading.Thread(
        target=thread_worker,
        kwargs={"session_filename": file_name, "speed": speed},
        daemon=True
    )
    EMULATION_THREAD.start()
    
    return {"message": f"Эмуляция сессии {session_id} изолирована в отдельном потоке."}


@router.post(
    "/stop",
    summary="Остановить эмуляцию сессии"
)
async def stop_emulation():
    global EMULATION_THREAD, THREAD_LOOP, MAIN_EMULATION_FUTURE, IS_EMULATION_RUNNING
    
    if not IS_EMULATION_RUNNING or THREAD_LOOP is None:
        return {"message": "Нет активных эмуляций для остановки."}
        
    logger.info("Инициирована безопасная остановка задач эмуляции...")
    
    # Отменяем фьючерс gather. Это автоматически по цепочке 
    # пошлет CancelledError внутрь watch_file и run_live_emulation
    if MAIN_EMULATION_FUTURE and not MAIN_EMULATION_FUTURE.done():
        THREAD_LOOP.call_soon_threadsafe(MAIN_EMULATION_FUTURE.cancel)
        
    # Даем корутинам закрыть транзакции в бд и тушим сам loop
    def stop_loop():
        if THREAD_LOOP and THREAD_LOOP.is_running():
            THREAD_LOOP.stop()

    THREAD_LOOP.call_soon_threadsafe(stop_loop)
    
    EMULATION_THREAD = None
    
    return {"message": "Сигнал отмены отправлен. База данных освобождается."}



# 2. Получение всех сессий
@router.get(
    "/sessions",
    response_model=List[SessionSchema],
    summary="Получить все сессии с записанной эмуляцией",
    status_code=status.HTTP_200_OK,
)
async def get_all_sessions(db: AsyncSession = Depends(get_db)):
    logger.info(f"Получен запрос на список сессий с записанной эмуляцией")
    
    base_query = """
        SELECT s.id, e.year, e.round, st.name as session_type, 
               st.id as session_type_id, t.country, t.circuit_name 
        FROM sessions s
        JOIN events e ON s.event_id = e.id 
        JOIN tracks t ON e.track_id = t.id
        JOIN session_types st ON s.session_type = st.id
        where s.id in (select session_id from emulated_sessions es )
    """
        
    try:
        result = await db.execute(text(base_query))
        rows = result.mappings().all()
        logger.info(f"Успешно возвращено {len(rows)} сессий с записанной эмуляцией")
        return rows
        
    except Exception as e:
        logger.exception(f"Ошибка при получении списка сессий с записанной эмуляцией: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )