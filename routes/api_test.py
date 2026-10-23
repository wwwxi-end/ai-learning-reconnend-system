from flask import Blueprint, jsonify
from flask_login import login_required, current_user

api_test_bp = Blueprint('api_test', __name__)


@api_test_bp.route('/test_forgetting')
@login_required
def test_forgetting():
    return jsonify({'message': 'Hello from test', 'user_id': current_user.id})
