import asyncio
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import os
from pgvector.sqlalchemy import Vector



Base = declarative_base()
Base.metadata.schema = "home_assistant"

def _get_database_url() -> str:
    """Resolve database URL from env vars used across the project."""
    db_url = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("POSTGRES_URL (or DATABASE_URL) is not set.")
    return db_url


def _get_session_factory() -> async_sessionmaker:
    """Create an async session factory compatible with asyncpg."""
    engine = create_async_engine(_get_database_url())
    return async_sessionmaker(bind=engine, expire_on_commit=False)

class ChatLog(Base):
    __tablename__ = "chat_log"
    __table_args__ = (
        sa.Index(
            "idx_chat_log_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        sa.Index("idx_chat_log_id", "id"),
    )

    id = sa.Column(sa.Integer, primary_key=True, index=True)
    client_id = sa.Column(sa.String, index=True)
    message = sa.Column(sa.Text)
    response = sa.Column(sa.Text)
    embedding = sa.Column(Vector(1536), nullable=True)
    timestamp = sa.Column(sa.DateTime, server_default=sa.func.now(), index=True)

class ClientFact(Base):
    __tablename__ = "client_fact"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    client_id = sa.Column(sa.String, index=True)
    fact = sa.Column(sa.Text)
    timestamp = sa.Column(sa.DateTime, server_default=sa.func.now(), index=True)

async def _init_models():
    async with create_async_engine(_get_database_url()).begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)

async def add_chat_log(client_id, message, response, embedding=None):
    """ Add a chat log entry to the database. """
    await _init_models()
    chat_log_entry = ChatLog(
        client_id=client_id,
        message=message,
        response=response,
        embedding=embedding,
    )
    Session = _get_session_factory()
    async with Session() as session:
        session.add(chat_log_entry)
        await session.commit()
        await session.refresh(chat_log_entry)
    return chat_log_entry

async def add_client_fact(client_id, fact):
    """ Add a client fact entry to the database. """
    await _init_models()
    client_fact_entry = ClientFact(
        client_id=client_id,
        fact=fact,
    )
    Session = _get_session_factory()
    async with Session() as session:
        session.add(client_fact_entry)
        await session.commit()
        await session.refresh(client_fact_entry)
    return client_fact_entry

async def get_recent_chat_logs(client_id, limit=10):
    """ Retrieve recent chat logs for a given client. """
    Session = _get_session_factory()
    async with Session() as session:
        result = await session.execute(
            sa.select(sa.literal("User Message: ") + ChatLog.message, sa.literal("Response: ") + ChatLog.response).where(ChatLog.client_id == client_id).order_by(ChatLog.timestamp.desc()).limit(limit)
        )
        return result.scalars().all()
    
async def get_client_facts(client_id, limit=10):
    """ Retrieve recent client facts for a given client. """
    Session = _get_session_factory()
    async with Session() as session:
        result = await session.execute(
            sa.select(ClientFact).where(ClientFact.client_id == client_id).order_by(ClientFact.timestamp.desc()).limit(limit)
        )
        return result.scalars().all()


if __name__ == "__main__":
    asyncio.run(add_client_fact("test_client", "The sky is blue."))
    asyncio.run(add_chat_log("test_client", "What color is the sky?", "The sky is blue.", embedding=[0.0]*1536))
