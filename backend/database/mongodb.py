# mongodb.py (updated for Atlas)
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from config import Config
import logging

logger = logging.getLogger(__name__)

class MongoDB:
    _instance = None
    
    def __init__(self):
        if MongoDB._instance is not None:
            raise Exception("This class is a singleton!")
        else:
            # For MongoDB Atlas with SRV connection string
            self.client = MongoClient(
                Config.MONGO_URI,
                server_api=ServerApi('1'),
                retryWrites=True,
                w='majority'
            )
            
            # Test the connection
            try:
                self.client.admin.command('ping')
                print("✅ Successfully connected to MongoDB Atlas!")
            except Exception as e:
                print(f"❌ Connection failed: {e}")
                raise
            
            self.db = self.client.career_counseling
            MongoDB._instance = self
    
    @staticmethod
    def get_instance():
        if MongoDB._instance is None:
            MongoDB()
        return MongoDB._instance
    
    def get_database(self):
        return self.db
    
    def get_users_collection(self):
        return self.db.users
    
    def get_jobs_collection(self):
        return self.db.jobs
    
    # In mongodb.py, update init_database method:

    def init_database(self, jobs_data=None):
        """Initialize database with sample data and vector indexes"""
        try:
            # Create indexes for better query performance
            self.db.users.create_index("user_id", unique=True)
            self.db.users.create_index("email", unique=True)
            
            self.db.jobs.create_index("job_id", unique=True)
            self.db.jobs.create_index("riasec_code")
            self.db.jobs.create_index("primary_interest_cluster")
            
            # Create vector field indexes
            self.db.jobs.create_index("interests_vector")
            self.db.jobs.create_index("riasec_vector")
            self.db.jobs.create_index("aptitude_vector")
            
            # Text index for fallback search
            self.db.jobs.create_index([("family_title", "text"), 
                                    ("nco_title", "text"), 
                                    ("primary_skills", "text"),
                                    ("job_description", "text")])
            
            # Create indexes for aptitude scores
            for apt in Config.APTITUDE_CATEGORIES:
                self.db.jobs.create_index(f"aptitude_scores.{apt}")
            
            logger.info("✅ Database initialized with vector indexes")
            
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise
# Global instance
mongo_db = MongoDB.get_instance()