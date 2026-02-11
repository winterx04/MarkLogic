import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from PIL import Image
import database as db

class MLModel:
    def __init__(self, image_model_name='clip-ViT-B-32', text_model_name='all-MiniLM-L6-v2'):
        print("Loading ML models...")
        # CLIP for images (512 dimensions)
        self.image_model = SentenceTransformer(image_model_name)
        # MiniLM for text (384 dimensions)
        self.text_model = SentenceTransformer(text_model_name)
        
        self.logo_index = None
        self.id_map = [] 
        print("ML models loaded successfully.")

    def generate_image_embedding(self, image_file_stream):
        """Converts an image file stream into a NORMALIZED vector embedding."""
        try:
            image = Image.open(image_file_stream).convert("RGB")
            # Returns a list, we take the first element [0]
            embedding = self.image_model.encode([image], convert_to_numpy=True, show_progress_bar=False)[0]
            
            # --- CRUCIAL FOR ACCURACY ---
            # Normalize the vector to unit length (1.0) immediately.
            # This fixes the "0.02%" similarity problem.
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
                
            return embedding.astype('float32')
        except Exception as e:
            print(f"Error processing image for embedding: {e}")
            return None

    def generate_text_embedding(self, text):
        """Converts trademark description/name to a NORMALIZED vector (384-dim)."""
        if not text:
            return np.zeros(384, dtype=np.float32)
        
        embedding = self.text_model.encode(text, convert_to_numpy=True)
        
        # Normalize text vectors for consistent Cosine Similarity search
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
            
        return embedding.astype('float32')

    def build_logo_index(self):
        """Fetches all logo embeddings from the DB and builds a FAISS index."""
        print("Building FAISS logo index from database...")
        db_data = db.get_all_embeddings()

        valid_logo_entries = []
        temp_id_map = []
        
        for db_id, logo_emb_array in zip(db_data['ids'], db_data['logo']):
            # Ensure we only index non-zero/valid embeddings
            if logo_emb_array is not None and np.any(logo_emb_array):
                valid_logo_entries.append(logo_emb_array)
                temp_id_map.append(db_id)

        if not valid_logo_entries:
            print("No logo embeddings found in the database to index.")
            return

        self.id_map = temp_id_map
        logo_embeddings_np = np.vstack(valid_logo_entries).astype('float32')

        # Vectors are already normalized in generate_image_embedding, 
        # but we run normalize_L2 here as a safety double-check.
        faiss.normalize_L2(logo_embeddings_np)
        
        dimension = logo_embeddings_np.shape[1]
        
        # Use IndexFlatIP (Inner Product) for Cosine Similarity
        cpu_index = faiss.IndexFlatIP(dimension)
        self.logo_index = faiss.IndexIDMap(cpu_index)
        
        # Add vectors with actual database IDs (int64)
        self.logo_index.add_with_ids(logo_embeddings_np, np.array(self.id_map).astype('int64'))
        print(f"FAISS logo index built successfully with {self.logo_index.ntotal} vectors.")

    def search_logo_index(self, query_embedding, return_distances=False):
        """
        Searches the FAISS index. 
        Returns high similarity scores (0.90+) for similar images like G813/G814.
        """
        if self.logo_index is None or self.logo_index.ntotal == 0:
            print("Error: FAISS logo index is not built.")
            return ([], []) if return_distances else []

        if query_embedding.ndim == 1:
            query_embedding = np.expand_dims(query_embedding, axis=0).astype('float32')

        # Normalize the query to match the indexed vectors
        faiss.normalize_L2(query_embedding)

        num_results_to_fetch = 10
        similarities, found_ids = self.logo_index.search(query_embedding, num_results_to_fetch)

        id_list = [int(i) for i in found_ids[0] if i != -1]
        
        if return_distances:
            # similarities[0] contains the Cosine Similarity (1.0 = perfect)
            # We convert to "Distance" where 0.0 = perfect for the logic in app.py
            distances = [float(1.0 - sim) for sim in similarities[0]]
            return distances, id_list
        else:
            return id_list