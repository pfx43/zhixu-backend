import requests, json, time

email = f'kb{int(time.time())}@test.com'

# 1. Register
r = requests.post('http://127.0.0.1:8765/api/v1/auth/register',
    json={'email': email, 'password': 'Test123456', 'nickname': 'KB'})
token = r.json()['access_token']
print('1. Register OK')

# 2. Chat (test with knowledge retrieval)
r = requests.post('http://127.0.0.1:8765/api/v1/chat',
    json={'content': '你好，介绍一下你自己'},
    headers={'Authorization': f'Bearer {token}'},
    stream=True, timeout=60)
print('2. Chat status:', r.status_code)

full = ''
for line in r.iter_lines():
    if line:
        decoded = line.decode('utf-8')
        if decoded.startswith('data: '):
            data = json.loads(decoded[6:])
            c = data.get('content', '')
            if c:
                full += c
                print(c, end='', flush=True)

print('\n\n3. Done! Response length:', len(full))
print('4. SERVER NOT CRASHED - SUCCESS!')
