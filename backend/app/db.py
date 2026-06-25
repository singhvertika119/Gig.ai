from collections.abc import AsyncGenerator

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

_mongo_client: AsyncIOMotorClient | None = None
_sql_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_mongo_client() -> AsyncIOMotorClient:
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(settings.mongodb_uri)
    return _mongo_client


def get_database() -> AsyncIOMotorDatabase:
    return get_mongo_client()[settings.mongodb_db]


def get_sql_engine() -> AsyncEngine:
    global _sql_engine
    if _sql_engine is None:
        # Async engine for SQLAlchemy-backed models and features.
        _sql_engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
        )
    return _sql_engine


async def get_sql_session() -> AsyncGenerator[AsyncSession, None]:
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            get_sql_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    async with _async_session_factory() as session:
        yield session


async def close_mongo_client() -> None:
    global _mongo_client
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None


async def close_sql_engine() -> None:
    global _sql_engine, _async_session_factory
    if _sql_engine is not None:
        await _sql_engine.dispose()
        _sql_engine = None
        _async_session_factory = None
