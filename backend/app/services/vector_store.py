"""
Vector store service using pgvector (PostgreSQL extension)

TODO: Implement vector storage using pgvector
- Create embeddings table in PostgreSQL
- Store document chunks with vector embeddings
- Implement similarity search using pgvector operators
- Handle metadata filtering
"""
from typing import List, Dict, Any, Optional
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import text
from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings
from app.core.config import settings
from app.db.session import SessionLocal


class VectorStore:
    """pgvector-based vector store for document embeddings"""
    
    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()
        self.embeddings = self._initialize_embeddings()
        self._ensure_extension()
    
    def _initialize_embeddings(self):
        """Initialize embedding model"""
        # Try Gemini embeddings first
        if hasattr(settings, 'GOOGLE_API_KEY') and settings.GOOGLE_API_KEY:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            return GoogleGenerativeAIEmbeddings(
                model="models/embedding-001",
                google_api_key=settings.GOOGLE_API_KEY
            )
        elif settings.OPENAI_API_KEY:
            return OpenAIEmbeddings(
                model=settings.OPENAI_EMBEDDING_MODEL,
                openai_api_key=settings.OPENAI_API_KEY
            )
        else:
            # Fallback to local embeddings (requires sentence-transformers)
            try:
                return HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-MiniLM-L6-v2"
                )
            except ImportError:
                raise ImportError(
                    "No API key configured and sentence-transformers not installed. "
                    "Please set GOOGLE_API_KEY or OPENAI_API_KEY in .env, or install sentence-transformers: "
                    "pip install sentence-transformers"
                )
    
    def _ensure_extension(self):
        """
        Ensure pgvector extension is enabled
        
        TODO: Implement this method
        - Execute: CREATE EXTENSION IF NOT EXISTS vector;
        - Create embeddings table if not exists
        """
        try:
            # Enable pgvector extension
            self.db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            
            # Create embeddings table
            # Dimension: 1536 for OpenAI, 384 for sentence-transformers
            dimension = 1536 if settings.OPENAI_API_KEY else 768  # Create embeddings table if not exists (768 dimensions for Gemini embeddings)
            create_table_sql = text("""
                CREATE TABLE IF NOT EXISTS document_embeddings (
                    id SERIAL PRIMARY KEY,
                    document_id INTEGER,
                    fund_id INTEGER,
                    content TEXT NOT NULL,
                    embedding vector(768),
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                    FOREIGN KEY (fund_id) REFERENCES funds(id) ON DELETE CASCADE
                );
                
                CREATE INDEX IF NOT EXISTS document_embeddings_embedding_idx 
                ON document_embeddings USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """)
            
            self.db.execute(create_table_sql)
            self.db.commit()
        except Exception as e:
            print(f"Error ensuring pgvector extension: {e}")
            self.db.rollback()
    
    async def add_document(self, content: str, metadata: Dict[str, Any]):
        """
        Add a document to the vector store
        
        TODO: Implement this method
        - Generate embedding for content
        - Insert into document_embeddings table
        - Store metadata as JSONB
        """
        try:
            # Generate embedding
            embedding = await self._get_embedding(content)
            embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else embedding
            
            # Format embedding as PostgreSQL array string
            embedding_str = '[' + ','.join(map(str, embedding_list)) + ']'
            
            # Convert metadata to JSON string
            import json
            metadata_json = json.dumps(metadata)
            
            # Insert into database using raw SQL with proper psycopg2 binding
            insert_sql = """
                INSERT INTO document_embeddings (document_id, fund_id, content, embedding, metadata)
                VALUES (%(document_id)s, %(fund_id)s, %(content)s, %(embedding)s::vector, %(metadata)s::jsonb)
            """
            
            # Use raw connection for proper parameter binding
            conn = self.db.connection().connection
            cursor = conn.cursor()
            cursor.execute(insert_sql, {
                "document_id": metadata.get("document_id"),
                "fund_id": metadata.get("fund_id"),
                "content": content,
                "embedding": embedding_str,
                "metadata": metadata_json
            })
            conn.commit()
            cursor.close()
        except Exception as e:
            print(f"Error adding document: {e}")
            self.db.rollback()
            raise
    
    async def similarity_search(
        self, 
        query: str, 
        k: int = 5, 
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents using cosine similarity
        
        TODO: Implement this method
        - Generate query embedding
        - Use pgvector's <=> operator for cosine distance
        - Apply metadata filters if provided
        - Return top k results
        
        Args:
            query: Search query
            k: Number of results to return
            filter_metadata: Optional metadata filters (e.g., {"fund_id": 1})
            
        Returns:
            List of similar documents with scores
        """
        try:
            # Generate query embedding
            query_embedding = await self._get_embedding(query)
            embedding_list = query_embedding.tolist()
            
            # Build query with optional filters
            where_clause = ""
            if filter_metadata:
                conditions = []
                for key, value in filter_metadata.items():
                    if key in ["document_id", "fund_id"]:
                        conditions.append(f"{key} = {value}")
                if conditions:
                    where_clause = "WHERE " + " AND ".join(conditions)
            
            # Search using cosine distance (<=> operator)
            search_sql = text(f"""
                SELECT 
                    id,
                    document_id,
                    fund_id,
                    content,
                    metadata,
                    1 - (embedding <=> :query_embedding::vector) as similarity_score
                FROM document_embeddings
                {where_clause}
                ORDER BY embedding <=> :query_embedding::vector
                LIMIT :k
            """)
            
            result = self.db.execute(search_sql, {
                "query_embedding": str(embedding_list),
                "k": k
            })
            
            # Format results
            results = []
            for row in result:
                results.append({
                    "id": row[0],
                    "document_id": row[1],
                    "fund_id": row[2],
                    "content": row[3],
                    "metadata": row[4],
                    "score": float(row[5])
                })
            
            return results
        except Exception as e:
            print(f"Error in similarity search: {e}")
            return []
    
    async def _get_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for text"""
        if hasattr(self.embeddings, 'embed_query'):
            embedding = self.embeddings.embed_query(text)
        else:
            embedding = self.embeddings.encode(text)
        
        return np.array(embedding, dtype=np.float32)
    
    def clear(self, fund_id: Optional[int] = None):
        """
        Clear the vector store
        
        TODO: Implement this method
        - Delete all embeddings (or filter by fund_id)
        """
        try:
            if fund_id:
                delete_sql = text("DELETE FROM document_embeddings WHERE fund_id = :fund_id")
                self.db.execute(delete_sql, {"fund_id": fund_id})
            else:
                delete_sql = text("DELETE FROM document_embeddings")
                self.db.execute(delete_sql)
            
            self.db.commit()
        except Exception as e:
            print(f"Error clearing vector store: {e}")
            self.db.rollback()
