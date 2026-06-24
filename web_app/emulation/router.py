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


logger = logging.getLogger("Server Emulation")

router = APIRouter(
    prefix="/emulation",
    tags=["emulation"]
)

set_current_session_id(None)
IS_EMULATION_RUNNING: bool = False
EMULATION_THREAD: Optional[threading.Thread] = None
THREAD_LOOP: Optional[asyncio.AbstractEventLoop] = None

# 1. Статус
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

def thread_worker(session_filename: str, speed: float):
    global IS_EMULATION_RUNNING, THREAD_LOOP
    
    # 1. Создаем и устанавливаем НОВЫЙ асинхронный цикл для этого потока
    THREAD_LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(THREAD_LOOP)
    
    logger.info(f"[Поток] Запущен новый Event Loop для эмуляции {session_filename}")
    
    try:
        session_filename = 'web_app/emulation/testing_data/' + session_filename

        real_time_filename = "web_app/real_time.txt"
        if os.path.exists(real_time_filename):
            os.remove(real_time_filename)
        # 2. Группируем ваши две асинхронные функции в единую задачу
        # asyncio.gather запустит их параллельно внутри этого потока
        main_task = asyncio.gather(
            watch_file(real_time_filename, speed),
            run_live_emulation(session_filename, real_time_filename, speed)
        )
        
        # 3. Запускаем цикл и передаем ему управление (поток заблокируется тут до завершения)
        THREAD_LOOP.run_until_complete(main_task)
        
    except asyncio.CancelledError:
        logger.info("[Поток] Асинхронные задачи эмуляции были отменены.")
    except Exception as e:
        logger.error(f"[Поток] Ошибка внутри Event Loop эмуляции: {str(e)}")
    finally:
        # Очищаем ресурсы при выходе
        THREAD_LOOP.close()
        THREAD_LOOP = None
        IS_EMULATION_RUNNING = False
        set_current_session_id(None)
        logger.info("[Поток] Поток эмуляции завершил работу, loop закрыт.")
    


@router.post(
    "/emulation/start",
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


# Ручка остановки
@router.post(
    "/emulation/stop",
    summary="Остановить эмуляцию сессии"
)
async def stop_emulation():
    global EMULATION_THREAD, THREAD_LOOP, IS_EMULATION_RUNNING
    
    if not IS_EMULATION_RUNNING or THREAD_LOOP is None:
        return {"message": "Нет активной эмуляции для остановки."}
        
    logger.info("Остановка асинхронных задач в фоновом потоке...")
    
    # КЛЮЧЕВОЙ МОМЕНТ:
    # Так как мы находимся в основном потоке FastAPI, мы не можем просто сказать loop.stop().
    # Мы используем call_soon_threadsafe, чтобы безопасно из основного потока дать команду 
    # фоновому циклу остановить все свои запущенные таски.
    THREAD_LOOP.call_soon_threadsafe(THREAD_LOOP.stop)
    
    # Зануляем объекты, поток сам допишет блок finally и очистит переменные состояния
    EMULATION_THREAD = None
    
    return {"message": "Команда на остановку отправлена в фоновый поток."}



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