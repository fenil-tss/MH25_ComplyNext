from sqlalchemy import (
    Column, Integer, Text, Date, DateTime, ForeignKey, BigInteger,
    ARRAY
)
from sqlalchemy.orm import declarative_base
from pgvector.sqlalchemy import Vector
from sqlalchemy import func, Index
from config import Config


DeclarativeBase = declarative_base()

BASEVECTOR = Vector(Config.EMBEDDING_SIZE)


class BaseModel(DeclarativeBase):
    __abstract__ = True

    id = Column(Integer, primary_key=True)

    added_on = Column(DateTime, default=func.now())
    edited_on = Column(DateTime, default=func.now(), onupdate=func.now())

    def json(self):
        return {
            c.name: getattr(self, c.name)
            for c in self.__table__.columns
        }

# ----------------------------------------------------------------------
# documents
# ----------------------------------------------------------------------
class Document(BaseModel):
    __tablename__ = 'documents'

    source = Column(Text)
    source_url = Column(Text)
    date = Column(Date)
    title = Column(Text)
    description = Column(Text, nullable=True)
    detail_url = Column(Text)
    file_url = Column(Text)
    file_path = Column(Text)
    downloaded_on = Column(DateTime)
    parsed_on = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index(
            "idx_documents_file_path",
            "file_path",
            unique=True,
            postgresql_where=(Column("file_path") != None)
        ),
    )


# ----------------------------------------------------------------------
# doc_chunk
# ----------------------------------------------------------------------
class DocChunk(BaseModel):
    __tablename__ = 'doc_chunk'

    id = Column(Integer, primary_key=True)

    # Replaced relationship with FK → documents.id
    document_id = Column(
        BigInteger,
        ForeignKey('documents.id', ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key referencing documents.id"
    )

    category_of_circular = Column(Text)
    entity_type = Column(Text)
    condition = Column(Text)
    action = Column(Text)
    deadline = Column(Text)
    citation = Column(Text)
    expected_outcome = Column(Text)
    source_quote = Column(Text)
    
    category_of_circular_embed = Column(BASEVECTOR)
    entity_type_embed = Column(BASEVECTOR)
    condition_embed = Column(BASEVECTOR)
    
    __table_args__ = (
        Index("idx_doc_chunk_document_id", "document_id"),
    )

# # ----------------------------------------------------------------------
# # company_profile
# # ----------------------------------------------------------------------
# class CompanyProfile(BaseModel):
#     __tablename__ = 'company_profile'

#     company_id = Column(Integer, primary_key=True)

#     company_name = Column(Text)
#     website = Column(Text)
#     scraped_at = Column(DateTime)
#     emails = Column(ARRAY(Text), nullable=True)
#     phones = Column(ARRAY(Text), nullable=True)
#     about_url = Column(Text)
#     about_text = Column(Text)
#     about_embed = Column(BASEVECTOR)
#     created_at = Column(DateTime, server_default=func.now())


# # ----------------------------------------------------------------------
# # company_product
# # ----------------------------------------------------------------------
# class CompanyProduct(BaseModel):
#     __tablename__ = 'company_product'

#     product_id = Column(Integer, primary_key=True)

#     # Replaced relationship with FK → company_profile.id
#     company_id = Column(
#         BigInteger,
#         ForeignKey('company_profile.id', ondelete="CASCADE"),
#         nullable=False,
#         doc="FK referencing company_profile.id"
#     )

#     product_title = Column(Text)
#     product_description = Column(Text)
#     product_url = Column(Text)
#     product_embed = Column(BASEVECTOR)
#     created_at = Column(DateTime, server_default=func.now())

#     __table_args__ = (
#         Index("idx_company_product_company_id", "company_id"),
#         Index(
#             "idx_company_product_embedding",
#             "product_embed",
#             postgresql_using="ivfflat",
#             postgresql_ops={"product_embed": "vector_cosine_ops"},
#         ),
#     )


# # ----------------------------------------------------------------------
# # retrieval_logs
# # ----------------------------------------------------------------------
# class RetrievalLogs(BaseModel):
#     __tablename__ = 'retrieval_logs'

#     id = Column(Integer, primary_key=True)

#     query = Column(Text)
#     retrieved_chunk_ids = Column(ARRAY(Integer))
#     created_at = Column(DateTime, server_default=func.now())
