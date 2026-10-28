from fastapi.testclient import TestClient

from helper_bot.main import app

with TestClient(app) as client:
    for path in ("/", "/health/live", "/health/ready", "/openapi.json"):
        response = client.get(path)
        assert response.status_code == 200, (path, response.status_code)
print("API и PostgreSQL доступны")
