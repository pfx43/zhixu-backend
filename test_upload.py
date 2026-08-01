import requests

# login to get token
r = requests.post('http://127.0.0.1:8765/api/v1/auth/token', 
    data={'username': 'ds@test.com', 'password': 'Test123456'})
print('Login:', r.status_code)
data = r.json()
token = data.get('access_token', '')
print('Token:', token[:20] if token else 'NONE')

if not token:
    # register
    r = requests.post('http://127.0.0.1:8765/api/v1/auth/register',
        json={'email': 'ds@test.com', 'password': 'Test123456', 'nickname': 'DS'})
    token = r.json().get('access_token', '')
    print('Registered, token:', token[:20])

# test upload
files = {'file': ('test.txt', b'hello world', 'text/plain')}
r = requests.post('http://127.0.0.1:8765/api/v1/kb/upload',
    headers={'Authorization': f'Bearer {token}'},
    files=files)
print('Upload status:', r.status_code)
print('Upload body:', r.text[:500])
