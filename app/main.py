from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .core_auth import CorePrincipal, get_core_principal
from .db import Farm, Metric, get_db, init_db

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Agriculture data analytics — Core JWT + self-hosted Postgres",
    version=settings.VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    await init_db()


@app.get("/health")
def health_check():
    return {"status": "healthy", "version": settings.VERSION}


@app.get("/")
def read_root():
    return {"message": "krishora-insight", "auth": "core", "db": "self-hosted-postgres"}


class FarmIn(BaseModel):
    name: str
    region: str | None = None


@app.get("/farms")
async def list_farms(
    principal: CorePrincipal = Depends(get_core_principal),
    db: AsyncSession = Depends(get_db),
):
    return (
        await db.execute(
            select(Farm).where(Farm.organization_id == principal.org_id)
        )
    ).scalars().all()


@app.post("/farms", status_code=201)
async def create_farm(
    body: FarmIn,
    principal: CorePrincipal = Depends(get_core_principal),
    db: AsyncSession = Depends(get_db),
):
    row = Farm(
        organization_id=principal.org_id,
        owner_user_id=principal.user_id,
        **body.model_dump(),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


class MetricIn(BaseModel):
    farm_id: str
    name: str
    value: float
    unit: str | None = None


@app.post("/metrics", status_code=201)
async def create_metric(
    body: MetricIn,
    principal: CorePrincipal = Depends(get_core_principal),
    db: AsyncSession = Depends(get_db),
):
    import uuid

    row = Metric(
        organization_id=principal.org_id,
        farm_id=uuid.UUID(body.farm_id),
        name=body.name,
        value=body.value,
        unit=body.unit,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row
