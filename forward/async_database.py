from sqlalchemy import MetaData, Table, Column, Integer, String, JSON, DateTime, BINARY
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

meta = MetaData()
StarletteRequest = Table(
    "request",
    meta,
    Column("id", Integer, primary_key=True, index=True),
    Column("time", DateTime),
    Column("method", String),
    Column("url", String),
    Column("headers", JSON),
    Column("params", JSON),
    Column("body", BINARY),
    Column("remote_ip", String),
)


async def get_db_engine(db_url: str) -> AsyncEngine:
    """
    Create a new database engine and create tables.
    """
    engine = create_async_engine(db_url, echo=True)

    async with engine.begin() as conn:
        await conn.run_sync(meta.create_all)
    return engine
