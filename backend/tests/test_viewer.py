from test_api import point, send


def viewer_login(c):
    c.post('/api/v1/auth/logout')
    result = c.post('/api/v1/auth/login', json={'username': 'friend', 'password': 'viewer-password-123'})
    assert result.status_code == 200
    assert result.json()['role'] == 'viewer'
    c.headers['X-CSRF-Token'] = result.json()['csrf_token']


def test_viewer_reads_real_vehicle_data(tracker):
    c, vehicle, device = tracker
    p = point()
    assert send(c, device, [p]).status_code == 200
    viewer_login(c)
    assert c.get('/api/v1/auth/me').json()['role'] == 'viewer'
    assert c.get('/api/v1/vehicles').json()[0]['id'] == vehicle
    assert c.get(f'/api/v1/vehicles/{vehicle}/latest').json()['point']['latitude'] == p['latitude']
    day = p['gps_timestamp'][:10]
    for endpoint in ('route', 'stops'):
        assert c.get(f'/api/v1/vehicles/{vehicle}/{endpoint}?date={day}').status_code == 200
    assert c.post('/api/v1/auth/logout').status_code == 204
    assert c.get('/api/v1/vehicles').status_code == 401


def test_viewer_cannot_manage_even_with_valid_csrf(tracker):
    c, vehicle, device = tracker
    viewer_login(c)
    assert c.post('/api/v1/vehicles', json={'name': 'Forbidden'}).status_code == 403
    assert c.get(f'/api/v1/vehicles/{vehicle}/devices').status_code == 403
    assert c.post(f'/api/v1/vehicles/{vehicle}/devices', json={'name': 'Forbidden'}).status_code == 403
    assert c.delete(f'/api/v1/devices/{device["id"]}').status_code == 403
    assert c.post('/api/v1/locations', json={'points': [point()]}).status_code == 401
    assert send(c, device, [point()]).status_code == 200  # Token was not revoked.
    assert len(c.get('/api/v1/vehicles').json()) == 1


def test_role_cannot_be_claimed_by_login_body(client):
    assert client.post('/api/v1/auth/login', json={
        'username': 'friend', 'password': 'viewer-password-123', 'role': 'owner'
    }).status_code == 422


def test_owner_retains_management(tracker):
    c, vehicle, device = tracker
    assert c.get('/api/v1/auth/me').json()['role'] == 'owner'
    assert c.get(f'/api/v1/vehicles/{vehicle}/devices').status_code == 200
    assert c.delete(f'/api/v1/devices/{device["id"]}').status_code == 204
