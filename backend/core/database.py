from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config.settings import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    pool_pre_ping=True,
)

# ---- SQLite robustness: WAL mode + busy timeout + FK enforcement ----
# Prevents "database is locked" under concurrent analysis writes/polling.
if "sqlite" in settings.DATABASE_URL:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):  # pragma: no cover
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout=30000;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()
        except Exception:
            pass

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    """Create tables + enforce WAL pragmas. Called from lifespan, init_db.py, start_server.py."""
    # Import models here to ensure all tables are registered before create_all.
    try:
        import backend.models.models  # noqa: F401
    except Exception:
        pass
    Base.metadata.create_all(bind=engine)
    # Enforce WAL on file DBs even if event listener missed (e.g. existing connection).
    if "sqlite" in settings.DATABASE_URL:
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
                conn.exec_driver_sql("PRAGMA busy_timeout=30000;")
        except Exception:
            pass
    return True


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
