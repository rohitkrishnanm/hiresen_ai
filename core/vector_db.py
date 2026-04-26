import sys
class MockPostHog:
    def capture(self, *args, **kwargs): pass
sys.modules['posthog'] = MockPostHog()
import chromadb
import uuid
import os
from typing import List, Dict, Optional

class VectorDBClient:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VectorDBClient, cls).__new__(cls)
            # Initialize with persistence
            db_path = os.path.join(os.getcwd(), "data", "chroma_db")
            from chromadb.config import Settings
            cls._instance.client = chromadb.PersistentClient(path=db_path, settings=Settings(anonymized_telemetry=False))
            cls._instance.collection = cls._instance.client.get_or_create_collection(
                name="resume_embeddings",
                metadata={"hnsw:space": "cosine"}
            )
        return cls._instance
        
    def add_document(self, text: str, metadata: Dict) -> str:
        """
        Adds a document to the vector store.
        Returns the ID.
        """
        doc_id = metadata.get("id", str(uuid.uuid4()))
        self.collection.upsert(
            documents=[text],
            metadatas=[metadata],
            ids=[doc_id]
        )
        return doc_id
        
    def query_similar(self, query_text: str, n_results: int = 3, filter_dict: Optional[Dict] = None) -> List[Dict]:
        """
        Finds similar documents.
        """
        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=filter_dict
        )
        
        # Flatten results for easier consumption
        matches = []
        if results and results['documents']:
            for i in range(len(results['documents'][0])):
                matches.append({
                    "id": results['ids'][0][i],
                    "document": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i],
                    "distance": results['distances'][0][i] if results['distances'] else None
                })
        return matches

    def delete_document(self, doc_id: str):
        self.collection.delete(ids=[doc_id])
    
    def count(self) -> int:
        return self.collection.count()
