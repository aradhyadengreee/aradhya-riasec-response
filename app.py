from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import uuid
from datetime import datetime
import os
from config import Config
from database.mongodb import mongo_db
from models.user import User
from routes.riasec import riasec_bp
from routes.recommendations import recommendations_bp
from routes.user import user_bp

def create_app():
    app = Flask(__name__,
                template_folder="../frontend/templates",
    static_folder="../frontend/static")
    app.config.from_object(Config)

    # Register blueprints
    app.register_blueprint(riasec_bp, url_prefix='/api/riasec')
    app.register_blueprint(recommendations_bp, url_prefix='/api/recommendations')
    app.register_blueprint(user_bp, url_prefix='/api/user')

    return app

app = create_app()

app.secret_key = Config.SECRET_KEY

# Main Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/user-info')
def user_info():
    return render_template('user_info.html', interest_clusters=Config.INTEREST_CLUSTERS)

@app.route('/interests')
def interests():
    if 'user_id' not in session:
        return redirect(url_for('user_info'))
    return render_template('interests.html', interest_clusters=Config.INTEREST_CLUSTERS)

@app.route('/assessment')
def assessment():
    if 'user_id' not in session:
        return redirect(url_for('user_info'))
    return render_template('assessment.html')

@app.route('/results')
def results():
    if 'user_id' not in session:
        return redirect(url_for('user_info'))
    return render_template('results.html')

@app.route('/download-results')
def download_results():
    # Placeholder for download functionality
    return redirect(url_for('results'))

if __name__ == '__main__':
    # Initialize database
    try:
        mongo_db.init_database()
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=app.config['DEBUG'], host='0.0.0.0', port=port)