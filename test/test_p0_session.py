# -*- coding: utf-8 -*-
"""
P0 step 5 test -- Redis session persistence

Usage:
  1. Start API: uvicorn server:app --host 127.0.0.1 --port 8765
  2. Run this:  py test_p0_session.py
"""
import urllib.request
import urllib.error
import json
import sys

BASE = "http://127.0.0.1:8765/api/v1/auth"


def req(method, path, data=None, headers=None, content_type=None):
    url = BASE + path
    h = dict(headers) if headers else {}
    if content_type:
        h["Content-Type"] = content_type
    body_bytes = None
    if data is not None:
        if content_type == "application/json":
            body_bytes = json.dumps(data).encode("utf-8")
        else:
            from urllib.parse import urlencode
            body_bytes = urlencode(data).encode("utf-8")
    r = urllib.request.Request(url, method=method, headers=h, data=body_bytes)
    try:
        resp = urllib.request.urlopen(r, timeout=10)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"detail": body}


def check_health():
    try:
        req("GET", "/token", None)
        return True
    except Exception as e:
        sys.exit("ERROR: API is not running!\n"
                 "Start it with: uvicorn server:app --host 127.0.0.1 --port 8765\n"
                 "Error: " + str(e))


def main():
    check_health()
    print("=" * 60)
    print("P0 Check 3: Redis session persistence")
    print("=" * 60)

    import time

    # 1. Register
    username = f"p0test_{int(time.time())}"
    print(f"\n[1] Register: {username}")
    code, body = req("POST", "/register",
        data={"username": username, "password": "Test123456",
              "email": f"{username}@test.com"},
        content_type="application/json")
    print(f"    Status: {code}")
    if code not in (200, 201):
        print(f"    Response: {json.dumps(body, ensure_ascii=False, indent=2)}")
        sys.exit("Register FAILED")

    # 2. Login (must use email because /token checks for @)
    email = f"{username}@test.com"
    print(f"\n[2] Login to get token (email: {email})")
    code, body = req("POST", "/token",
        data={"username": email, "password": "Test123456"})
    print(f"    Status: {code}")
    token = body.get("access_token", "")
    if not token:
        print(f"    Response: {json.dumps(body, ensure_ascii=False, indent=2)}")
        sys.exit("Login FAILED")
    print(f"    Token: {token[:30]}...")

    # 3. Verify token
    print(f"\n[3] Call /users/me with token")
    code, body = req("GET", "/users/me",
        headers={"Authorization": f"Bearer {token}"})
    print(f"    Status: {code}")
    username_back = body.get("username", "?")
    print(f"    Username: {username_back}")
    if code != 200 or username_back != username:
        sys.exit("Token verification FAILED!")

    print(f"\n{'=' * 60}")
    print(f">>> Now restart the API:")
    print(f"    1. Ctrl+C in the API terminal")
    print(f"    2. uvicorn server:app --host 127.0.0.1 --port 8765")
    print(f"    3. Wait for 'Application startup complete'")
    print(f"    4. Press Enter here to continue...")
    print(f"{'=' * 60}")
    input("\n    >>> Press Enter to continue...")

    # 4. Verify old token after restart
    print(f"\n[4] After restart: /users/me with old token")
    code, body = req("GET", "/users/me",
        headers={"Authorization": f"Bearer {token}"})
    print(f"    Status: {code}")
    if code == 200:
        username_back = body.get("username", "?")
        print(f"    Username: {username_back}")
        if username_back == username:
            print(f"\n{'=' * 60}")
            print(f"*** P0 Check 3 PASS! ***")
            print(f"    Session stored in Redis, token survived restart")
            print(f"{'=' * 60}")
        else:
            sys.exit("Username mismatch?")
    elif code == 401:
        print(f"\n{'=' * 60}")
        print(f"*** P0 Check 3 FAIL! ***")
        print(f"    Token invalid after restart, session NOT in Redis")
        print(f"    Check if CACHE_BACKEND=redis")
        print(f"{'=' * 60}")

    print(f"\n--- Check 4: Memory mode comparison ---")
    print(f"    1. Set CACHE_BACKEND=memory in .env")
    print(f"    2. Restart API")
    print(f"    3. Re-run this script")
    print(f"    4. Expect token to fail after restart")


if __name__ == "__main__":
    main()