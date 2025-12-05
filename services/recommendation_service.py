# backend/services/hierarchical_recommendation_service.py
import logging
import sys
import os
from typing import Dict, List, Any, Tuple, Set
from itertools import permutations
import numpy as np
from collections import defaultdict

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
    2. CLUSTER-WISE GROUPING (group by primary interest cluster)
    3. HIGH-QUALITY MATCHING (80%+ threshold within clusters)
    4. PER-INTEREST-CLUSTER MATCHING (vector-based, separate for each user interest)
    5. APTITUDE MATCHING (vector-based)
    6. TEXT MATCHING (vector-based)
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
    
    def _extract_job_clusters(self, job: Dict) -> List[str]:
        """
        Extract all interest clusters from a job.
        Returns a list of unique cluster names.
        """
        clusters = []
        
        # Primary cluster
        primary = job.get('primary_interest_cluster')
        if primary and primary not in clusters:
            clusters.append(primary)
        
        # Secondary clusters
        secondary = job.get('secondary_interest_clusters', [])
        if isinstance(secondary, list):
            for sec in secondary:
                if sec and sec not in clusters:
                    clusters.append(sec)
        
        # Subcategories (as potential clusters)
        subcategories = job.get('interest_cluster_subcategories', [])
        if isinstance(subcategories, list):
            for sub in subcategories:
                if sub and sub not in clusters:
                    clusters.append(sub)
        
        return clusters
    
    def _calculate_interest_cluster_similarity(self, user_interests: List[str], job: Dict) -> Tuple[float, str]:
        """
        Calculate MAX similarity between ANY user interest and job's interest clusters.
        Returns the similarity score and the best matching cluster.
        """
        if not user_interests:
            return 0.0, ""
        
        # Get job's interest clusters text
        job_clusters = {}
        
        # Primary interest cluster
        primary = job.get('primary_interest_cluster')
        if primary:
            job_clusters[primary] = str(primary)
        
        # Subcategories
        subcategories = job.get('interest_cluster_subcategories', [])
        if isinstance(subcategories, list):
            for sub in subcategories:
                if sub and sub not in job_clusters:
                    job_clusters[sub] = str(sub)
        
        # Secondary clusters
        secondary = job.get('secondary_interest_clusters', [])
        if isinstance(secondary, list):
            for sec in secondary:
                if sec and sec not in job_clusters:
                    job_clusters[sec] = str(sec)
        
        # RIASEC alignment (adds context)
        riasec_alignment = job.get('interest_riasec_alignment')
        if riasec_alignment:
            for cluster in list(job_clusters.keys()):
                job_clusters[cluster] += f" | RIASEC: {riasec_alignment}"
        
        max_similarity = 0.0
        best_cluster = ""
        
        for user_interest in user_interests:
            if not user_interest:
                continue
            
            user_interest_text = f"Interest: {user_interest}"
            user_interest_vector = self.embedding_service._encode(user_interest_text)
            
            for cluster_name, cluster_text in job_clusters.items():
                if not cluster_text:
                    continue
                
                # Create vector for this specific cluster
                cluster_vector = self.embedding_service._encode(cluster_text)
                
                # Calculate similarity
                similarity = self.embedding_service.cosine_similarity(
                    user_interest_vector, cluster_vector
                )
                
                if similarity > max_similarity:
                    max_similarity = similarity
                    best_cluster = cluster_name
                
                # If we get a very high match, return immediately
                if similarity > 0.95:
                    return similarity, cluster_name
        
        return max_similarity, best_cluster
    
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
        HIERARCHICAL SCORING WITH TRUE FIELD BONUS:
        1. RIASEC match (40%)
        2. Interest cluster match (35%)
        3. Aptitude match (15%)
        4. Text match (10%)
        + FIELD BONUS (0–10 points added AFTER weighted score)
        """
        try:
            # 1. RIASEC MATCH
            job_riasec = job.get('riasec_code', '')
            user_riasec_code = user_profile.get('riasec_code', '')

            job_riasec_clean = str(job_riasec).strip().upper().replace(' ', '').replace(',', '')
            user_riasec_clean = str(user_riasec_code).strip().upper().replace(' ', '').replace(',', '')

            riasec_score = 0.0
            if job_riasec_clean and user_riasec_clean:
                job_letters = set(job_riasec_clean)
                user_letters = set(user_riasec_clean)

                if job_letters.issubset(user_letters):
                    base_score = 0.8
                    length_bonus = len(job_riasec_clean) * 0.05
                    riasec_score = min(1.0, base_score + length_bonus)

                    if job_riasec_clean == user_riasec_clean:
                        riasec_score = 1.0

            # 2. INTEREST MATCH
            user_interests = user_profile.get('interests', [])
            interest_score, matched_cluster = self._calculate_interest_cluster_similarity(user_interests, job)

            # 3. APTITUDE MATCH
            user_aptitudes = user_profile.get('aptitude_percentiles', {})
            job_aptitudes = job.get('aptitude_scores', {})
            aptitude_score = self._calculate_aptitude_similarity(user_aptitudes, job_aptitudes)

            # 4. TEXT MATCH
            text_score = self._calculate_text_similarity(user_profile, job)

            # ==========================
            # ✅ IMPROVED FIELD BONUS LOGIC (0-15)
            # ==========================
            user_field = user_profile.get('current_field', '').lower().strip()
            field_bonus = 0

            if user_field and user_field not in ['', 'not specified', 'none', 'undefined']:
                # Get job information
                job_title = job.get('nco_title', '').lower()
                job_family = job.get('family_title', '').lower()
                job_desc = job.get('job_description', '').lower()
                job_cluster = job.get('primary_interest_cluster', '').lower()
                
                # Get user's field keywords
                user_field_lower = user_field.lower().strip()
                
                # Remove common filler words
                filler_words = {'and', 'or', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 
                            'for', 'with', 'by', 'of', 'field', 'area', 'domain', 'sector'}
                field_keywords = [w for w in user_field_lower.split() if w not in filler_words and len(w) > 2]
                
                if not field_keywords:
                    field_keywords = [user_field_lower]
                
                # Combine all job text for checking
                all_job_text = f"{job_title} {job_family} {job_desc} {job_cluster}".lower()
                
                # ==========================
                # STRICT FIELD BONUS RULES
                # ==========================
                
                # RULE 1: EXACT JOB TITLE MATCH → +15
                # User's field appears as the main part of job title
                exact_title_match = False
                for keyword in field_keywords:
                    if len(keyword) >= 4:
                        # Check if keyword is in job title as a major component
                        words_in_title = job_title.split()
                        if keyword in words_in_title:
                            # Check position - if it's first or second word, it's important
                            if keyword in words_in_title[:2]:
                                field_bonus = 15
                                exact_title_match = True
                                logger.debug(f"Exact title match: '{keyword}' in '{job_title}' → +15")
                                break
                
                # RULE 2: JOB FAMILY/CATEGORY MATCH → +10
                if not exact_title_match:
                    for keyword in field_keywords:
                        if len(keyword) >= 4:
                            # Check in job family (category)
                            if keyword in job_family:
                                field_bonus = 10
                                exact_title_match = True
                                logger.debug(f"Family match: '{keyword}' in '{job_family}' → +10")
                                break
                
                # RULE 3: PRIMARY CLUSTER MATCH → +6
                if not exact_title_match and matched_cluster:
                    cluster_lower = matched_cluster.lower()
                    for keyword in field_keywords:
                        if len(keyword) >= 4 and keyword in cluster_lower:
                            field_bonus = 6
                            exact_title_match = True
                            logger.debug(f"Cluster match: '{keyword}' in '{cluster_lower}' → +6")
                            break
                
                # RULE 4: SKILLS/DESCRIPTION MATCH → +4
                if not exact_title_match:
                    # Check job skills and description
                    job_skills = ' '.join(job.get('primary_skills', []) if isinstance(job.get('primary_skills', []), list) else []).lower()
                    learning_path = job.get('learning_pathway_recommendations', '').lower()
                    
                    skills_desc_text = f"{job_skills} {learning_path}".lower()
                    
                    keyword_hits = 0
                    for keyword in field_keywords:
                        if len(keyword) >= 4:
                            # Check in skills/description
                            if keyword in skills_desc_text:
                                keyword_hits += 1
                    
                    if keyword_hits >= 2:  # Need at least 2 keyword matches in skills/description
                        field_bonus = 4
                        logger.debug(f"Skills match: {keyword_hits} keywords → +4")
                
                # Log field bonus decision
                if field_bonus > 0:
                    logger.info(f"Field bonus {field_bonus} for '{job_title}' (user field: '{user_field}')")
                else:
                    logger.debug(f"No field bonus for '{job_title}' (user field: '{user_field}')")

            # ==========================
            # ✅ WEIGHTED SCORING
            # ==========================
            weights = {
                'riasec': 0.40,
                'interests': 0.35,
                'aptitude': 0.15,
                'text': 0.10
            }

            weighted_score = (
                riasec_score * weights['riasec'] +
                interest_score * weights['interests'] +
                aptitude_score * weights['aptitude'] +
                text_score * weights['text']
            )

            # ✅ Convert base to percentage FIRST
            base_match_percent = weighted_score * 100

            # ✅ ADD FIELD BONUS AS PURE POINTS
            final_match_percent = min(100, round(base_match_percent + field_bonus))

            # ==========================
            # ✅ CORRECTED REASONING
            # ==========================
            reasoning_parts = []

            if riasec_score >= 0.9:
                reasoning_parts.append(f"Perfect RIASEC match: {job_riasec}")
            elif riasec_score >= 0.7:
                reasoning_parts.append(f"Strong RIASEC alignment: {job_riasec}")

            if interest_score >= 0.8:
                reasoning_parts.append(f"Excellent match with {matched_cluster} cluster")
            elif interest_score >= 0.6:
                reasoning_parts.append(f"Good match with {matched_cluster} cluster")

            if aptitude_score >= 0.7:
                reasoning_parts.append("Strong aptitude fit")

            # CORRECTED FIELD BONUS REASONING
            if field_bonus == 15:
                reasoning_parts.append(f"Perfect field-title match: {user_field} (+15 bonus)")
            elif field_bonus == 10:
                reasoning_parts.append(f"Field-category match: {user_field} (+10 bonus)")
            elif field_bonus == 6:
                reasoning_parts.append(f"Field-cluster alignment: {user_field} (+6 bonus)")
            elif field_bonus == 4:
                reasoning_parts.append(f"Skills/description match: {user_field} (+4 bonus)")

            reasoning = ". ".join(reasoning_parts) if reasoning_parts else "Good career match based on your profile"

            # ==========================
            # ✅ FINAL OUTPUT
            # ==========================
            primary_cluster = job.get("primary_interest_cluster", "") or matched_cluster

            return {
                "job_id": job.get("job_id", ""),
                "job_title": job.get("nco_title", ""),
                "family_title": job.get("family_title", ""),
                "riasec_code": job.get("riasec_code", ""),
                "match_percentage": final_match_percent,

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
                    "field_bonus": field_bonus
                },

                "weighted_score": round(base_match_percent, 1),
                "final_score": final_match_percent / 100,
                "field_bonus": field_bonus,

                "reasoning": reasoning,
                "primary_cluster": primary_cluster,
                "matched_cluster": matched_cluster,
                "all_clusters": self._extract_job_clusters(job),

                "interest_clusters": {
                    "primary": primary_cluster,
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
                "primary_cluster": job.get("primary_interest_cluster", ""),
                "similarity_breakdown": {
                    "riasec": 0,
                    "interests": 0,
                    "aptitude": 0,
                    "text": 0,
                    "field_bonus": 0
                },
                "reasoning": f"Error in calculation: {str(e)}"
            }

    
    def _organize_by_clusters(self, jobs: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Organize jobs by their primary interest cluster.
        Returns a dict with cluster_name -> list of jobs
        """
        clusters = defaultdict(list)
        
        for job in jobs:
            # Get primary cluster
            primary_cluster = job.get("primary_cluster", "")
            
            if not primary_cluster:
                # Try to get from other fields
                primary_cluster = job.get("matched_cluster", "")
                if not primary_cluster and job.get("interest_clusters", {}).get("primary"):
                    primary_cluster = job["interest_clusters"]["primary"]
            
            # If still no cluster, use "Other"
            if not primary_cluster:
                primary_cluster = "Other"
            
            clusters[primary_cluster].append(job)
        
        # Sort clusters by number of jobs (descending)
        sorted_clusters = dict(sorted(
            clusters.items(), 
            key=lambda x: len(x[1]), 
            reverse=True
        ))
        
        # Sort jobs within each cluster by match percentage (descending)
        for cluster_name, cluster_jobs in sorted_clusters.items():
            sorted_clusters[cluster_name] = sorted(
                cluster_jobs, 
                key=lambda x: x.get("match_percentage", 0), 
                reverse=True
            )
        
        return sorted_clusters
    
    def _filter_high_quality_matches(self, jobs: List[Dict], min_score: int = 80) -> List[Dict]:
        """
        Filter jobs to only include high-quality matches (80%+).
        Also ensures we get at least some jobs even if none are 80%+.
        """
        high_quality = [job for job in jobs if job.get("match_percentage", 0) >= min_score]
        
        # If no high-quality matches, return top 10 overall
        if not high_quality and jobs:
            logger.info(f"No jobs with {min_score}%+ match. Returning top 10 overall.")
            return sorted(jobs, key=lambda x: x.get("match_percentage", 0), reverse=True)[:10]
        
        return high_quality
    
    def generate_recommendations(self, user, min_score: int = 80) -> Dict:
        """
        HIERARCHICAL RECOMMENDATION GENERATION:
        1. Strict RIASEC filtering
        2. Filter by user's selected interest clusters
        3. Per-interest-cluster matching
        4. Cluster-wise organization
        5. High-quality filtering (80%+ by default)
        """
        logger.info(f"🎯 Generating CLUSTER-WISE recommendations for {user.name} (min {min_score}%)")
        
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
            
            # Get user's selected interests
            user_interests = user_profile.get('interests', [])
            logger.info(f"User's selected interest clusters: {user_interests}")
            
            # Normalize user interests for better matching
            normalized_user_interests = []
            for interest in user_interests:
                if interest:
                    # Remove common variations
                    interest_normalized = interest.lower().strip()
                    # Map common variations to standard names
                    interest_mapping = {
                        'social and community service': 'Social and Community Service',
                        'healthcare and wellness': 'Healthcare and Wellness', 
                        'finance and economics': 'Finance and Economics',
                        'technology': 'Technology',
                        'engineering': 'Engineering',
                        'business': 'Business',
                        'arts': 'Arts',
                        'education': 'Education'
                    }
                    
                    # Try to find matching standard name
                    matched_standard = None
                    for key, value in interest_mapping.items():
                        if key in interest_normalized or interest_normalized in key:
                            matched_standard = value
                            break
                    
                    if matched_standard:
                        normalized_user_interests.append(matched_standard)
                    else:
                        normalized_user_interests.append(interest.strip())
            
            logger.info(f"Normalized user interests: {normalized_user_interests}")
            
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
            
            # STEP 2: FILTER BY USER'S INTEREST CLUSTERS
            interest_filtered_jobs = []
            
            if normalized_user_interests:
                # Create normalized sets for matching
                user_interest_set = {interest.lower().strip() for interest in normalized_user_interests if interest}
                
                # Also create keyword sets for partial matching
                user_interest_keywords = set()
                for interest in user_interest_set:
                    words = interest.split()
                    user_interest_keywords.update([word for word in words if len(word) > 3])
                
                for job in riasec_filtered_jobs:
                    # Extract all clusters from the job
                    job_clusters = self._extract_job_clusters(job)
                    
                    # Also get primary cluster separately
                    primary_cluster = job.get('primary_interest_cluster', '')
                    if primary_cluster and primary_cluster not in job_clusters:
                        job_clusters.append(primary_cluster)
                    
                    # Check if any job cluster matches user interests
                    match_found = False
                    
                    for cluster in job_clusters:
                        if not cluster:
                            continue
                        
                        cluster_lower = cluster.lower().strip()
                        
                        # Check direct match
                        if cluster_lower in user_interest_set:
                            match_found = True
                            logger.debug(f"Direct cluster match: {cluster} matches user interest")
                            break
                        
                        # Check partial match
                        for user_interest in user_interest_set:
                            if (user_interest in cluster_lower or 
                                cluster_lower in user_interest):
                                match_found = True
                                logger.debug(f"Partial cluster match: {cluster} partially matches {user_interest}")
                                break
                        
                        if match_found:
                            break
                    
                    # If still no match, check keyword matching
                    if not match_found and user_interest_keywords:
                        for cluster in job_clusters:
                            if not cluster:
                                continue
                            
                            cluster_lower = cluster.lower()
                            cluster_words = set(cluster_lower.split())
                            
                            # Check for keyword overlap
                            if user_interest_keywords.intersection(cluster_words):
                                match_found = True
                                logger.debug(f"Keyword match: {cluster} shares keywords with user interests")
                                break
                    
                    if match_found:
                        interest_filtered_jobs.append(job)
            else:
                # If user has no specific interests, use all RIASEC-filtered jobs
                interest_filtered_jobs = riasec_filtered_jobs
            
            logger.info(f"Jobs after INTEREST CLUSTER filtering: {len(interest_filtered_jobs)} of {len(riasec_filtered_jobs)}")
            
            # STEP 3: PER-INTEREST-CLUSTER MATCHING & SCORING
            scored_recommendations = []
            
            for job in interest_filtered_jobs:
                score_data = self._score_job_hierarchical(user_profile, job)
                scored_recommendations.append(score_data)
            
            # STEP 4: FILTER FOR HIGH-QUALITY MATCHES (80%+)
            high_quality_jobs = self._filter_high_quality_matches(scored_recommendations, min_score)
            
            # STEP 5: ORGANIZE BY CLUSTERS
            clustered_jobs = self._organize_by_clusters(high_quality_jobs)
            
            # ENSURE ALL USER INTEREST CLUSTERS ARE REPRESENTED
            # Create placeholder clusters for user interests that have no jobs
            final_clusters = {}
            
            # First, add clusters that have jobs
            for cluster_name, cluster_jobs in clustered_jobs.items():
                if cluster_name and cluster_jobs:
                    final_clusters[cluster_name] = cluster_jobs
            
            # Check which user interests are not represented
            user_interest_names = [interest for interest in normalized_user_interests if interest]
            
            for user_interest in user_interest_names:
                interest_found = False
                
                # Check if this interest matches any existing cluster
                user_interest_lower = user_interest.lower()
                
                for cluster_name in final_clusters.keys():
                    cluster_name_lower = cluster_name.lower()
                    
                    # Check for match
                    if (user_interest_lower in cluster_name_lower or 
                        cluster_name_lower in user_interest_lower or
                        any(word in cluster_name_lower for word in user_interest_lower.split() if len(word) > 3)):
                        interest_found = True
                        break
                
                # If interest not found, try to find lower quality matches for this cluster
                if not interest_found:
                    logger.info(f"No high-quality jobs found for interest cluster: {user_interest}")
                    
                    # Look for lower quality matches for this specific interest
                    interest_specific_jobs = []
                    for job in scored_recommendations:
                        # Check job clusters against this specific interest
                        job_clusters = job.get('all_clusters', [])
                        primary_cluster = job.get('primary_cluster', '')
                        
                        match_found = False
                        for cluster in [primary_cluster] + job_clusters:
                            if not cluster:
                                continue
                            
                            cluster_lower = cluster.lower()
                            if (user_interest_lower in cluster_lower or 
                                cluster_lower in user_interest_lower):
                                match_found = True
                                break
                        
                        if match_found and job.get('match_percentage', 0) >= 60:  # Lower threshold
                            interest_specific_jobs.append(job)
                    
                    # If found some jobs, add them as a cluster
                    if interest_specific_jobs:
                        # Sort by match percentage
                        interest_specific_jobs.sort(key=lambda x: x.get("match_percentage", 0), reverse=True)
                        # Take top 5
                        top_jobs = interest_specific_jobs[:5]
                        
                        final_clusters[user_interest] = top_jobs
                        logger.info(f"Added {len(top_jobs)} lower quality jobs for cluster: {user_interest}")
            
            # If still no clusters, use all high quality jobs
            if not final_clusters and high_quality_jobs:
                logger.info("No clusters match user interests exactly, showing all high-quality jobs")
                final_clusters = clustered_jobs
            
            # Prepare final recommendations
            final_recommendations = []
            
            for cluster_name, cluster_jobs in final_clusters.items():
                # Get top 5 jobs per cluster
                top_jobs_in_cluster = cluster_jobs[:5]
                
                # Calculate cluster statistics
                cluster_stats = {
                    "cluster_name": cluster_name,
                    "total_jobs": len(cluster_jobs),
                    "average_match": round(sum(j.get("match_percentage", 0) for j in cluster_jobs) / len(cluster_jobs) if cluster_jobs else 0),
                    "top_match": cluster_jobs[0].get("match_percentage", 0) if cluster_jobs else 0,
                    "user_requested": any(
                        user_interest.lower() in cluster_name.lower() or 
                        cluster_name.lower() in user_interest.lower()
                        for user_interest in normalized_user_interests
                    )
                }
                
                cluster_data = {
                    "cluster": cluster_name,
                    "cluster_stats": cluster_stats,
                    "jobs": top_jobs_in_cluster
                }
                
                final_recommendations.append(cluster_data)
            
            # Sort clusters: user-requested clusters first, then by average match
            final_recommendations.sort(
                key=lambda x: (
                    -x["cluster_stats"].get("user_requested", False),
                    -x["cluster_stats"]["average_match"]
                )
            )
            
            # Log summary
            logger.info(f"Final cluster-wise recommendations:")
            total_jobs_shown = sum(len(cluster["jobs"]) for cluster in final_recommendations)
            logger.info(f"Total jobs shown: {total_jobs_shown}")
            logger.info(f"Number of clusters: {len(final_recommendations)}")
            
            user_requested_clusters = [c for c in final_recommendations if c["cluster_stats"].get("user_requested", False)]
            logger.info(f"User-requested clusters shown: {len(user_requested_clusters)} of {len(normalized_user_interests)}")
            
            for cluster in final_recommendations:
                cluster_name = cluster['cluster']
                is_requested = cluster["cluster_stats"].get("user_requested", False)
                requested_marker = "✅" if is_requested else "  "
                logger.info(f"  {requested_marker} {cluster_name}: {len(cluster['jobs'])} jobs, avg match: {cluster['cluster_stats']['average_match']}%")
                
            return {
                "success": True,
                "recommendations": final_recommendations,
                "filter_stats": {
                    "total_jobs": len(all_jobs),
                    "riasec_filtered": len(riasec_filtered_jobs),
                    "interest_filtered": len(interest_filtered_jobs),
                    "high_quality_matches": len(high_quality_jobs),
                    "clusters_count": len(final_recommendations),
                    "user_requested_clusters_shown": len(user_requested_clusters),
                    "user_total_interests": len(normalized_user_interests),
                    "riasec_strategy": "top-3" if len(sorted_letters[:3]) == 3 else "top-4",
                    "user_top_letters": top_letters,
                    "user_interests": normalized_user_interests,
                    "quality_threshold": min_score
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