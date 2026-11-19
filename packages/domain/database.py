from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://rizoma@localhost:5432/rizoma")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    from .models import Base
    with engine.connect() as conn:
        # Habilitar extensiones necesarias
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        conn.commit()
    
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
