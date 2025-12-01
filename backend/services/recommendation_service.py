# backend/services/recommendation_service.py
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import logging
import sys
import os
from typing import Dict, List, Any


# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from backend.database.mongodb import mongo_db
    from backend.config import Config
    from backend.vector_embedding_service import VectorEmbeddingService
except ImportError:
    # Fallback for direct execution
    from database.mongodb import mongo_db
    from config import Config
    from vector_embedding_service import VectorEmbeddingService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RecommendationService:
    def __init__(self):
        self.vectorizer = None
        self.job_vectors = None
        self.jobs_data = None
        self.use_vector_search = False
        self.embedding_service = None
        
        try:
            self.embedding_service = VectorEmbeddingService()
            self._load_jobs_data()
        except Exception as e:
            logger.error(f"Error initializing RecommendationService: {e}")
            self._load_jobs_data_fallback()
    
    def _load_jobs_data(self):
        """Load jobs data from MongoDB and check for vector search capability"""
        try:
            jobs_collection = mongo_db.get_jobs_collection()
            
            # Check if embeddings exist
            sample_job = jobs_collection.find_one({"embedding": {"$exists": True, "$ne": []}})
            
            if sample_job:
                logger.info("✅ Jobs have embeddings - checking vector search capability")
                
                # Test if vector search works by running a test query
                try:
                    # Create a simple test query to check if vector search works
                    test_vector = [0.1] * 384  # Dummy vector
                    test_pipeline = [
                        {
                            "$vectorSearch": {
                                "index": "career_vectors",  # Your index name
                                "path": "embedding",
                                "queryVector": test_vector,
                                "numCandidates": 10,
                                "limit": 1
                            }
                        }
                    ]
                    
                    # Try to run vector search
                    results = list(jobs_collection.aggregate(test_pipeline, maxTimeMS=5000))
                    
                    if results:
                        logger.info("✅ Vector search is working!")
                        self.use_vector_search = True
                    else:
                        logger.warning("⚠️ Vector search test returned no results")
                        logger.info("   Falling back to enhanced matching")
                        self.use_vector_search = False
                        self._prepare_similarity_matrix()
                        
                except Exception as vector_test_error:
                    logger.warning(f"⚠️ Vector search test failed: {vector_test_error}")
                    logger.info("   Falling back to enhanced matching without vector search")
                    self.use_vector_search = False
                    self._prepare_similarity_matrix()
                    
            else:
                logger.info("⚠️ No embeddings found - using enhanced TF-IDF matching")
                self.use_vector_search = False
                self._prepare_similarity_matrix()
                
        except Exception as e:
            logger.error(f"❌ Error loading jobs data: {e}")
            self._load_jobs_data_fallback()
            
    def _load_jobs_data_fallback(self):
        """Fallback method to load data without MongoDB"""
        try:
            logger.info("Attempting fallback data loading...")
            # Try to load from a local file or use empty data
            self.jobs_data = []
            self.use_vector_search = False
            self._prepare_similarity_matrix()
        except Exception as e:
            logger.error(f"Fallback also failed: {e}")
    
    def _prepare_similarity_matrix(self):
        """Prepare TF-IDF vectorizer for text similarity (fallback)"""
        try:
            jobs_collection = mongo_db.get_jobs_collection()
            self.jobs_data = list(jobs_collection.find({}, {'_id': 0}))
            
            if not self.jobs_data:
                logger.warning("⚠️ No jobs found in database")
                self.vectorizer = None
                self.job_vectors = None
                return
            
            logger.info(f"📊 Loaded {len(self.jobs_data)} jobs for TF-IDF processing")
            
            texts = []
            for job in self.jobs_data:
                # Create text from job data
                text_parts = []
                
                if job.get('family_title'):
                    text_parts.append(str(job['family_title']))
                
                if job.get('nco_title'):
                    text_parts.append(str(job['nco_title']))
                
                if job.get('job_description'):
                    text_parts.append(str(job['job_description']))
                
                # Handle skills
                skills = job.get('primary_skills', [])
                if isinstance(skills, list):
                    text_parts.append(' '.join(str(skill) for skill in skills if skill))
                elif skills:
                    text_parts.append(str(skills))
                
                if job.get('primary_interest_cluster'):
                    text_parts.append(str(job['primary_interest_cluster']))
                
                combined_text = ' '.join(text_parts)
                if combined_text.strip():
                    texts.append(combined_text)
                else:
                    texts.append('')
            
            if not texts or all(not text.strip() for text in texts):
                logger.warning("⚠️ No valid text content found for TF-IDF")
                self.vectorizer = None
                self.job_vectors = None
                return
            
            logger.info(f"🔧 Creating TF-IDF matrix from {len(texts)} job texts")
            
            self.vectorizer = TfidfVectorizer(
                stop_words='english',
                max_features=1000,
                min_df=1,
                max_df=0.95,
                ngram_range=(1, 2)
            )
            
            self.job_vectors = self.vectorizer.fit_transform(texts)
            logger.info(f"✅ TF-IDF vocabulary size: {len(self.vectorizer.vocabulary_)}")
            
        except Exception as e:
            logger.error(f"❌ Error preparing similarity matrix: {e}")
            self.vectorizer = None
            self.job_vectors = None
    
    def calculate_riasec_similarity_advanced(self, user_riasec, job_riasec):
        """Calculate RIASEC similarity using advanced matching (from old app)"""
        if not job_riasec or not user_riasec:
            return 0
        
        # Clean and normalize codes
        user_riasec = str(user_riasec).replace(' ', '')[:3].upper()
        job_riasec = str(job_riasec).replace(' ', '')[:3].upper()
        
        if not user_riasec or not job_riasec:
            return 0
        
        # Exact 3-character match in same order - 100%
        if user_riasec == job_riasec:
            return 1.0
        
        # Exact first 2 characters in same order - 95%
        if user_riasec[:2] == job_riasec[:2]:
            return 0.95
        
        # First character matches + second character appears anywhere - 90%
        if user_riasec[0] == job_riasec[0] and user_riasec[1] in job_riasec:
            return 0.90
        
        # First character matches + any other user character appears - 85%
        if user_riasec[0] == job_riasec[0] and any(char in job_riasec for char in user_riasec[1:]):
            return 0.85
        
        # First two characters appear in career code (not necessarily in order) - 80%
        if all(char in job_riasec for char in user_riasec[:2]):
            # Bonus if they appear in relatively same positions
            user_first_pos = job_riasec.find(user_riasec[0])
            user_second_pos = job_riasec.find(user_riasec[1])
            if user_first_pos >= 0 and user_second_pos >= 0 and user_second_pos > user_first_pos:
                return 0.85  # Slight bonus for maintaining relative order
            return 0.80
        
        # First character matches - 75%
        if user_riasec[0] in job_riasec:
            return 0.75
        
        # At least 2 characters from user's top 3 appear in career - 70%
        common_chars = len(set(user_riasec) & set(job_riasec))
        if common_chars >= 2:
            # Check if common characters maintain some order
            user_chars_in_career = [char for char in user_riasec if char in job_riasec]
            career_positions = [job_riasec.find(char) for char in user_chars_in_career]
            if career_positions == sorted(career_positions):  # Maintains order
                return 0.75
            return 0.70
        
        # At least 1 character matches - 60%
        if common_chars >= 1:
            return 0.60
        
        return 0.30  # Minimal match for completely different codes
    
    def calculate_riasec_similarity(self, user_riasec, job_riasec):
        """Original RIASEC similarity calculation"""
        if not job_riasec or len(job_riasec) < 2:
            return 0
        
        user_riasec = user_riasec.upper()
        job_riasec = job_riasec.upper()
        
        # Focus on first two characters for 100% match requirement
        job_primary = job_riasec[:2]
        
        # Exact match for first two characters - 100% match
        if job_primary == user_riasec[:2]:
            return 1.0
        
        # Calculate character-based similarity
        user_chars = set(user_riasec)
        job_chars = set(job_primary)
        
        intersection = user_chars.intersection(job_chars)
        union = user_chars.union(job_chars)
        
        if not union:
            return 0
        
        jaccard_similarity = len(intersection) / len(union)
        
        # Boost similarity if first character matches
        if user_riasec[0] == job_primary[0]:
            jaccard_similarity = max(jaccard_similarity, 0.7)
        
        return jaccard_similarity
    
    def calculate_interests_similarity(self, user_interests, job_interests_text):
        """Calculate similarity based on interests"""
        if not user_interests:
            return 0.5
        
        # Ensure user_interests is a list
        if isinstance(user_interests, str):
            user_interests_list = [user_interests]
        elif isinstance(user_interests, list):
            user_interests_list = user_interests
        else:
            user_interests_list = []
        
        user_interests_text = ' '.join([str(interest).lower() for interest in user_interests_list])
        job_interests_text = str(job_interests_text).lower() if job_interests_text else ''
        
        if not user_interests_text.strip():
            return 0
        
        user_words = set(user_interests_text.split())
        job_words = set(job_interests_text.split())
        
        if not user_words:
            return 0
        
        intersection = user_words.intersection(job_words)
        return len(intersection) / len(user_words)
    
    def calculate_aptitude_similarity(self, user_aptitudes, job_aptitudes):
        """Calculate similarity based on top 3 aptitudes"""
        if not user_aptitudes or not job_aptitudes:
            return 0.5
        
        # Get user's top 3 aptitudes
        user_top_3 = sorted(
            user_aptitudes.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:3]
        
        if not user_top_3:
            return 0
        
        total_similarity = 0
        matched_count = 0
        
        for aptitude_name, user_percentile in user_top_3:
            if aptitude_name in job_aptitudes:
                job_score = job_aptitudes[aptitude_name]
                
                if isinstance(job_score, (int, float)):
                    if job_score > 100:
                        job_score = min(job_score, 100)
                    
                    # Calculate similarity as 1 - (difference/100)
                    similarity = 1.0 - (abs(user_percentile - job_score) / 100.0)
                    total_similarity += max(0, similarity)
                    matched_count += 1
        
        if matched_count > 0:
            return total_similarity / matched_count
        return 0
    
    def calculate_text_similarity(self, user_profile):
        """Calculate text-based similarity using TF-IDF (fallback)"""
        if self.vectorizer is None or self.job_vectors is None:
            return np.zeros(len(self.jobs_data) if self.jobs_data else 0)
        
        user_text_parts = [
            ' '.join(user_profile.get('interests', [])),
            user_profile.get('education_level', ''),
            user_profile.get('current_field', ''),
            user_profile.get('riasec_code', '')
        ]
        user_text = ' '.join([str(part) for part in user_text_parts])
        
        if not user_text.strip():
            return np.zeros(len(self.jobs_data))
        
        user_vector = self.vectorizer.transform([user_text])
        similarities = cosine_similarity(user_vector, self.job_vectors)
        return similarities[0]
    
    def vector_search(self, user_profile: Dict, n_results: int = 50):
        """Perform vector similarity search in MongoDB"""
        try:
            if not self.use_vector_search or not self.embedding_service:
                logger.warning("Vector search not available, returning empty results")
                return []
            
            # Create user embedding
            user_embedding = self.embedding_service.create_user_embedding(user_profile)
            
            # Validate embedding
            if not user_embedding or len(user_embedding) != 384:
                logger.error(f"Invalid embedding created: length={len(user_embedding) if user_embedding else 0}")
                return []
            
            # Perform vector search
            jobs_collection = mongo_db.get_jobs_collection()
            
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "career_vectors",  # Make sure this matches your Atlas index name
                        "path": "embedding",
                        "queryVector": user_embedding,
                        "numCandidates": min(200, n_results * 4),  # More candidates for better accuracy
                        "limit": n_results
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "job_id": 1,
                        "family_title": 1,
                        "nco_title": 1,
                        "riasec_code": 1,
                        "job_description": 1,
                        "primary_skills": 1,
                        "primary_interest_cluster": 1,
                        "salary_range_analysis": 1,
                        "market_demand_score": 1,
                        "industry_growth_projection": 1,
                        "learning_pathway_recommendations": 1,
                        "aptitude_scores": 1,
                        "score": {"$meta": "vectorSearchScore"}
                    }
                }
            ]
            
            logger.info(f"🔍 Running vector search with {len(user_embedding)}-dim embedding")
            results = list(jobs_collection.aggregate(pipeline, maxTimeMS=15000))
            logger.info(f"✅ Vector search found {len(results)} results")
            
            # Log top results for debugging
            if results:
                logger.info(f"Top vector score: {results[0].get('score', 0):.4f}")
                logger.info(f"Sample match: {results[0].get('nco_title', 'Unknown')}")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Vector search error: {e}")
            # Fallback: try to get some results without vector search
            try:
                jobs_collection = mongo_db.get_jobs_collection()
                results = list(jobs_collection.find({}, {
                    "_id": 0,
                    "job_id": 1,
                    "family_title": 1,
                    "nco_title": 1,
                    "riasec_code": 1,
                    "job_description": 1,
                    "primary_skills": 1,
                    "primary_interest_cluster": 1,
                    "salary_range_analysis": 1,
                    "market_demand_score": 1,
                    "industry_growth_projection": 1,
                    "learning_pathway_recommendations": 1,
                    "aptitude_scores": 1
                }).limit(n_results))
                
                # Add dummy scores
                for result in results:
                    result['score'] = 0.5  # Default score
                
                logger.info(f"⚠️ Using fallback with {len(results)} results")
                return results
                
            except Exception as fallback_error:
                logger.error(f"❌ Fallback also failed: {fallback_error}")
                return []

                
    def generate_recommendations(self, user, min_percentage=70):
        """Generate job recommendations with minimum match percentage"""
        logger.info(f"🎯 Generating recommendations for user with min {min_percentage}% match")
        
        if self.use_vector_search:
            return self._generate_recommendations_vector(user, min_percentage)
        else:
            return self._generate_recommendations_enhanced(user, min_percentage)
    
    def _generate_recommendations_vector(self, user, min_percentage=70):
        """Generate recommendations using vector search with minimum percentage filter"""
        try:
            user_profile = {
                'riasec_code': user.riasec_code,
                'interests': user.interests,
                'education_level': user.education_level,
                'current_field': user.current_field,
                'experience_years': user.experience_years,
                'aptitude_percentiles': user.aptitude_percentiles
            }
            
            # Get vector search results - increase limit to get more candidates
            vector_results = self.vector_search(user_profile, n_results=200)  # Increased from 100
            
            if not vector_results:
                logger.warning("⚠️ No vector results, falling back to enhanced matching")
                return self._generate_recommendations_enhanced(user, min_percentage)
            
            matches = []
            
            for job in vector_results:
                # Calculate detailed similarity scores (same as before)
                riasec_similarity = self.calculate_riasec_similarity_advanced(
                    user.riasec_code, 
                    job.get('riasec_code', '')
                )
                
                interests_similarity = self.calculate_interests_similarity(
                    user.interests,
                    job.get('primary_interest_cluster', '')
                )
                
                aptitude_similarity = self.calculate_aptitude_similarity(
                    user.aptitude_percentiles,
                    job.get('aptitude_scores', {})
                )
                
                vector_score = job.get('score', 0)
                
                # Combined score with weights
                combined_score = (
                    vector_score * 0.4 +           # 40% vector similarity
                    riasec_similarity * 0.3 +      # 30% RIASEC match
                    interests_similarity * 0.2 +   # 20% interests match
                    aptitude_similarity * 0.1      # 10% aptitude match
                )
                
                # Convert to percentage
                match_percentage = min(round(combined_score * 100), 100)
                
                # Apply boosting for high matches
                if riasec_similarity >= 0.9:
                    match_percentage = min(match_percentage + 15, 100)
                elif riasec_similarity >= 0.8:
                    match_percentage = min(match_percentage + 10, 100)
                elif riasec_similarity >= 0.7:
                    match_percentage = min(match_percentage + 5, 100)
                
                if vector_score >= 0.8:
                    match_percentage = min(match_percentage + 5, 100)
                
                # Filter by minimum percentage
                if match_percentage < min_percentage:
                    continue  # Skip jobs below threshold
                
                # Get top aptitudes for reasoning
                user_top_aptitudes = self._get_top_aptitudes(user.aptitude_percentiles, 3)
                
                matches.append({
                    'job_id': job.get('job_id', ''),
                    'job_title': job.get('nco_title', ''),
                    'family_title': job.get('family_title', ''),
                    'riasec_code': job.get('riasec_code', ''),
                    'match_percentage': match_percentage,
                    'job_description': job.get('job_description', ''),
                    'primary_skills': job.get('primary_skills', ''),
                    'salary_range': job.get('salary_range_analysis', 'Not specified'),
                    'market_demand': job.get('market_demand_score', 'Medium'),
                    'growth_projection': job.get('industry_growth_projection', ''),
                    'learning_pathway': job.get('learning_pathway_recommendations', ''),
                    'aptitude_scores': job.get('aptitude_scores', {}),
                    'user_top_aptitudes': user_top_aptitudes,
                    'similarity_breakdown': {
                        'vector': round(vector_score * 100),
                        'riasec': round(riasec_similarity * 100),
                        'interests': round(interests_similarity * 100),
                        'aptitude': round(aptitude_similarity * 100)
                    },
                    'reasoning': self._generate_reasoning(
                        riasec_similarity, 
                        interests_similarity, 
                        aptitude_similarity,
                        vector_score
                    )
                })
            
            # Sort by match percentage (descending)
            matches.sort(key=lambda x: x['match_percentage'], reverse=True)
            logger.info(f"✅ Found {len(matches)} jobs with ≥{min_percentage}% match using vector search")
            return matches
            
        except Exception as e:
            logger.error(f"❌ Error in vector recommendations: {e}")
            return self._generate_recommendations_enhanced(user, min_percentage)

    def _generate_recommendations_enhanced(self, user, min_percentage=70):
        """Enhanced recommendations with minimum percentage filter"""
        try:
            if not self.jobs_data:
                self._prepare_similarity_matrix()
            
            user_profile = {
                'riasec_code': user.riasec_code,
                'interests': user.interests,
                'education_level': user.education_level,
                'current_field': user.current_field,
                'experience_years': user.experience_years,
                'aptitude_percentiles': user.aptitude_percentiles
            }
            
            matches = []
            
            for idx, job in enumerate(self.jobs_data):
                # Calculate similarity scores (same as before)
                riasec_similarity = self.calculate_riasec_similarity_advanced(
                    user.riasec_code, 
                    job.get('riasec_code', '')
                )
                
                interests_similarity = self.calculate_interests_similarity(
                    user.interests,
                    job.get('primary_interest_cluster', '')
                )
                
                aptitude_similarity = self.calculate_aptitude_similarity(
                    user.aptitude_percentiles,
                    job.get('aptitude_scores', {})
                )
                
                text_similarities = self.calculate_text_similarity(user_profile)
                text_similarity = text_similarities[idx] if idx < len(text_similarities) else 0
                
                # Combined score with updated weights
                combined_score = (
                    riasec_similarity * 0.5 +           # 50% weight to RIASEC
                    interests_similarity * 0.3 +        # 30% interests
                    aptitude_similarity * 0.15 +        # 15% aptitude
                    text_similarity * 0.05              # 5% text
                )
                
                # Convert to percentage
                match_percentage = min(round(combined_score * 100), 100)
                
                # Apply boosting for high RIASEC matches
                if riasec_similarity >= 0.9:
                    match_percentage = min(match_percentage + 20, 100)
                elif riasec_similarity >= 0.8:
                    match_percentage = min(match_percentage + 15, 100)
                elif riasec_similarity >= 0.7:
                    match_percentage = min(match_percentage + 10, 100)
                elif riasec_similarity >= 0.6:
                    match_percentage = min(match_percentage + 5, 100)
                
                # Filter by minimum percentage
                if match_percentage < min_percentage:
                    continue  # Skip jobs below threshold
                
                # Get top aptitudes for reasoning
                user_top_aptitudes = self._get_top_aptitudes(user.aptitude_percentiles, 3)
                
                matches.append({
                    'job_id': job.get('job_id', ''),
                    'job_title': job.get('nco_title', ''),
                    'family_title': job.get('family_title', ''),
                    'riasec_code': job.get('riasec_code', ''),
                    'match_percentage': match_percentage,
                    'job_description': job.get('job_description', ''),
                    'primary_skills': job.get('primary_skills', ''),
                    'salary_range': job.get('salary_range_analysis', 'Not specified'),
                    'market_demand': job.get('market_demand_score', 'Medium'),
                    'growth_projection': job.get('industry_growth_projection', ''),
                    'learning_pathway': job.get('learning_pathway_recommendations', ''),
                    'aptitude_scores': job.get('aptitude_scores', {}),
                    'user_top_aptitudes': user_top_aptitudes,
                    'similarity_breakdown': {
                        'riasec': round(riasec_similarity * 100),
                        'interests': round(interests_similarity * 100),
                        'aptitude': round(aptitude_similarity * 100),
                        'text': round(text_similarity * 100)
                    },
                    'reasoning': self._generate_reasoning(
                        riasec_similarity, 
                        interests_similarity, 
                        aptitude_similarity,
                        0  # No vector score
                    )
                })
            
            # Sort by match percentage (descending)
            matches.sort(key=lambda x: x['match_percentage'], reverse=True)
            logger.info(f"✅ Found {len(matches)} jobs with ≥{min_percentage}% match using enhanced matching")
            return matches
            
        except Exception as e:
            logger.error(f"❌ Error in enhanced recommendations: {e}")
            return []
    def _get_top_aptitudes(self, aptitude_dict, n=3):
        """Get top n aptitudes from user's aptitude scores"""
        if not aptitude_dict:
            return []
        
        sorted_aptitudes = sorted(
            aptitude_dict.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:n]
        
        return [{"name": name, "score": score} for name, score in sorted_aptitudes]
    
    def _generate_reasoning(self, riasec_similarity, interests_similarity, aptitude_similarity, vector_score):
        """Generate reasoning for match"""
        reasoning_parts = []
        
        if vector_score >= 0.8:
            reasoning_parts.append("Excellent semantic match based on comprehensive profile analysis")
        elif vector_score >= 0.6:
            reasoning_parts.append("Strong semantic similarity to your profile")
        
        if riasec_similarity >= 0.9:
            reasoning_parts.append("Perfect RIASEC personality match")
        elif riasec_similarity >= 0.8:
            reasoning_parts.append("Excellent RIASEC personality alignment")
        elif riasec_similarity >= 0.7:
            reasoning_parts.append("Strong RIASEC compatibility")
        elif riasec_similarity >= 0.6:
            reasoning_parts.append("Good RIASEC personality match")
        
        if interests_similarity >= 0.8:
            reasoning_parts.append("Excellent interest cluster match")
        elif interests_similarity >= 0.6:
            reasoning_parts.append("Strong interest alignment")
        
        if aptitude_similarity >= 0.8:
            reasoning_parts.append("Excellent aptitude match with your top skills")
        elif aptitude_similarity >= 0.6:
            reasoning_parts.append("Good aptitude alignment")
        
        if reasoning_parts:
            return ". ".join(reasoning_parts)
        
        # Fallback reasoning
        if riasec_similarity > 0 or interests_similarity > 0:
            return "Good career fit based on your profile characteristics"
        
        return "Potential career option worth exploring"