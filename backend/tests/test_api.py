import httpx

from app.main import create_app
from app.settings import Settings


async def test_health_auth_body_limit_and_removed_chat():
    app = create_app(Settings(local_token='t'))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.get('/api/v1/health')).status_code == 401
        client.headers['Authorization'] = 'Bearer t'
        assert (await client.get('/api/v1/health')).json() == {'status': 'ok', 'model_configured': False}
        assert (await client.post('/api/v1/chat', json={})).status_code == 404
        assert (await client.post('/api/v1/sessions', content=b'x' * (1024 * 1024 + 1))).status_code == 413
        assert (await client.post('/api/v1/sessions', content='{')).status_code == 422
