# backend/services/hierarchical_recommendation_service.py
import logging
import sys
import os
from typing import Dict, List, Any, Tuple, Set
from itertools import permutations
import numpy as np

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from backend.database.mongodb import mongo_db
    from backend.config import Config
    from backend.vector_embedding_service import VectorEmbeddingService
except ImportError:
    from database.mongodb import mongo_db
    from config import Config
    from vector_embedding_service import VectorEmbeddingService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HierarchicalRecommendationService:
    """
    HIERARCHICAL RECOMMENDATION SYSTEM:
    1. STRICT RIASEC FILTERING (exact combinations only)
    2. PER-INTEREST-CLUSTER MATCHING (vector-based, separate for each user interest)
    3. APTITUDE MATCHING (vector-based)
    4. TEXT MATCHING (vector-based)
    """
    
    def __init__(self):
        self.embedding_service = None
        try:
            self.embedding_service = VectorEmbeddingService()
        except Exception as e:
            logger.error(f"Error initializing embedding service: {e}")
            raise
    
    def _get_user_profile(self, user) -> Dict:
        """Create comprehensive user profile"""
        return {
            'user_id': user.user_id,
            'name': user.name,
            'riasec_scores': user.riasec_scores,
            'riasec_code': user.riasec_code,
            'interests': user.interests,
            'education_level': user.education_level,
            'current_field': user.current_field,
            'experience_years': user.experience_years,
            'aptitude_percentiles': user.aptitude_percentiles
        }
    
    def _get_sorted_riasec_letters(self, riasec_scores: Dict[str, float]) -> List[str]:
        """Get RIASEC letters sorted by score (descending)"""
        if not riasec_scores:
            return []
        
        sorted_letters = sorted(
            riasec_scores.items(),
            key=lambda x: (-x[1], x[0])
        )
        return [letter for letter, score in sorted_letters]
    
    def _generate_riasec_combinations(self, letters: List[str]) -> Set[str]:
        """
        Generate ALL RIASEC combinations from given letters.
        For ['C', 'E', 'I']:
        - 3-letter: CEI, CIE, ECI, EIC, ICE, IEC
        - 2-letter: CE, CI, EC, EI, IC, IE
        - 1-letter: C, E, I
        """
        combinations_set = set()
        
        # Generate permutations for 1, 2, and 3 letters
        for r in range(1, min(4, len(letters) + 1)):
            for perm in permutations(letters, r):
                combinations_set.add(''.join(perm))
        
        logger.info(f"Generated {len(combinations_set)} RIASEC combinations from letters: {letters}")
        return combinations_set
    
    def _is_riasec_match(self, job_riasec: str, allowed_combinations: Set[str]) -> bool:
        """
        STRICT RIASEC MATCHING:
        Job must match one of the allowed combinations EXACTLY
        """
        if not job_riasec:
            return False
        
        # Clean and normalize
        clean_code = str(job_riasec).strip().upper().replace(' ', '').replace(',', '')
        
        if not clean_code:
            return False
        
        # Exact match check
        return clean_code in allowed_combinations
    
    def _calculate_interest_cluster_similarity(self, user_interests: List[str], job: Dict) -> float:
        """
        Calculate MAX similarity between ANY user interest and job's interest clusters.
        Uses vector similarity for each user interest separately.
        """
        if not user_interests:
            return 0.0
        
        # Get job's interest clusters text
        job_interest_parts = []
        
        # Primary interest cluster
        primary = job.get('primary_interest_cluster')
        if primary:
            job_interest_parts.append(str(primary))
        
        # Subcategories
        subcategories = job.get('interest_cluster_subcategories', [])
        if isinstance(subcategories, list):
            for sub in subcategories:
                if sub:
                    job_interest_parts.append(str(sub))
        
        # Secondary clusters
        secondary = job.get('secondary_interest_clusters', [])
        if isinstance(secondary, list):
            for sec in secondary:
                if sec:
                    job_interest_parts.append(str(sec))
        
        # RIASEC alignment (adds context)
        riasec_alignment = job.get('interest_riasec_alignment')
        if riasec_alignment:
            job_interest_parts.append(str(riasec_alignment))
        
        # Combine all job interest parts
        job_interest_text = " | ".join(job_interest_parts)
        
        if not job_interest_text.strip():
            return 0.0
        
        # Create vector for job interest text
        job_interest_vector = self.embedding_service._encode(job_interest_text)
        
        # Calculate MAX similarity with ANY user interest
        max_similarity = 0.0
        
        for user_interest in user_interests:
            if not user_interest:
                continue
            
            # Create vector for this specific user interest
            user_interest_text = f"Interest: {user_interest}"
            user_interest_vector = self.embedding_service._encode(user_interest_text)
            
            # Calculate similarity
            similarity = self.embedding_service.cosine_similarity(
                user_interest_vector, job_interest_vector
            )
            
            # Track maximum similarity
            max_similarity = max(max_similarity, similarity)
            
            # If we get a very high match, return immediately
            if similarity > 0.9:
                return similarity
        
        return max_similarity
    
    def _calculate_aptitude_similarity(self, user_aptitudes: Dict, job_aptitudes: Dict) -> float:
        """
        Calculate aptitude similarity using vectors.
        """
        if not user_aptitudes or not job_aptitudes:
            return 0.5  # Default moderate match if no data
        
        # Create text representations
        user_apt_text = " ".join([f"{k}:{v}" for k, v in user_aptitudes.items()])
        job_apt_text = " ".join([f"{k}:{v}" for k, v in job_aptitudes.items()])
        
        # Create vectors
        user_apt_vector = self.embedding_service._encode(user_apt_text)
        job_apt_vector = self.embedding_service._encode(job_apt_text)
        
        # Calculate similarity
        return self.embedding_service.cosine_similarity(user_apt_vector, job_apt_vector)
    
    def _calculate_text_similarity(self, user_profile: Dict, job: Dict) -> float:
        """
        Calculate full text similarity including field relevance.
        """
        # Create comprehensive user text
        user_text_parts = []
        
        # Education and field are VERY important
        education = user_profile.get('education_level', '')
        field = user_profile.get('current_field', '')
        experience = user_profile.get('experience_years', '')
        
        if education:
            user_text_parts.append(f"Education: {education}")
        if field:
            user_text_parts.append(f"Field: {field}")
            # Emphasize field by repeating it
            user_text_parts.append(f"Specialization: {field}")
        if experience:
            user_text_parts.append(f"Experience: {experience} years")
        
        # Interests
        interests = user_profile.get('interests', [])
        if interests:
            user_text_parts.append("Interests: " + " ".join(str(x) for x in interests))
        
        # Aptitudes
        aptitudes = user_profile.get('aptitude_percentiles', {})
        if aptitudes:
            # Only include top 3 aptitudes
            sorted_aptitudes = sorted(aptitudes.items(), key=lambda x: x[1], reverse=True)[:3]
            user_text_parts.append("Top Aptitudes: " + " ".join([f"{k}:{v}" for k, v in sorted_aptitudes]))
        
        user_text = " | ".join(user_text_parts)
        
        # Create comprehensive job text
        job_text_parts = []
        
        # Job title and family (most important)
        family_title = job.get('family_title', '')
        nco_title = job.get('nco_title', '')
        
        if family_title:
            job_text_parts.append(f"Field: {family_title}")
            job_text_parts.append(f"Category: {family_title}")
        if nco_title:
            job_text_parts.append(f"Role: {nco_title}")
        
        # Job description
        job_desc = job.get('job_description', '')
        if job_desc:
            job_text_parts.append(f"Description: {job_desc}")
        
        # Skills
        skills = job.get('primary_skills', [])
        if skills and isinstance(skills, list):
            job_text_parts.append("Skills: " + " ".join(str(s) for s in skills[:5]))
        
        # Growth and market info
        growth = job.get('industry_growth_projection', '')
        if growth:
            job_text_parts.append(f"Growth: {growth}")
        
        market = job.get('market_demand_score', '')
        if market:
            job_text_parts.append(f"Demand: {market}")
        
        # Learning pathway
        learning = job.get('learning_pathway_recommendations', '')
        if learning:
            job_text_parts.append(f"Pathway: {learning}")
        
        job_text = " | ".join(job_text_parts)
        
        # Create vectors
        user_vector = self.embedding_service._encode(user_text)
        job_vector = self.embedding_service._encode(job_text)
        
        # Calculate similarity
        return self.embedding_service.cosine_similarity(user_vector, job_vector)
    
    def _calculate_field_relevance(self, user_field: str, job: Dict) -> float:
        """
        Calculate field relevance boost (0-30%).
        Checks if user's field appears in job titles/descriptions.
        """
        if not user_field:
            return 0.0
        
        user_field_lower = user_field.lower()
        
        # Check in various job fields
        job_fields = [
            job.get('family_title', ''),
            job.get('nco_title', ''),
            job.get('job_description', ''),
            job.get('primary_interest_cluster', '')
        ]
        
        field_keywords = user_field_lower.split()
        relevance_score = 0.0
        
        for field in job_fields:
            if not field:
                continue
                
            field_lower = field.lower()
            
            # Check for exact field match
            if user_field_lower in field_lower:
                relevance_score += 0.15
            
            # Check for keyword matches
            for keyword in field_keywords:
                if len(keyword) > 3 and keyword in field_lower:
                    relevance_score += 0.05
        
        return min(0.3, relevance_score)  # Max 30% boost
    
    def _score_job_hierarchical(self, user_profile: Dict, job: Dict) -> Dict:
        """
        HIERARCHICAL SCORING:
        1. RIASEC match (exact, binary: 100% if match, 0% if not)
        2. Interest cluster match (MAX similarity with any user interest)
        3. Aptitude match (vector similarity)
        4. Text match (comprehensive vector similarity)
        5. Field relevance boost
        """
        try:
            # 1. RIASEC MATCH (already filtered, but calculate score)
            job_riasec = job.get('riasec_code', '')
            user_riasec_code = user_profile.get('riasec_code', '')
            
            # Clean both codes
            job_riasec_clean = str(job_riasec).strip().upper().replace(' ', '').replace(',', '')
            user_riasec_clean = str(user_riasec_code).strip().upper().replace(' ', '').replace(',', '')
            
            # RIASEC score: 100% if job code is subset/permutation of user code
            riasec_score = 0.0
            if job_riasec_clean and user_riasec_clean:
                # Check if job code is permutation of user code
                job_letters = set(job_riasec_clean)
                user_letters = set(user_riasec_clean)
                
                if job_letters.issubset(user_letters):
                    # Length-based scoring: longer matches are better
                    base_score = 0.8  # Base for subset match
                    length_bonus = len(job_riasec_clean) * 0.05  # 5% per letter
                    riasec_score = min(1.0, base_score + length_bonus)
                    
                    # Exact match bonus
                    if job_riasec_clean == user_riasec_clean:
                        riasec_score = 1.0
            
            # 2. INTEREST CLUSTER MATCH (per-interest, MAX similarity)
            user_interests = user_profile.get('interests', [])
            interest_score = self._calculate_interest_cluster_similarity(user_interests, job)
            
            # 3. APTITUDE MATCH
            user_aptitudes = user_profile.get('aptitude_percentiles', {})
            job_aptitudes = job.get('aptitude_scores', {})
            aptitude_score = self._calculate_aptitude_similarity(user_aptitudes, job_aptitudes)
            
            # 4. TEXT MATCH (comprehensive)
            text_score = self._calculate_text_similarity(user_profile, job)
            
            # 5. FIELD RELEVANCE BOOST
            user_field = user_profile.get('current_field', '')
            field_boost = self._calculate_field_relevance(user_field, job)
            
            # WEIGHTS (adjust based on importance)
            weights = {
                'riasec': 0.40,    # 40% - most important
                'interests': 0.35,  # 35% - per-interest matching
                'aptitude': 0.15,   # 15% - aptitude alignment
                'text': 0.10        # 10% - overall text match
            }
            
            # Calculate weighted score
            weighted_score = (
                riasec_score * weights['riasec'] +
                interest_score * weights['interests'] +
                aptitude_score * weights['aptitude'] +
                text_score * weights['text']
            )
            
            # Add field boost
            final_score = min(1.0, weighted_score + field_boost)
            
            # Convert to percentage
            match_percentage = round(final_score * 100)
            
            # Generate detailed reasoning
            reasoning_parts = []
            
            if riasec_score >= 0.9:
                reasoning_parts.append(f"Perfect RIASEC match: {job_riasec}")
            elif riasec_score >= 0.7:
                reasoning_parts.append(f"Strong RIASEC alignment: {job_riasec}")
            
            if interest_score >= 0.8:
                reasoning_parts.append("Excellent interest cluster match")
            elif interest_score >= 0.6:
                reasoning_parts.append("Good interest alignment")
            
            if aptitude_score >= 0.7:
                reasoning_parts.append("Strong aptitude fit")
            
            if field_boost >= 0.2:
                reasoning_parts.append(f"Highly relevant to your field: {user_field}")
            elif field_boost > 0:
                reasoning_parts.append(f"Relevant to your field: {user_field}")
            
            reasoning = ". ".join(reasoning_parts) if reasoning_parts else "Good career match based on your profile"
            
            return {
                "job_id": job.get("job_id", ""),
                "job_title": job.get("nco_title", ""),
                "family_title": job.get("family_title", ""),
                "riasec_code": job.get("riasec_code", ""),
                "match_percentage": match_percentage,
                "job_description": job.get("job_description", ""),
                "primary_skills": job.get("primary_skills", []),
                "salary_range": job.get("salary_range_analysis", "Not specified"),
                "market_demand": job.get("market_demand_score", "Medium"),
                "growth_projection": job.get("industry_growth_projection", ""),
                "learning_pathway": job.get("learning_pathway_recommendations", ""),
                "aptitude_scores": job.get("aptitude_scores", {}),
                "similarity_breakdown": {
                    "riasec": round(riasec_score * 100),
                    "interests": round(interest_score * 100),
                    "aptitude": round(aptitude_score * 100),
                    "text": round(text_score * 100),
                    "field_boost": round(field_boost * 100)
                },
                "weighted_score": round(weighted_score * 100, 1),
                "final_score": final_score,
                "reasoning": reasoning,
                "primary_interest_cluster": job.get("primary_interest_cluster", ""),
                "interest_clusters": {
                    "primary": job.get("primary_interest_cluster", ""),
                    "subcategories": job.get("interest_cluster_subcategories", []),
                    "secondary": job.get("secondary_interest_clusters", [])
                }
            }
            
        except Exception as e:
            logger.error(f"Error scoring job {job.get('job_id')}: {e}")
            return {
                "job_id": job.get("job_id", ""),
                "job_title": job.get("nco_title", ""),
                "match_percentage": 0,
                "similarity_breakdown": {
                    "riasec": 0,
                    "interests": 0,
                    "aptitude": 0,
                    "text": 0,
                    "field_boost": 0
                },
                "reasoning": f"Error in calculation: {str(e)}"
            }
    
    def generate_recommendations(self, user, min_score: int = 20) -> Dict:
        """
        HIERARCHICAL RECOMMENDATION GENERATION:
        1. Strict RIASEC filtering
        2. Per-interest-cluster matching
        3. Comprehensive scoring
        """
        logger.info(f"🎯 Generating HIERARCHICAL recommendations for {user.name}")
        
        try:
            user_profile = self._get_user_profile(user)
            
            # Get user's RIASEC scores
            riasec_scores = user_profile.get('riasec_scores', {})
            if not riasec_scores:
                return {
                    "success": False,
                    "error": "User has not completed RIASEC assessment",
                    "recommendations": []
                }
            
            # Get user's top 3 letters
            sorted_letters = self._get_sorted_riasec_letters(riasec_scores)
            top_letters = sorted_letters[:3]
            logger.info(f"User's top 3 RIASEC letters: {top_letters}")
            
            # Generate allowed RIASEC combinations
            allowed_combinations = self._generate_riasec_combinations(top_letters)
            
            # Get all jobs
            all_jobs = self._get_all_jobs()
            if not all_jobs:
                return {
                    "success": False,
                    "error": "No jobs available in database",
                    "recommendations": []
                }
            
            logger.info(f"Total jobs in database: {len(all_jobs)}")
            
            # STEP 1: STRICT RIASEC FILTERING
            riasec_filtered_jobs = []
            for job in all_jobs:
                job_riasec = job.get('riasec_code', '')
                if self._is_riasec_match(job_riasec, allowed_combinations):
                    riasec_filtered_jobs.append(job)
            
            logger.info(f"Jobs after STRICT RIASEC filtering: {len(riasec_filtered_jobs)} of {len(all_jobs)}")
            
            # If no jobs with top 3, try top 4
            if not riasec_filtered_jobs:
                logger.info(f"No jobs with top 3 letters {top_letters}, expanding to top 4")
                top_letters = sorted_letters[:4]
                allowed_combinations = self._generate_riasec_combinations(top_letters)
                
                riasec_filtered_jobs = []
                for job in all_jobs:
                    if self._is_riasec_match(job.get('riasec_code', ''), allowed_combinations):
                        riasec_filtered_jobs.append(job)
                
                logger.info(f"Jobs after top-4 RIASEC filtering: {len(riasec_filtered_jobs)}")
            
            # STEP 2: PER-INTEREST-CLUSTER MATCHING & SCORING
            scored_recommendations = []
            
            for job in riasec_filtered_jobs:
                score_data = self._score_job_hierarchical(user_profile, job)
                
                if score_data["match_percentage"] >= min_score:
                    scored_recommendations.append(score_data)
            
            # Sort by match percentage
            scored_recommendations.sort(key=lambda x: x["match_percentage"], reverse=True)
            
            logger.info(f"Final recommendations: {len(scored_recommendations)} jobs")
            
            # Show top 5 jobs for debugging
            logger.info("Top 5 recommended jobs:")
            for i, job in enumerate(scored_recommendations[:5]):
                logger.info(f"  {i+1}. {job['job_title']} - {job['match_percentage']}%")
                logger.info(f"     RIASEC: {job['riasec_code']}, Interests: {job.get('interest_clusters', {}).get('primary', '')}")
                logger.info(f"     Breakdown: RIASEC={job['similarity_breakdown']['riasec']}%, "
                          f"Interests={job['similarity_breakdown']['interests']}%, "
                          f"Field={job['similarity_breakdown']['field_boost']}%")
            
            return {
                "success": True,
                "recommendations": scored_recommendations,
                "filter_stats": {
                    "total_jobs": len(all_jobs),
                    "riasec_filtered": len(riasec_filtered_jobs),
                    "final_count": len(scored_recommendations),
                    "riasec_strategy": "top-3" if len(sorted_letters[:3]) == 3 else "top-4",
                    "user_top_letters": top_letters,
                    "user_interests": user_profile.get('interests', [])
                },
                "user_profile": self._serialize_user_profile(user_profile)
            }
            
        except Exception as e:
            logger.error(f"❌ Error generating recommendations: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                "success": False,
                "error": str(e),
                "recommendations": []
            }
    
    def _get_all_jobs(self) -> List[Dict]:
        """Retrieve all jobs from database"""
        try:
            jobs_collection = mongo_db.get_jobs_collection()
            
            jobs = list(jobs_collection.find(
                {},
                {
                    "_id": 0,
                    "job_id": 1,
                    "family_title": 1,
                    "nco_title": 1,
                    "riasec_code": 1,
                    "job_description": 1,
                    "primary_skills": 1,
                    "primary_interest_cluster": 1,
                    "interest_cluster_subcategories": 1,
                    "secondary_interest_clusters": 1,
                    "interest_riasec_alignment": 1,
                    "salary_range_analysis": 1,
                    "market_demand_score": 1,
                    "industry_growth_projection": 1,
                    "learning_pathway_recommendations": 1,
                    "aptitude_scores": 1
                }
            ))
            
            return jobs
            
        except Exception as e:
            logger.error(f"Error retrieving jobs: {e}")
            return []
    
    def _serialize_user_profile(self, user_profile: Dict) -> Dict:
        """Convert user profile to JSON-serializable format"""
        try:
            return {
                "name": user_profile.get('name', ''),
                "current_field": user_profile.get('current_field', ''),
                "education_level": user_profile.get('education_level', ''),
                "experience_years": user_profile.get('experience_years', 0),
                "riasec_code": user_profile.get('riasec_code', ''),
                "riasec_scores": user_profile.get('riasec_scores', {}),
                "interests": user_profile.get('interests', []),
                "aptitude_percentiles": user_profile.get('aptitude_percentiles', {})
            }
        except Exception as e:
            logger.error(f"Error serializing user profile: {e}")
            return {}