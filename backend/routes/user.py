from flask import Blueprint, request, jsonify, session
import uuid
from models.user import User

user_bp = Blueprint('user', __name__)

@user_bp.route('/create', methods=['POST'])
def create_user():
    try:
        user_data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'email', 'education_level', 'current_field']
        for field in required_fields:
            if field not in user_data or not user_data[field]:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Generate unique user ID
        user_data['user_id'] = str(uuid.uuid4())
        
        # Create user in database
        user = User.create_user(user_data)
        
        # Store user ID in session
        session['user_id'] = user.user_id
        
        return jsonify({
            "success": True,
            "user_id": user.user_id,
            "message": "User created successfully"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@user_bp.route('/update-interests', methods=['POST'])
def update_interests():
    try:
        if 'user_id' not in session:
            return jsonify({"error": "User not logged in"}), 401
        
        data = request.get_json()
        interests = data.get('interests', [])
        
        # Validate interests
        if len(interests) < 3:
            return jsonify({"error": "Please select at least 3 interests"}), 400
        
        if len(interests) > 5:
            return jsonify({"error": "Please select at most 5 interests"}), 400
        
        # Get user and update interests
        user = User.get_user(session['user_id'])
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        user.update_interests(interests)
        
        return jsonify({
            "success": True,
            "message": "Interests updated successfully",
            "interests": interests
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@user_bp.route('/profile')
def get_profile():
    try:
        if 'user_id' not in session:
            return jsonify({"error": "User not logged in"}), 401
        
        user = User.get_user(session['user_id'])
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        return jsonify({
            "success": True,
            "user": user.to_dict()
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400