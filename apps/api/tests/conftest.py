import pytest
from sqlalchemy.orm import Session

from apps.api.config.database import engine, get_db
from apps.api.main import app


@pytest.fixture()
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture()
def override_get_db(db_session):
    """Points Depends(get_db) at this test's db_session for the duration
    of the test, so data set up via the ORM directly is visible to
    requests made through TestClient — they'd otherwise be on two
    separate connections, and db_session's isolation (a transaction that
    rolls back at teardown) means the endpoint's own connection would
    never see it."""
    app.dependency_overrides[get_db] = lambda: db_session
    yield
    app.dependency_overrides.pop(get_db, None)
