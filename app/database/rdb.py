from typing import Optional, Dict, Any
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from app.api.models import Base
from app.config import DEFAULT_DB_PORT_BY_TYPE
from app.database.interface import DatabaseInterface
from app.core.logging import logger

class RDBConnection(DatabaseInterface):
    def __init__(self, config=None):
        self.engine = None
        self.Session = None
        self._session = None
        settings = config or {}
        self.db_type = str(settings.get("DB_TYPE", "")).lower()
        if self.db_type not in {"postgresql", "mysql", "sqlite"}:
            raise ValueError(f"Unsupported relational database type: {self.db_type}")

        db_uri = settings.get("DB_URI")
        db_name = settings.get("DB_NAME", "compugit")
        if db_uri:
            url = make_url(db_uri)
            if url.get_backend_name() != self.db_type:
                raise ValueError(
                    f"DB_URI backend must match DB_TYPE ({self.db_type})"
                )
            if self.db_type == "mysql" and url.drivername == "mysql":
                url = url.set(drivername="mysql+pymysql")
            self.db_url = url if self.db_type == "sqlite" or url.database else url.set(
                database=db_name
            )
        elif self.db_type == "sqlite":
            sqlite_path = settings.get("DB_SQLITE_PATH", "compugit.sqlite3")
            self.db_url = URL.create("sqlite", database=str(sqlite_path))
        else:
            default_port = DEFAULT_DB_PORT_BY_TYPE[self.db_type]
            username = settings.get("DB_USERNAME")
            password = settings.get("DB_PASSWORD")
            if self.db_type == "postgresql":
                username = username or "postgres"
                password = password or "postgres"
            self.db_url = URL.create(
                drivername=(
                    "postgresql+psycopg2"
                    if self.db_type == "postgresql"
                    else "mysql+pymysql"
                ),
                username=username,
                password=password,
                host=settings.get("DB_HOST", "localhost"),
                port=int(settings.get("DB_PORT") or default_port),
                database=db_name,
            )

    @property
    def native(self):
        return self._session

    def execute_sql(self, statement: str, parameters: Optional[Dict[str, Any]] = None):
        if self._session is None:
            raise RuntimeError("Database is not connected")
        return self._session.execute(text(statement), parameters or {})

    def connect(self) -> None:
        try:
            self.engine = create_engine(self.db_url)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self._session = self.Session()
            logger.info("Successfully connected to %s", self.db_type)
        except Exception as e:
            logger.error("%s connection failed: %s", self.db_type, str(e))
            raise

    def disconnect(self) -> None:
        if self._session:
            self._session.close()
        if self.engine:
            self.engine.dispose()
        self._session = None
        self.engine = None
        logger.info("%s connection closed", self.db_type)

    def is_connected(self) -> bool:
        if self.engine:
            try:
                with self.engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                return True
            except SQLAlchemyError:
                return False
        return False
