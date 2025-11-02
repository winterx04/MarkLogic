# ml_utils.py (Image-Only Version)
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from PIL import Image
import database as db

class MLModel:
    def __init__(self, model_name='clip-ViT-B-32'):
        print("Loading Image ML model...")
        self.model = SentenceTransformer(model_name)
        self.logo_index = None
        self.id_map = [] # Maps FAISS index position to database ID
        print("Image ML model loaded successfully.")

    def generate_image_embedding(self, image_file_stream):
        """Converts an image file stream into a vector embedding."""
        try:
            image = Image.open(image_file_stream).convert("RGB")
            embedding = self.model.encode([image], convert_to_numpy=True, show_progress_bar=False)
            return embedding[0]
        except Exception as e:
            print(f"Error processing image for embedding: {e}")
            return None

    def build_logo_index(self):
        """Fetches all logo embeddings from the DB and builds a FAISS index."""
        print("Building FAISS logo index from database...")
        db_data = db.get_all_embeddings()

        # Filter for entries that have a valid logo embedding
        valid_logo_entries = []
        temp_id_map = []
        for db_id, logo_emb_array in zip(db_data['ids'], db_data['logo']):
            if logo_emb_array.any(): # Check if the array is not all zeros
                valid_logo_entries.append(logo_emb_array)
                temp_id_map.append(db_id)

        if not valid_logo_entries:
            print("No logo embeddings found in the database to index.")
            return

        self.id_map = temp_id_map
        logo_embeddings_np = np.vstack(valid_logo_entries).astype('float32')

        # --- Use Cosine Similarity for better results ---
        # 1. Normalize the vectors
        faiss.normalize_L2(logo_embeddings_np)
        dimension = logo_embeddings_np.shape[1]
        
        # 2. Use IndexFlatIP (Inner Product), which is equivalent to Cosine Similarity
        # We use IndexIDMap to store our actual database IDs
        cpu_index = faiss.IndexFlatIP(dimension)
        self.logo_index = faiss.IndexIDMap(cpu_index)
        
        # Add vectors to the index with their corresponding database IDs
        self.logo_index.add_with_ids(logo_embeddings_np, np.array(self.id_map).astype('int64'))
        print(f"FAISS logo index built successfully with {self.logo_index.ntotal} vectors.")

    def search_logo_index(self, query_embedding, top_k=50):
        """Searches the FAISS index for the most similar images."""
        if self.logo_index is None or self.logo_index.ntotal == 0:
            print("FAISS logo index is not built or is empty.")
            return []

        query_embedding_np = np.array([query_embedding]).astype('float32')
        # Normalize the query vector to match the index
        faiss.normalize_L2(query_embedding_np)
        
        # Perform the search
        distances, indices = self.logo_index.search(query_embedding_np, top_k)
        
        # The 'indices' are the database IDs we stored. Filter out -1 (no result).
        found_ids = [int(i) for i in indices[0] if i != -1]
        return found_ids