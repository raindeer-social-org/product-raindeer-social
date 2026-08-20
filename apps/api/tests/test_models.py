import pytest
from sqlalchemy.exc import IntegrityError

from apps.api.models import Brand, Organization, User, UserRole


def test_create_organization_user_brand(db_session) -> None:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    user = User(
        organization_id=org.id,
        email="owner@acme.test",
        password_hash="not-a-real-hash",
        role=UserRole.OWNER,
    )
    brand = Brand(organization_id=org.id, name="Acme Widgets")
    db_session.add_all([user, brand])
    db_session.flush()

    db_session.refresh(org)
    assert user in org.users
    assert brand in org.brands
    assert user.organization is org
    assert brand.organization is org


def test_user_role_defaults_to_viewer(db_session) -> None:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    user = User(
        organization_id=org.id, email="viewer@acme.test", password_hash="not-a-real-hash"
    )
    db_session.add(user)
    db_session.flush()

    assert user.role == UserRole.VIEWER


def test_user_email_must_be_unique(db_session) -> None:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    db_session.add(
        User(organization_id=org.id, email="dup@acme.test", password_hash="hash-1")
    )
    db_session.flush()

    db_session.add(
        User(organization_id=org.id, email="dup@acme.test", password_hash="hash-2")
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_brand_report_and_embedding_round_trip(db_session) -> None:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    embedding = [0.1] * 1536
    brand = Brand(
        organization_id=org.id,
        name="Acme Widgets",
        brand_report={"voice": "playful", "audience": "gen-z"},
        report_embedding=embedding,
    )
    db_session.add(brand)
    db_session.flush()
    db_session.refresh(brand)

    assert brand.brand_report == {"voice": "playful", "audience": "gen-z"}
    assert len(brand.report_embedding) == 1536
