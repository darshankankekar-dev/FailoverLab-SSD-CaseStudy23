import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy import select
from .config import settings
from .models import Base, RegionalMetadataEntity

logger = logging.getLogger("region.database")

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initializes tables and seeds regional metadata."""
    logger.info(f"Initializing database for region '{settings.region_id}' ({settings.region_name})...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            res = await session.execute(
                select(RegionalMetadataEntity).where(RegionalMetadataEntity.id == 1)
            )
            meta = res.scalar_one_or_none()
            if not meta:
                is_active = (settings.initial_role.upper() == "ACTIVE")
                meta = RegionalMetadataEntity(
                    id=1,
                    region_id=settings.region_id,
                    region_name=settings.region_name,
                    cloud_zone=settings.cloud_zone,
                    role=settings.initial_role.upper(),
                    health="HEALTHY",
                    accepts_writes=is_active,
                    fencing_epoch=settings.initial_epoch,
                    is_fenced=False,
                )
                session.add(meta)
                logger.info(f"Seeded metadata for {settings.region_name}: Role={meta.role}, AcceptsWrites={meta.accepts_writes}, Epoch={meta.fencing_epoch}")

    logger.info("Regional database initialization completed.")

