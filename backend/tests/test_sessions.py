from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import settings
from app.db import get_db, utcnow
from app.main import app
from app.models import AdminSession


@pytest.mark.parametrize("remember,seconds", [(False, 12 * 3600), (True, 30 * 86400)])
def test_session_lifetime_and_revocation(client, remember, seconds):
    response = client.post('/api/v1/auth/login', json={
        'username': 'friend', 'password': 'viewer-password-123', 'remember_me': remember})
    assert response.status_code == 200
    cookie = response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie
    assert ('max-age=2592000' in cookie) if remember else ('max-age' not in cookie)
    with next(app.dependency_overrides[get_db]()) as db:
        session = db.scalar(select(AdminSession))
        expected = seconds if remember else settings().session_hours * 3600
        assert expected - 10 <= (session.expires_at - utcnow()).total_seconds() <= expected
    client.headers['X-CSRF-Token'] = response.json()['csrf_token']
    assert client.post('/api/v1/vehicles', json={'name': 'Forbidden'}).status_code == 403
    token = client.cookies.get('gps_session')
    assert client.post('/api/v1/auth/logout').status_code == 204
    client.cookies.set('gps_session', token)
    assert client.get('/api/v1/auth/me').status_code == 401


def test_remembered_session_expires_on_server(client):
    client.post('/api/v1/auth/login', json={
        'username': 'owner', 'password': 'test-password-123', 'remember_me': True})
    with next(app.dependency_overrides[get_db]()) as db:
        db.scalar(select(AdminSession)).expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.get('/api/v1/vehicles').status_code == 401
