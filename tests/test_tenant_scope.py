"""Metrics must only attach to farms owned by the caller's organization."""

import uuid
from http import HTTPStatus

import pytest
import pytest_asyncio
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core_auth import CorePrincipal, get_core_principal
from app.db import Base, get_db
from app.main import app

engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    poolclass=StaticPool,
    connect_args={"check_same_thread": False},
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

ORG_A = uuid.uuid4()
ORG_B = uuid.uuid4()


async def override_get_db():
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def override_principal(request: Request) -> CorePrincipal:
    org_id = uuid.UUID(request.headers.get("X-Test-Org", str(ORG_A)))
    return CorePrincipal(
        user_id=uuid.uuid4(),
        email=None,
        org_id=org_id,
        role="owner",
        raw={},
    )


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_core_principal] = override_principal
    yield
    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _create_farm(client: AsyncClient, org_id: uuid.UUID) -> str:
    response = await client.post(
        "/farms",
        json={"name": "North Field", "region": "Punjab"},
        headers={"X-Test-Org": str(org_id)},
    )
    assert response.status_code == HTTPStatus.CREATED
    return response.json()["id"]


@pytest.mark.asyncio
async def test_metric_accepts_own_farm(client: AsyncClient):
    farm_id = await _create_farm(client, ORG_A)

    response = await client.post(
        "/metrics",
        json={"farm_id": farm_id, "name": "soil_ph", "value": 6.8},
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["organization_id"] == str(ORG_A)


@pytest.mark.asyncio
async def test_metric_rejects_other_org_farm(client: AsyncClient):
    farm_id = await _create_farm(client, ORG_B)

    response = await client.post(
        "/metrics",
        json={"farm_id": farm_id, "name": "soil_ph", "value": 6.8},
        headers={"X-Test-Org": str(ORG_A)},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
