from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
from sqlalchemy import text, create_engine


load_dotenv()
DATABASE_URL_ASYNC = f'postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:5432/f1pace'
engine_async = create_async_engine(DATABASE_URL_ASYNC, echo=True)
AsyncSessionLocal = async_sessionmaker(bind=engine_async, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


DATABASE_URL = f'postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:5432/f1pace'
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


# 3. Функции работы с БД (используем SessionLocal напрямую для простоты)
def get_current_session_id():
    # Открываем обычную сессию
    with SessionLocal() as session:
        query = text("select session_id from current_session_id csi limit 1")
        # Выполняем через session.execute
        cursor = session.execute(query)
        row = cursor.fetchone()
        curr_session_id = row[0] if row else None

    return curr_session_id


def set_current_session_id(new_session_id):
    with SessionLocal() as session:
        query = text("update current_session_id set session_id = :new_session_id")
        session.execute(query, {"new_session_id": new_session_id})
        # У сессии изменения фиксируются через session.commit()
        session.commit()

