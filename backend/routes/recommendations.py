from flask import Blueprint, request, jsonify, session
from models.user import User
from services.recommendation_service import RecommendationService

recommendations_bp = Blueprint('recommendations', __name__)
recommendation_service = RecommendationService()

@recommendations_bp.route('/generate', methods=['POST'])
def generate_recommendations():
    try:
        if 'user_id' not in session:
            return jsonify({"error": "User not logged in"}), 401
        
        # Get user data
        user = User.get_user(session['user_id'])
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        if not user.riasec_code:
            return jsonify({"error": "Please complete RIASEC test first"}), 400
        
        # Generate recommendations
        recommendations = recommendation_service.generate_recommendations(user)
        
        return jsonify({
            "success": True,
            "user_info": {
                "name": user.name,
                "education_level": user.education_level,
                "experience_years": user.experience_years,
                "current_field": user.current_field,
                "interests": user.interests
            },
            "riasec_code": user.riasec_code,
            "recommendations": recommendations
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@recommendations_bp.route('/filter-by-percentage', methods=['POST'])
def filter_recommendations_by_percentage():
    try:
        if 'user_id' not in session:
            return jsonify({"error": "User not logged in"}), 401
        
        # Get minimum percentage from request
        data = request.get_json()
        min_percentage = data.get('min_percentage', 70)
        
        if not isinstance(min_percentage, (int, float)) or min_percentage < 0 or min_percentage > 100:
            return jsonify({"error": "Invalid minimum percentage"}), 400
        
        # Get user data
        user = User.get_user(session['user_id'])
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        if not user.riasec_code:
            return jsonify({"error": "Please complete RIASEC test first"}), 400
        
        # Generate recommendations with minimum percentage
        # You'll need to modify the RecommendationService to accept min_percentage parameter
        recommendations = recommendation_service.generate_recommendations(user, min_percentage)
        
        return jsonify({
            "success": True,
            "user_info": {
                "name": user.name,
                "education_level": user.education_level,
                "experience_years": user.experience_years,
                "current_field": user.current_field,
                "interests": user.interests
            },
            "riasec_code": user.riasec_code,
            "min_percentage": min_percentage,
            "total_matches": len(recommendations),
            "recommendations": recommendations
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    
@recommendations_bp.route('/user/<user_id>')
def get_recommendations_by_user_id(user_id):
    """Endpoint for other services to get recommendations by user_id"""
    try:
        user = User.get_user(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        if not user.riasec_code:
            return jsonify({"error": "User has not completed RIASEC test"}), 400
        
        # Generate recommendations
        recommendations = recommendation_service.generate_recommendations(user)
        
        return jsonify({
            "success": True,
            "user_id": user_id,
            "riasec_code": user.riasec_code,
            "recommendations": recommendations
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400