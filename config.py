import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

EMBEDDING_MODEL = 'all-MiniLM-L6-v2'  # Same as ChromaDB
EMBEDDING_DIMENSION = 384  # Dimension for all-MiniLM-L6-v2
VECTOR_SEARCH_INDEX_NAME = 'career_vectors_new'

class Config:
    """Base configuration"""
    # Security - MUST be set in environment
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
    # Debug mode - default to False for safety
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    # MongoDB Configuration - MUST be set in environment
    MONGO_URI = os.environ.get('MONGO_URI')
    
    # Recommendation system configuration
    TIE_BREAKER_DELTA = int(os.environ.get('TIE_BREAKER_DELTA', '1'))
    MAX_TIE_BREAKER_ROUNDS = int(os.environ.get('MAX_TIE_BREAKER_ROUNDS', '3'))
    
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

    # Aptitude Categories
    APTITUDE_CATEGORIES = [
        "Mechanical", "Spatial/Design", "Logical Reasoning", 
        "Organizing/Structuring", "Digital/Computer", "Scientific",
        "Numerical", "Creative", "Writing/Expression", 
        "Social/Helping", "Verbal Communication", "Leadership/Persuasion"
    ]
    
    # Configuration validation
    @classmethod
    def validate(cls):
        """Validate that all required environment variables are set"""
        errors = []
        
        # Check required variables
        if not cls.MONGO_URI:
            errors.append("MONGO_URI is not set in environment variables")
        if not cls.SECRET_KEY:
            errors.append("SECRET_KEY is not set in environment variables")
        
        # Warn about default values
        if cls.DEBUG:
            print("⚠️ WARNING: Debug mode is enabled. Disable in production!")
        
        if errors:
            error_msg = "\n".join(errors)
            raise ValueError(f"Configuration validation failed:\n{error_msg}")
        
        return True


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


# Determine which configuration to use based on environment
def get_config():
    """Get the appropriate configuration based on environment"""
    env = os.environ.get('FLASK_ENV', 'development')
    
    config_map = {
        'development': DevelopmentConfig,
        'production': ProductionConfig,
        'default': DevelopmentConfig
    }
    
    config_class = config_map.get(env, config_map['default'])
    config = config_class()
    
    # Validate configuration
    try:
        config.validate()
        return config
    except ValueError as e:
        print(f"❌ Configuration Error: {e}")
        print("💡 Make sure you have a .env file with all required variables")
        print("💡 Or set environment variables directly")
        raise


# Create a config instance
config = get_config()