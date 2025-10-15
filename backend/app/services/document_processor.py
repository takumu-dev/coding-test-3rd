"""
Document processing service using pdfplumber

Implements the document processing pipeline:
- Extract tables from PDF using pdfplumber
- Classify tables (capital calls, distributions, adjustments)
- Extract and chunk text for vector storage
- Handle errors and edge cases
"""
from typing import Dict, List, Any
import pdfplumber
import re
from app.core.config import settings
from app.services.table_parser import TableParser
from app.services.vector_store import VectorStore
from app.db.session import SessionLocal


class DocumentProcessor:
    """Process PDF documents and extract structured data"""
    
    def __init__(self):
        self.table_parser = TableParser()
        self.vector_store = VectorStore()
    
    async def process_document(self, file_path: str, document_id: int, fund_id: int) -> Dict[str, Any]:
        """
        Process a PDF document
        
        Args:
            file_path: Path to the PDF file
            document_id: Database document ID
            fund_id: Fund ID
            
        Returns:
            Processing result with statistics
        """
        db = SessionLocal()
        
        try:
            stats = {
                'status': 'completed',
                'tables_found': 0,
                'capital_calls': 0,
                'distributions': 0,
                'adjustments': 0,
                'text_chunks': 0,
                'pages_processed': 0,
                'error': None
            }
            
            # Open PDF
            with pdfplumber.open(file_path) as pdf:
                stats['pages_processed'] = len(pdf.pages)
                
                all_text_content = []
                
                # Process each page
                for page_num, page in enumerate(pdf.pages, start=1):
                    # Extract tables
                    tables = page.extract_tables()
                    
                    for table in tables:
                        if not table or len(table) < 2:
                            continue
                        
                        stats['tables_found'] += 1
                        
                        # Get surrounding text for context
                        page_text = page.extract_text() or ""
                        
                        # Classify and parse table
                        table_type = self.table_parser.classify_table(table, page_text)
                        
                        if table_type == 'capital_call':
                            records = self.table_parser.parse_capital_call_table(table, fund_id, db)
                            stats['capital_calls'] += len(records)
                        elif table_type == 'distribution':
                            records = self.table_parser.parse_distribution_table(table, fund_id, db)
                            stats['distributions'] += len(records)
                        elif table_type == 'adjustment':
                            records = self.table_parser.parse_adjustment_table(table, fund_id, db)
                            stats['adjustments'] += len(records)
                    
                    # Extract text (excluding tables for cleaner text)
                    page_text = page.extract_text()
                    if page_text:
                        all_text_content.append({
                            'text': page_text,
                            'page': page_num,
                            'document_id': document_id,
                            'fund_id': fund_id
                        })
                
                # Chunk and store text in vector database
                chunks = self._chunk_text(all_text_content)
                
                for chunk in chunks:
                    await self.vector_store.add_document(
                        content=chunk['text'],
                        metadata={
                            'document_id': document_id,
                            'fund_id': fund_id,
                            'page': chunk['page'],
                            'chunk_index': chunk['chunk_index']
                        }
                    )
                
                stats['text_chunks'] = len(chunks)
            
            db.close()
            return stats
            
        except Exception as e:
            db.close()
            return {
                'status': 'failed',
                'error': str(e),
                'tables_found': 0,
                'capital_calls': 0,
                'distributions': 0,
                'adjustments': 0,
                'text_chunks': 0,
                'pages_processed': 0
            }
    
    def _chunk_text(self, text_content: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Chunk text content for vector storage
        
        Implements intelligent text chunking:
        - Split text into semantic chunks
        - Maintain context overlap
        - Preserve sentence boundaries
        - Add metadata to each chunk
        
        Args:
            text_content: List of text content with metadata
            
        Returns:
            List of text chunks with metadata
        """
        chunks = []
        chunk_index = 0
        
        for content in text_content:
            text = content['text']
            page = content['page']
            document_id = content['document_id']
            fund_id = content['fund_id']
            
            # Clean text
            text = self._clean_text(text)
            
            # Split into sentences
            sentences = self._split_into_sentences(text)
            
            # Create chunks with overlap
            current_chunk = []
            current_length = 0
            
            for sentence in sentences:
                sentence_length = len(sentence)
                
                # Check if adding this sentence exceeds chunk size
                if current_length + sentence_length > settings.CHUNK_SIZE and current_chunk:
                    # Save current chunk
                    chunk_text = ' '.join(current_chunk)
                    chunks.append({
                        'text': chunk_text,
                        'page': page,
                        'document_id': document_id,
                        'fund_id': fund_id,
                        'chunk_index': chunk_index
                    })
                    chunk_index += 1
                    
                    # Start new chunk with overlap
                    overlap_sentences = []
                    overlap_length = 0
                    
                    # Add sentences for overlap
                    for s in reversed(current_chunk):
                        if overlap_length + len(s) <= settings.CHUNK_OVERLAP:
                            overlap_sentences.insert(0, s)
                            overlap_length += len(s)
                        else:
                            break
                    
                    current_chunk = overlap_sentences
                    current_length = overlap_length
                
                # Add sentence to current chunk
                current_chunk.append(sentence)
                current_length += sentence_length
            
            # Add remaining chunk
            if current_chunk:
                chunk_text = ' '.join(current_chunk)
                chunks.append({
                    'text': chunk_text,
                    'page': page,
                    'document_id': document_id,
                    'fund_id': fund_id,
                    'chunk_index': chunk_index
                })
                chunk_index += 1
        
        return chunks
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove page numbers and headers/footers (common patterns)
        text = re.sub(r'Page \d+', '', text, flags=re.IGNORECASE)
        
        # Normalize quotes
        text = text.replace('"', '"').replace('"', '"')
        text = text.replace(''', "'").replace(''', "'")
        
        return text.strip()
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences while preserving meaning"""
        # Simple sentence splitting (can be improved with NLTK)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Filter out very short sentences
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
        
        return sentences
