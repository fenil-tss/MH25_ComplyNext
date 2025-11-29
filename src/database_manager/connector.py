from config import Config
from urllib.parse import quote_plus
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy import create_engine


encoded_password = quote_plus(Config.PG_PASSWORD)
# Create the database connection manager
db_uri = f"postgresql://{Config.PG_USER}:{encoded_password}@{Config.PG_HOST}:{Config.PG_PORT}/{Config.PG_DATABASE}"
db_engine = create_engine(
    db_uri, 
    pool_size=4,
    max_overflow=0, 
    pool_pre_ping=True, 
    connect_args={
        "connect_timeout": 10, 
        # "options": "-csearch_path=eas"
    }
)
session_maker = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=db_engine))