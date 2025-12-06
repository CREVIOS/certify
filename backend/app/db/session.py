"""Database session management with connection pooling."""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from loguru import logger
from uuid import uuid4

from app.core.config import settings

# Convert PostgreSQL URL to async version
DATABASE_URL = settings.DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://')

# Create async engine with pgbouncer compatibility
engine = create_async_engine(
    DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    connect_args={
        # Disable prepared statements so pgbouncer (transaction/statement mode) won't choke
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        # Generate unique names if the driver prepares anyway
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
    },
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for models
Base = declarative_base()


async def get_db() -> AsyncSession:
    """
    Dependency for getting database session.

    Yields:
        AsyncSession: Database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database - create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")


async def close_db():
    """Close database connections."""
    await engine.dispose()
    logger.info("Database connections closed")
