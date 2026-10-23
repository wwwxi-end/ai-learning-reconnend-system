import requests
import re

s = requests.Session()
s.headers.update({'Accept': 'application/json'})

r1 = s.get('http://127.0.0.1:5000/auth/login')
csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', r1.text)
csrf_token = csrf_match.group(1) if csrf_match else ''
print(f'CSRF Token: {csrf_token}')

r2 = s.post('http://127.0.0.1:5000/auth/login', data={'username': 'test_student', 'password': '123456', 'role': 'student', 'csrf_token': csrf_token})
print(f'Login status: {r2.status_code}')

print('\n--- Testing forgetting_trend ---')
r3 = s.get('http://127.0.0.1:5000/api/student/forgetting_trend')
print(f'URL: {r3.url}')
print(f'Status: {r3.status_code}')
print(f'Response text (first 500 chars): {r3.text[:500]}')
