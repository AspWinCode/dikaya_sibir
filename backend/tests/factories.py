"""Test factories using factory_boy + SQLAlchemy async."""

import uuid

import factory
from app.core.security import hash_password
from app.models.identity import Role, User
from factory.alchemy import SQLAlchemyModelFactory


class RoleFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Role
        sqlalchemy_session_persistence = "flush"

    id = factory.Sequence(lambda n: f"role_{n}")
    display_name = factory.LazyAttribute(lambda o: o.id.replace("_", " ").title())
    is_system = False


class UserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid.uuid4)
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    display_name = factory.Sequence(lambda n: f"Test User {n}")
    password_hash = factory.LazyFunction(lambda: hash_password("Test1234!"))
    is_active = True
    is_superuser = False
    totp_enabled = False
