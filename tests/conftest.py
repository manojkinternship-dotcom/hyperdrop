import pytest
from unittest.mock import patch
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_session
import app.database as app_db
import app.core.orchestrator as orch_module
import app.providers.payment as payment_module

# In-memory test engine with StaticPool so all threads/sessions share the same DB
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    SQLModel.metadata.create_all(test_engine)
    app_db.engine = test_engine
    orch_module.engine = test_engine
    payment_module.engine = test_engine
    yield
    SQLModel.metadata.drop_all(test_engine)

@pytest.fixture
def session():
    SQLModel.metadata.drop_all(test_engine)
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        yield session

@pytest.fixture
def client(session):
    def get_session_override():
        return session
    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
