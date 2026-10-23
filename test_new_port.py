import requests
import re

s = requests.Session()

r1 = s.get('http://127.0.0.1:5001/auth/login')
csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', r1.text)
csrf_token = csrf_match.group(1) if csrf_match else ''

r2 = s.post('http://127.0.0.1:5001/auth/login', data={'username': 'test_student', 'password': '123456', 'role': 'student', 'csrf_token': csrf_token})
print(f'Login status: {r2.status_code}')

print('\n--- Testing test_fix ---')
r3 = s.get('http://127.0.0.1:5001/api/student/test_fix')
print(f'Status: {r3.status_code}')
print(f'Response: {r3.text}')

print('\n--- Testing forgetting_trend ---')
r4 = s.get('http://127.0.0.1:5001/api/student/forgetting_trend')
print(f'Status: {r4.status_code}')
print(f'Response (first 500 chars): {r4.text[:500]}')
