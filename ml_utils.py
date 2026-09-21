from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
from PIL import Image
import database as db

def pad_to_square_rgb(image, fill=255):
    """Composite onto a white background and letterbox to a square canvas
    before handing off to CLIP.

    CLIP's own preprocessor resizes to a fixed shortest-edge then
    center-crops to a square - measured on real trademark logo crops
    (routinely 2:1 to 6:1 wide) this silently discards 40-85% of the
    logo's width before the model ever sees it, which is a real driver of
    both false positives (unrelated logos whose surviving center strips
    happen to align) and crop-sensitivity (the same logo cropped with
    different margins keeps a different strip). Padding to a square first
    means CLIP's center-crop has nothing left to cut off. Validated via
    eval/eval_similarity.py-style rescoring on the bootstrap pairs:
    FP 78->59, confident-precision 0.619->0.650, recall unchanged at 100%."""
    rgba = image.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (fill, fill, fill, 255))
    bg.paste(rgba, mask=rgba.split()[-1])
    rgb = bg.convert("RGB")
    w, h = rgb.size
    side = max(w, h)
    if side == 0:
        return rgb
    canvas = Image.new("RGB", (side, side), (fill, fill, fill))
    canvas.paste(rgb, ((side - w) // 2, (side - h) // 2))
    return canvas


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
            image = pad_to_square_rgb(Image.open(image_file_stream))
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
        """
        Fetches all logo embeddings from the DB and builds a FAISS index.

        A single trademark can now have multiple logo variants (see
        trademark_logos in database.py - e.g. a device + text_logo, or
        several sub-elements of one composite mark), so several FAISS vector
        ids can map back to the same trademark. self.id_map records that
        mapping; search_logo_index() dedupes on it so callers still just see
        one entry per trademark, same as before this change.
        """
        print("Building FAISS logo index from database...")
        db_data = db.get_all_logo_variant_embeddings()

        valid_logo_entries = []
        temp_id_map = {}  # FAISS vector id (row_key) -> trademark_id

        for row_key, trademark_id, logo_emb_array in zip(
            db_data['ids'], db_data['trademark_ids'], db_data['logo']
        ):
            # Ensure we only index non-zero/valid embeddings
            if logo_emb_array is not None and np.any(logo_emb_array):
                valid_logo_entries.append(logo_emb_array)
                temp_id_map[row_key] = trademark_id

        if not valid_logo_entries:
            print("No logo embeddings found in the database to index.")
            return

        self.id_map = temp_id_map
        row_keys = list(temp_id_map.keys())
        logo_embeddings_np = np.vstack(valid_logo_entries).astype('float32')

        # Vectors are already normalized in generate_image_embedding,
        # but we run normalize_L2 here as a safety double-check.
        faiss.normalize_L2(logo_embeddings_np)

        dimension = logo_embeddings_np.shape[1]

        # Use IndexFlatIP (Inner Product) for Cosine Similarity
        cpu_index = faiss.IndexFlatIP(dimension)
        self.logo_index = faiss.IndexIDMap(cpu_index)

        # Add vectors with row keys (int64) - NOT trademark ids directly,
        # since several rows can share one trademark id.
        self.logo_index.add_with_ids(logo_embeddings_np, np.array(row_keys).astype('int64'))
        num_trademarks = len(set(temp_id_map.values()))
        print(f"FAISS logo index built successfully with {self.logo_index.ntotal} vectors "
              f"across {num_trademarks} trademarks.")

    def search_logo_index(self, query_embedding, return_distances=False, top_k=10):
        """
        Searches the FAISS index and returns up to top_k results, ONE PER
        TRADEMARK (not per logo variant) - if a trademark's device and
        text_logo both score highly against the query, only its best-scoring
        variant is kept, same external shape as before this change.
        """
        if self.logo_index is None or self.logo_index.ntotal == 0:
            print("Error: FAISS logo index is not built.")
            return ([], []) if return_distances else []

        if query_embedding.ndim == 1:
            query_embedding = np.expand_dims(query_embedding, axis=0).astype('float32')

        # Normalize the query to match the indexed vectors
        faiss.normalize_L2(query_embedding)

        # Fetch more raw candidates than top_k - multiple logo variants of the
        # same trademark can occupy several of the top slots, so we need room
        # to dedupe down to top_k *unique* trademarks.
        num_results_to_fetch = max(top_k * 4, 40)
        similarities, found_ids = self.logo_index.search(query_embedding, num_results_to_fetch)

        best_per_trademark = {}  # trademark_id -> best cosine similarity
        for sim, row_key in zip(similarities[0], found_ids[0]):
            if row_key == -1:
                continue
            trademark_id = self.id_map.get(int(row_key))
            if trademark_id is None:
                continue
            if trademark_id not in best_per_trademark or sim > best_per_trademark[trademark_id]:
                best_per_trademark[trademark_id] = float(sim)

        ranked = sorted(best_per_trademark.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        id_list = [trademark_id for trademark_id, _ in ranked]

        if return_distances:
            # Cosine Similarity -> "Distance" where 0.0 = perfect, matching app.py
            distances = [float(1.0 - sim) for _, sim in ranked]
            return distances, id_list
        else:
            return id_list