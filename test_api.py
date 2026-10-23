import requests
import re

s = requests.Session()

r1 = s.get('http://127.0.0.1:8888/auth/login')
csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', r1.text)
csrf_token = csrf_match.group(1) if csrf_match else ''
print(f'CSRF Token: {csrf_token}')

r2 = s.post('http://127.0.0.1:8888/auth/login', data={'username': 'test_student', 'password': '123456', 'role': 'student', 'csrf_token': csrf_token})
print(f'Login status: {r2.status_code}')

r3 = s.get('http://127.0.0.1:8888/api/forgetting_trend')
print(f'Forgetting trend status: {r3.status_code}')
print(f'Forgetting trend response: {r3.text}')

r4 = s.get('http://127.0.0.1:8888/api/dashboard_stats')
print(f'\nDashboard stats status: {r4.status_code}')
print(f'Dashboard stats response: {r4.text}')

r5 = s.get('http://127.0.0.1:8888/api/chapter_radar')
print(f'\nChapter radar status: {r5.status_code}')
print(f'Chapter radar response: {r5.text}')

r6 = s.get('http://127.0.0.1:8888/api/weak_points')
print(f'\nWeak points status: {r6.status_code}')
print(f'Weak points response: {r6.text[:1000]}')
