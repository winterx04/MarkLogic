# ml_utils.py (Image-Only Version) NOTED! This is for Searching, NOT COMPARING
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


    def search_logo_index(self, query_embedding, return_distances=False):
        """
        Searches the FAISS index for the most similar logo embeddings.
        This version is corrected for Cosine Similarity (IndexFlatIP).
        """
        # Add a crucial check to ensure the index has been built
        if self.logo_index is None or self.logo_index.ntotal == 0:
            print("Error: FAISS logo index is not built or is empty.")
            return ([], []) if return_distances else []

        # FAISS expects a 2D numpy array of type float32
        if query_embedding.ndim == 1:
            query_embedding = np.expand_dims(query_embedding, axis=0).astype('float32')

        # --- CRUCIAL FIX for COSINE SIMILARITY ---
        # MUST normalize the query vector to match the index vectors.
        faiss.normalize_L2(query_embedding)

        num_results_to_fetch = 10

        # `search` returns similarity scores (higher is better) and the stored database IDs
        similarities, found_ids = self.logo_index.search(query_embedding, num_results_to_fetch)

        # Flatten the results and filter out -1 (which means no result found)
        id_list = [int(i) for i in found_ids[0] if i != -1]
        
        if return_distances:
            similarity_list = similarities[0]
            
            # --- CONVERT SIMILARITY TO DISTANCE ---
            # Similarity Score: 1.0 = perfect match, -1.0 = opposite.
            # Distance:         0.0 = perfect match, > 0 = less similar.
            # This makes the threshold logic (dist <= THRESHOLD) intuitive and correct.
            distances = [1 - sim for sim, i in zip(similarity_list, found_ids[0]) if i != -1]
            
            return distances, id_list
        else:
            return id_list

