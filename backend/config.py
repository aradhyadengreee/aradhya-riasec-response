import os
from dotenv import load_dotenv

load_dotenv()

EMBEDDING_MODEL = 'all-MiniLM-L6-v2'  # Same as ChromaDB
EMBEDDING_DIMENSION = 384  # Dimension for all-MiniLM-L6-v2
VECTOR_SEARCH_INDEX_NAME = 'career_vectors_new'

class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_secret_key_change_in_production')
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    # MongoDB Configuration
    MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/career_counseling')
    
    # Tie-breaker configuration
    TIE_BREAKER_DELTA = int(os.environ.get('TIE_BREAKER_DELTA', 1))
    
    # Session configuration
    SESSION_PERMANENT = False
    SESSION_TYPE = 'filesystem'
    
    # Career Matching Weights
    RIASEC_EXACT_MATCH_WEIGHT = 0.35  # For exact RIASEC code match
    RIASEC_PARTIAL_MATCH_WEIGHT = 0.15  # For partial RIASEC match
    INTEREST_CLUSTER_EXACT_MATCH_WEIGHT = 0.25  # For exact interest cluster match
    INTEREST_CLUSTER_SEMANTIC_WEIGHT = 0.15  # For semantic similarity
    FIELD_MATCH_WEIGHT = 0.08  # For field relevance
    APTITUDE_MATCH_WEIGHT = 0.02  # For aptitude match
    # Interest Clusters
    INTEREST_CLUSTERS = [
        "Engineering and Technical Skills",
        "Art and Design", 
        "Social and Community Service",
        "Environmental and Sustainable Development",
        "Science and Research",
        "Healthcare and Wellness",
        "Business and Entrepreneurship",
        "Technology and Innovation",
        "Finance and Economics"
    ]

    APTITUDE_CATEGORIES = [
    "Mechanical", "Spatial/Design", "Logical Reasoning", 
    "Organizing/Structuring", "Digital/Computer", "Scientific",
    "Numerical", "Creative", "Writing/Expression", 
    "Social/Helping", "Verbal Communication", "Leadership/Persuasion"
    ]
    
class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 1800

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}