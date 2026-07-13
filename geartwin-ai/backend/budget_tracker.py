"""GearTwin AI — Prädiktiver Budget-Tracker (Prototyp).

Liest einen CSV-Kontoauszug ein, kategorisiert Auto-Ausgaben per Regex und
kombiniert sie mit einer modellspezifischen Wissensbasis, um ein
Rücklagen-Budget für die kommenden Monate zu berechnen (siehe
04-budget-and-parts-modules.md, Abschnitt "Algorithmus Rücklagen-Vorschau").
"""
from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

app = FastAPI(title="GearTwin AI — Budget Tracker", version="0.1.0")

HORIZON_MONTHS = 6

CATEGORY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("fuel", re.compile(r"\b(ARAL|SHELL|ESSO|TOTAL|JET|STAR TANKSTELLE|OMV|AVIA)\b", re.I)),
    ("insurance", re.compile(r"\b(VERSICHERUNG|ALLIANZ|HUK[- ]?COBURG|AXA|ERGO|DEVK)\b", re.I)),
    ("tax", re.compile(r"\b(HAUPTZOLLAMT|KFZ[- ]?STEUER|KRAFTFAHRZEUGSTEUER)\b", re.I)),
    (
        "maintenance",
        re.compile(r"\b(WERKSTATT|ATU|PIT[- ]?STOP|BOSCH CAR SERVICE|AUTOHAUS|T[UÜ]V|TUEV|DEKRA|REIFEN)\b", re.I),
    ),
    ("parts", re.compile(r"\b(AUTODOC|KFZTEILE24|EBAY MOTORS|EBAY.*KFZ)\b", re.I)),
]

CATEGORIES = ["fuel", "insurance", "tax", "maintenance", "parts", "other"]


def categorize_transaction(description: str) -> str:
    for category, pattern in CATEGORY_PATTERNS:
        if pattern.search(description):
            return category
    return "other"


@dataclass
class Transaction:
    transaction_date: date
    description: str
    amount_eur: float
    category: str = field(init=False)

    def __post_init__(self) -> None:
        self.category = categorize_transaction(self.description)


def parse_transactions_csv(raw: bytes) -> list[Transaction]:
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    required = {"date", "description", "amount"}
    if reader.fieldnames is None or not required.issubset({f.lower() for f in reader.fieldnames}):
        raise HTTPException(
            status_code=400,
            detail=f"CSV muss die Spalten {sorted(required)} enthalten, gefunden: {reader.fieldnames}",
        )
    transactions: list[Transaction] = []
    for row in reader:
        row = {k.lower(): v for k, v in row.items()}
        transactions.append(
            Transaction(
                transaction_date=date.fromisoformat(row["date"]),
                description=row["description"],
                amount_eur=abs(float(row["amount"].replace(",", "."))),
            )
        )
    return transactions


class ModelIssue(BaseModel):
    issue_title: str
    typical_mileage_from: int
    avg_cost_workshop_eur: float
    avg_cost_diy_eur: float


# Modell-Wissensbasis (Prototyp-Stub fuer die knowledge_base_issues-Tabelle).
MODEL_KNOWLEDGE_BASE: dict[tuple[str, str], list[ModelIssue]] = {
    ("vw", "polo iv"): [
        ModelIssue(
            issue_title="Lenkschloss hakt / blockiert",
            typical_mileage_from=150_000,
            avg_cost_workshop_eur=250.0,
            avg_cost_diy_eur=60.0,
        ),
        ModelIssue(
            issue_title="Verschlissene Querlenkerbuchsen",
            typical_mileage_from=130_000,
            avg_cost_workshop_eur=180.0,
            avg_cost_diy_eur=45.0,
        ),
    ],
    ("vw", "golf iv"): [
        ModelIssue(
            issue_title="Ausfall Fensterheber-Steuergeraet",
            typical_mileage_from=140_000,
            avg_cost_workshop_eur=220.0,
            avg_cost_diy_eur=50.0,
        ),
    ],
}


class BudgetForecast(BaseModel):
    issue_title: str
    months_until_due: float
    estimated_cost_workshop_eur: float
    estimated_cost_diy_eur: float
    recommended_monthly_reserve_eur: float


class CategorySummary(BaseModel):
    category: str
    total_eur: float
    transaction_count: int


class BudgetAnalysis(BaseModel):
    category_summary: list[CategorySummary]
    predictive_forecasts: list[BudgetForecast]


def build_category_summary(transactions: list[Transaction]) -> list[CategorySummary]:
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for t in transactions:
        totals[t.category] += t.amount_eur
        counts[t.category] += 1
    return [
        CategorySummary(category=c, total_eur=round(totals[c], 2), transaction_count=counts[c])
        for c in CATEGORIES
        if counts[c] > 0
    ]


def build_predictive_forecasts(
    make: str, model: str, mileage: int, monthly_mileage: float
) -> list[BudgetForecast]:
    issues = MODEL_KNOWLEDGE_BASE.get((make.strip().lower(), model.strip().lower()), [])
    forecasts: list[BudgetForecast] = []
    for issue in issues:
        km_remaining = issue.typical_mileage_from - mileage
        months_until_due = max(km_remaining, 0) / monthly_mileage if km_remaining > 0 else 0.0
        if months_until_due > HORIZON_MONTHS:
            continue
        reserve = issue.avg_cost_workshop_eur / max(months_until_due, 1.0)
        forecasts.append(
            BudgetForecast(
                issue_title=issue.issue_title,
                months_until_due=round(months_until_due, 1),
                estimated_cost_workshop_eur=issue.avg_cost_workshop_eur,
                estimated_cost_diy_eur=issue.avg_cost_diy_eur,
                recommended_monthly_reserve_eur=round(reserve, 2),
            )
        )
    return sorted(forecasts, key=lambda f: f.months_until_due)


@app.post("/budget/analyze", response_model=BudgetAnalysis)
async def analyze_budget(
    make: str,
    model: str,
    mileage: int,
    monthly_mileage: float = 1200.0,
    file: UploadFile = File(...),
) -> BudgetAnalysis:
    if monthly_mileage <= 0:
        raise HTTPException(status_code=400, detail="monthly_mileage muss > 0 sein")
    raw = await file.read()
    transactions = parse_transactions_csv(raw)
    return BudgetAnalysis(
        category_summary=build_category_summary(transactions),
        predictive_forecasts=build_predictive_forecasts(make, model, mileage, monthly_mileage),
    )
