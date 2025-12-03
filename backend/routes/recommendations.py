# backend/routes/recommendations.py (UPDATED VERSION)
from flask import Blueprint, request, jsonify, session
from models.user import User
from services.recommendation_service import HierarchicalRecommendationService

recommendations_bp = Blueprint('recommendations', __name__)
recommendation_service = HierarchicalRecommendationService()

@recommendations_bp.route('/generate', methods=['POST'])
def generate_recommendations():
    """
    Generate hierarchical recommendations with:
    1. Strict RIASEC-first filtering
    2. Per-interest-cluster matching
    3. Vector-based similarity for all other components
    """
    try:
        if 'user_id' not in session:
            return jsonify({"error": "User not logged in"}), 401
        
        # Get user data
        user = User.get_user(session['user_id'])
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        if not user.riasec_code:
            return jsonify({"error": "Please complete RIASEC test first"}), 400
        
        # Get optional parameters
        data = request.get_json(silent=True) or {}
        min_score = data.get('min_score', 20)
        
        # Generate hierarchical recommendations
        recommendations_data = recommendation_service.generate_recommendations(user, min_score)
        
        return jsonify(recommendations_data)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "Failed to generate hierarchical recommendations"
        }), 500


