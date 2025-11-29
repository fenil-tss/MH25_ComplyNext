from utils import root_logger
from datetime import datetime
from traceback import format_exc
from sqlalchemy import text, select
from sqlalchemy.exc import IntegrityError
from database_manager.connector import session_maker
from database_manager.models import (
    DeclarativeBase, Document, DocChunk,
)



class DatabaseManager:
    """
    Usage:
    with DatabaseManager() as db:
        for object in objects:
            db.add(object)
        # commit happens automatically on exit
    """
    readonly_fields = [
        "id",
        "added_on"
    ]

    def __init__(self):
        self.logger = root_logger

    def __enter__(self):
        self.session = session_maker()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                self.session.commit()
            else:
                self.session.rollback()
                self.logger.error(f"Transaction rolled back due to exception: {exc_val}", exc_info=True)
        finally:
            self.session.close()

    def validate_connection(self):
        try:
            self.session.execute(text("set search_path to public"))
        except Exception as e:
            self.session.close()
            raise Exception("Cannot continue. Database is not connected") from e


    def add_to_session(self, obj, flush=False):
        try:
            self.session.add(obj)
            if flush:
                self.session.flush()
        except IntegrityError as exception:
            self.logger.error(format_exc())
            raise exception

    def all(self, limit=50, offset=0):
        return self.session.query(self.model).limit(limit).offset(offset).all()
    
    def get_by_id(self, pkey):
        return self.session.get(self.model, pkey)

    def get_by_values(self, filters, limit=10):
        return self.session.query(self.model).filter(**filters).limit(limit).all()

    def update_from_dict(self, obj, mapping):
        mutable_fields = [
            column.name
            for column in obj.__table__.columns
            if column not in self.readonly_fields
        ]

        is_value_updated = False
        for key, value in mapping.items():
            if (key in mutable_fields) and (getattr(obj, key) != value):
                setattr(obj, key, value)
                is_value_updated = True

        # Only creates a UPDATE query if actually something has changed
        if is_value_updated:
            self.add_to_session(obj)
        
        return obj


###################################
## DOCUMENTS
def get_all_existing_documents():
    with DatabaseManager() as db:
        query = select(Document.file_url)
        file_urls = db.session.execute(query).scalars().all()
        return set(file_urls)


def save_document_and_nodes(document, nodes):
    with DatabaseManager() as db:
        document_obj = Document(
            source = document['source'],
            source_url = document['source_url'],
            date = document['date'],
            title = document['title'],
            description = document['description'],
            detail_url = document['detail_url'],
            file_url = document['fileurl'],
            file_path = document['filepath'],
            downloaded_on = document['downloaded_on'],
            parsed_on = datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )
        db.add_to_session(document_obj, flush=True)
        for node in nodes:
            db.add_to_session(
                DocChunk(
                document_id = document_obj.id,
                **node,
            ))
        

# Validates database connection on import
with DatabaseManager() as db:
    db.validate_connection()
    engine = db.session.get_bind()
    DeclarativeBase.metadata.create_all(bind=engine)