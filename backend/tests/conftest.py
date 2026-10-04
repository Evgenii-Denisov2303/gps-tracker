import os
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Admin
from app.security import hasher


@pytest.fixture
def client():
    # TEST_DATABASE_URL must be a dedicated disposable database: tables are dropped.
    url = os.environ.get("TEST_DATABASE_URL", "sqlite://")
    kwargs = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool} if url == "sqlite://" else {}
    engine = create_engine(url, **kwargs)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        db.add(Admin(username="owner", password_hash=hasher.hash("test-password-123")))
        db.add(Admin(username="friend", password_hash=hasher.hash("viewer-password-123"), read_only=True))
        db.commit()
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app, headers={"Origin": "http://localhost:8000"}) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def owner(client):
    response = client.post("/api/v1/auth/login", json={"username": "owner", "password": "test-password-123"})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


@pytest.fixture
def tracker(owner):
    vehicle = owner.post("/api/v1/vehicles", json={"name": "Газель №1"}).json()["id"]
    device = owner.post(f"/api/v1/vehicles/{vehicle}/devices", json={"name": "Android"}).json()
    return owner, vehicle, device
