import requests 

BASE="http://localhost:8088"

login=requests.post(

    f"{BASE}/api/v1/security/login", json={
        "username": "admin",
        "password": "Pass123",
        "provider":"db",
        "refresh":True,
    }
)

login.raise_for_status()
access_token=login.json()["access_token"]
print("access_token:", access_token)

response=requests.get(
    f"{BASE}/api/v1/semantic_layer/",
    headers={"Authorization": f"Bearer {access_token}"}
)

print(response.status_code)
print("response:", response.json())