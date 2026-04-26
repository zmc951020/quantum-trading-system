import requests
import json

# 测试登录API
def test_login():
    url = 'http://localhost:5000/api/auth/login'
    headers = {'Content-Type': 'application/json'}
    data = {
        'username': 'admin',
        'password': 'admin123'
    }
    
    response = requests.post(url, headers=headers, json=data)
    print(f"Status code: {response.status_code}")
    print(f"Response: {response.json()}")

# 测试会话验证API
def test_validate(session_id):
    url = 'http://localhost:5000/api/auth/validate'
    headers = {'X-Session-ID': session_id}
    
    response = requests.get(url, headers=headers)
    print(f"Validate status code: {response.status_code}")
    print(f"Validate response: {response.json()}")

if __name__ == '__main__':
    print("Testing login API...")
    test_login()
