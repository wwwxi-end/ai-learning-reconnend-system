import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app()
app.config['TESTING'] = True

client = app.test_client()

with app.app_context():
    from models.user import User
    from flask_login import login_user
    
    with client.session_transaction() as sess:
        sess['_user_id'] = '2'
        sess['_fresh'] = True
    
    resp = client.get('/api/forgetting_trend')
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.data[:500]}")
