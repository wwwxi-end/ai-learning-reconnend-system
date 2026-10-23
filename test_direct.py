import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import db
from models.user import User

app = create_app()

with app.app_context():
    from routes.api import forgetting_trend
    
    user = User.query.filter_by(username='test_student').first()
    print(f"User: {user.username}, id: {user.id}")
    
    from flask_login import current_user
    with app.test_request_context():
        with app.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
        
        result = forgetting_trend()
        print(f"Result: {result}")
