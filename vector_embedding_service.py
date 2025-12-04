# backend/vector_embedding_service.py
import logging
from sentence_transformers import SentenceTransformer
from typing import Dict, List, Tuple
import numpy as np

logger = logging.getLogger(__name__)

class VectorEmbeddingService:
    """
    Produces multi-vector semantic embeddings for:
      - interests_vector
      - riasec_vector
      - aptitude_vector
      - text_vector (full job/profile text)
    Use sentence-transformers model (all-MiniLM-L6-v2 by default).
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            logger.info(f"Loading embedding model: {model_name}")
            self.model = SentenceTransformer(model_name)
            self.dimension = self.model.get_sentence_embedding_dimension()
            logger.info(f"✅ Embedding model loaded (dim={self.dimension})")
        except Exception as e:
            logger.error(f"❌ Failed to load embedding model: {e}")
            raise

    def _encode(self, text: str):
        if not text or not text.strip():
            return [0.0] * self.dimension
        emb = self.model.encode(text, normalize_embeddings=True)
        return emb.tolist()

    def create_job_vectors(self, job_data: Dict) -> Dict[str, List[float]]:
        """
        Build four semantic vectors for a job.
        Returns dict with keys: interests_vector, riasec_vector, aptitude_vector, text_vector
        """
        try:
            # Interests vector: primary interest cluster + family_title
            interests_parts = []
            if job_data.get("primary_interest_cluster"):
                interests_parts.append(str(job_data["primary_interest_cluster"]))
            if job_data.get("family_title"):
                interests_parts.append(str(job_data["family_title"]))
            interests_text = " | ".join(interests_parts)

            # RIASEC vector: store the code with short description
            riasec_text = f"RIASEC: {job_data.get('riasec_code','')}" if job_data.get("riasec_code") else ""

            # Aptitude vector: aptitude scores mapping -> text
            apt_map = job_data.get("aptitude_scores", {})
            apt_parts = []
            if isinstance(apt_map, dict) and apt_map:
                apt_parts = [f"{k}:{v}" for k, v in apt_map.items()]
            aptitude_text = " ".join(apt_parts)

            # Text vector: combine title, skills, description, growth, demand, salary, pathways
            text_parts = []
            for field in [
                "family_title",
                "nco_title",
                "job_description",
                "primary_skills",
                "industry_growth_projection",
                "market_demand_score",
                "salary_range_analysis",
                "learning_pathway_recommendations"
            ]:
                val = job_data.get(field)
                if val:
                    # handle list of skills
                    if field == "primary_skills" and isinstance(val, list):
                        text_parts.append(" ".join(str(x) for x in val))
                    else:
                        text_parts.append(str(val))
            text_full = " | ".join(text_parts)

            return {
                "interests_vector": self._encode(interests_text),
                "riasec_vector": self._encode(riasec_text),
                "aptitude_vector": self._encode(aptitude_text),
                "text_vector": self._encode(text_full),
            }
        except Exception as e:
            logger.error(f"Error creating job vectors: {e}")
            # return zero vectors on failure
            return {
                "interests_vector": [0.0] * self.dimension,
                "riasec_vector": [0.0] * self.dimension,
                "aptitude_vector": [0.0] * self.dimension,
                "text_vector": [0.0] * self.dimension,
            }

    def create_user_vectors(self, user_data: Dict) -> Dict[str, List[float]]:
        """
        Build four semantic vectors for a user profile.
        Keys: interests_vector, riasec_vector, aptitude_vector, text_vector
        """
        try:
            # Interests
            interests = user_data.get("interests", [])
            if isinstance(interests, list):
                interests_text = " ".join(str(x) for x in interests if x)
            else:
                interests_text = str(interests) if interests else ""

            # RIASEC
            riasec_text = f"RIASEC: {user_data.get('riasec_code','')}" if user_data.get("riasec_code") else ""

            # Aptitudes
            aptitudes = user_data.get("aptitude_percentiles", {})
            apt_parts = []
            if isinstance(aptitudes, dict) and aptitudes:
                apt_parts = [f"{k}:{v}" for k, v in aptitudes.items()]
            aptitude_text = " ".join(apt_parts)

            # Text: combine profile fields
            text_parts = []
            for field in ["education_level", "current_field", "experience_years"]:
                val = user_data.get(field)
                if val:
                    text_parts.append(str(val))
            # include interests and aptitudes as part of full text too
            if interests_text:
                text_parts.append(interests_text)
            if aptitude_text:
                text_parts.append(aptitude_text)
            text_full = " | ".join(text_parts)

            return {
                "interests_vector": self._encode(interests_text),
                "riasec_vector": self._encode(riasec_text),
                "aptitude_vector": self._encode(aptitude_text),
                "text_vector": self._encode(text_full),
            }
        except Exception as e:
            logger.error(f"Error creating user vectors: {e}")
            return {
                "interests_vector": [0.0] * self.dimension,
                "riasec_vector": [0.0] * self.dimension,
                "aptitude_vector": [0.0] * self.dimension,
                "text_vector": [0.0] * self.dimension,
            }

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        if not vec1 or not vec2:
            return 0.0
        
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        
        # Ensure same length
        min_len = min(len(v1), len(v2))
        v1 = v1[:min_len]
        v2 = v2[:min_len]
        
        dot_product = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    def create_interest_cluster_vector(self, interest_cluster: str) -> List[float]:
        """Create vector for a single interest cluster"""
        try:
            if not interest_cluster or not interest_cluster.strip():
                return [0.0] * self.dimension
            return self._encode(interest_cluster)
        except Exception as e:
            logger.error(f"Error creating interest cluster vector: {e}")
            return [0.0] * self.dimension

    def create_field_specific_vector(self, field: str, interests: List[str]) -> List[float]:
        """Create vector for user's current field combined with interests"""
        try:
            if not field:
                field = ""
            if not interests:
                interests = []
            
            # Combine field and interests
            combined_text = f"{field} | {' '.join(interests)}"
            return self._encode(combined_text)
        except Exception as e:
            logger.error(f"Error creating field-specific vector: {e}")
            return [0.0] * self.dimension