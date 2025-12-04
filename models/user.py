# models/user.py (update to store aptitude scores and ensure RIASEC scores are saved)
from datetime import datetime
from database.mongodb import mongo_db

class User:
    def __init__(self, user_data):
        self.user_id = user_data.get('user_id')
        self.name = user_data.get('name')
        self.email = user_data.get('email')
        self.education_level = user_data.get('education_level')
        self.experience_years = user_data.get('experience_years', 0)
        self.current_field = user_data.get('current_field')
        self.interests = user_data.get('interests', [])
        self.riasec_scores = user_data.get('riasec_scores', {})  # Ensure this is stored
        self.riasec_code = user_data.get('riasec_code', '')
        self.aptitude_percentiles = user_data.get('aptitude_percentiles', {})
        self.created_at = user_data.get('created_at', datetime.utcnow())
    
    def to_dict(self):
        return {
            'user_id': self.user_id,
            'name': self.name,
            'email': self.email,
            'education_level': self.education_level,
            'experience_years': self.experience_years,
            'current_field': self.current_field,
            'interests': self.interests,
            'riasec_scores': self.riasec_scores,  # Ensure this is included
            'riasec_code': self.riasec_code,
            'aptitude_percentiles': self.aptitude_percentiles,
            'created_at': self.created_at
        }
    
    @classmethod
    def create_user(cls, user_data):
        """Create new user in database"""
        users_collection = mongo_db.get_users_collection()
        
        user = cls(user_data)
        result = users_collection.insert_one(user.to_dict())
        
        return user
    
    @classmethod
    def get_user(cls, user_id):
        """Get user by user_id"""
        users_collection = mongo_db.get_users_collection()
        user_data = users_collection.find_one({"user_id": user_id})
        
        if user_data:
            return cls(user_data)
        return None
    
    def update_riasec_results(self, riasec_scores, riasec_code, answers=None, aptitude_percentiles=None):
        """Update RIASEC test results and optionally store question-answer mapping and aptitude scores"""
        users_collection = mongo_db.get_users_collection()

        self.riasec_scores = riasec_scores  # Ensure scores are stored
        self.riasec_code = riasec_code

        if aptitude_percentiles is not None:
            # Convert old aptitude format to new format if needed
            self.aptitude_percentiles = self._convert_aptitude_format(aptitude_percentiles)

        update_fields = {
            "riasec_scores": riasec_scores,  # Ensure scores are saved
            "riasec_code": riasec_code
        }
        if answers is not None:
            update_fields["answers"] = answers  # store question -> answer mapping
        if aptitude_percentiles is not None:
            update_fields["aptitude_percentiles"] = self._convert_aptitude_format(aptitude_percentiles)

        print(f"Updating user {self.user_id} with RIASEC:")
        print(f"  Code: {riasec_code}")
        print(f"  Scores: {riasec_scores}")
        print(f"  Aptitude: {aptitude_percentiles}")

        result = users_collection.update_one(
            {"user_id": self.user_id},
            {"$set": update_fields}
        )

        print(f"Update result: {result.modified_count} documents modified")
    
    def _convert_aptitude_format(self, old_aptitudes):
        """Convert from old aptitude format to new format if needed"""
        # If already in new format, return as is
        new_categories = [
            "Mechanical",
            "Spatial/Design", 
            "Logical Reasoning",
            "Organizing/Structuring",
            "Digital/Computer",
            "Scientific",
            "Numerical",
            "Creative",
            "Writing/Expression",
            "Social/Helping",
            "Verbal Communication",
            "Leadership/Persuasion"
        ]
        
        # Check if already in new format
        has_new_format = any(cat in old_aptitudes for cat in new_categories)
        
        if has_new_format:
            return old_aptitudes
        
        # Convert from old format to new format
        new_aptitudes = {}
        mapping = {
            'verbal': ['Verbal Communication', 'Writing/Expression'],
            'numerical': ['Numerical'],
            'abstract': ['Logical Reasoning'],
            'mechanical': ['Mechanical'],
            'spatial': ['Spatial/Design'],
            'clerical': ['Organizing/Structuring'],
            'logical': ['Logical Reasoning'],
            'technical': ['Digital/Computer'],
            'analytical': ['Logical Reasoning', 'Scientific'],
            'creative': ['Creative'],
            'interpersonal': ['Social/Helping', 'Leadership/Persuasion'],
            'organizational': ['Organizing/Structuring']
        }
        
        for old_cat, score in old_aptitudes.items():
            new_cats = mapping.get(old_cat.lower(), [])
            for new_cat in new_cats:
                if new_cat not in new_aptitudes:
                    new_aptitudes[new_cat] = score
                else:
                    new_aptitudes[new_cat] = max(new_aptitudes[new_cat], score)
        
        # Fill missing with default 50
        for cat in new_categories:
            if cat not in new_aptitudes:
                new_aptitudes[cat] = 50
        
        return new_aptitudes

    def update_interests(self, interests):
        """Update user interests"""
        users_collection = mongo_db.get_users_collection()
        
        self.interests = interests
        
        users_collection.update_one(
            {"user_id": self.user_id},
            {"$set": {"interests": interests}}
        )