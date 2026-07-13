"""GearTwin AI — Fahrzeug-Digital-Twin & prädiktives Warnsystem (Prototyp).

In-Memory-Prototyp ohne echte Datenbank/Vektorsuche. Der Retrieval-Schritt aus
03-architecture-rag.md ist als `find_matching_issues` austauschbar gehalten:
in Produktion ersetzt eine SQL-Filterung + pgvector-Suche gegen
`knowledge_base_issues` diese Funktion.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="GearTwin AI — Vehicle API", version="0.1.0")


class Severity(str, Enum):
    info = "info"
    advisory = "advisory"
    warning = "warning"
    critical = "critical"


class KnowledgeBaseIssue(BaseModel):
    id: str
    make: str
    model: str
    issue_title: str
    issue_description: str
    typical_mileage_from: int
    typical_mileage_to: int
    severity: Severity
    avg_cost_workshop_eur: float
    avg_cost_diy_eur: float
    source_url: str
    confidence_score: float


# Stub-Wissensbasis, wie sie in Produktion aus der RAG-Ingestion-Pipeline befuellt wuerde.
KNOWLEDGE_BASE: list[KnowledgeBaseIssue] = [
    KnowledgeBaseIssue(
        id=str(uuid.uuid4()),
        make="Volkswagen",
        model="Polo IV",
        issue_title="Lenkschloss hakt / blockiert",
        issue_description=(
            "Bei diesem Modell berichten mehrere Foren-Threads von einem "
            "hakenden oder blockierenden elektronischen Lenkschloss."
        ),
        typical_mileage_from=120_000,
        typical_mileage_to=170_000,
        severity=Severity.warning,
        avg_cost_workshop_eur=250.0,
        avg_cost_diy_eur=60.0,
        source_url="https://www.motor-talk.de/forum/polo-9n-lenkschloss",
        confidence_score=0.82,
    ),
    KnowledgeBaseIssue(
        id=str(uuid.uuid4()),
        make="Volkswagen",
        model="Polo IV",
        issue_title="Verschlissene Querlenkerbuchsen",
        issue_description="Poltern/Knarzen im Fahrwerk, typisch ab ca. 130.000 km.",
        typical_mileage_from=130_000,
        typical_mileage_to=180_000,
        severity=Severity.advisory,
        avg_cost_workshop_eur=180.0,
        avg_cost_diy_eur=45.0,
        source_url="https://www.motor-talk.de/forum/polo-9n-querlenker",
        confidence_score=0.75,
    ),
]


class VehicleCreate(BaseModel):
    make: str
    model: str
    engine_code: str | None = None
    fuel_type: str | None = None
    first_registration_date: date | None = None
    current_mileage: int = Field(ge=0)


class Vehicle(VehicleCreate):
    id: str
    user_id: str
    created_at: datetime


VEHICLES: dict[str, Vehicle] = {}
DEMO_USER_ID = "demo-user"


def find_matching_issues(make: str, model: str, current_mileage: int) -> list[KnowledgeBaseIssue]:
    """Retrieval-Stub: strukturierter Pre-Filter wie in Schritt 4 der RAG-Architektur."""
    window = 15_000
    return [
        issue
        for issue in KNOWLEDGE_BASE
        if issue.make.lower() == make.lower()
        and issue.model.lower() == model.lower()
        and issue.typical_mileage_from - window <= current_mileage
        and current_mileage <= issue.typical_mileage_to + window
    ]


@app.post("/vehicles", response_model=Vehicle, status_code=201)
def create_vehicle(payload: VehicleCreate) -> Vehicle:
    vehicle = Vehicle(
        id=str(uuid.uuid4()),
        user_id=DEMO_USER_ID,
        created_at=datetime.utcnow(),
        **payload.model_dump(),
    )
    VEHICLES[vehicle.id] = vehicle
    return vehicle


@app.get("/vehicles/{vehicle_id}", response_model=Vehicle)
def get_vehicle(vehicle_id: str) -> Vehicle:
    vehicle = VEHICLES.get(vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Fahrzeug nicht gefunden")
    return vehicle


@app.get("/vehicles/{vehicle_id}/warnings", response_model=list[KnowledgeBaseIssue])
def get_vehicle_warnings(vehicle_id: str) -> list[KnowledgeBaseIssue]:
    vehicle = VEHICLES.get(vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Fahrzeug nicht gefunden")
    matches = find_matching_issues(vehicle.make, vehicle.model, vehicle.current_mileage)
    return sorted(matches, key=lambda i: i.confidence_score, reverse=True)
