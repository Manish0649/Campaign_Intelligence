
import os
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set testing environment before importing application modules.
os.environ["TESTING"] = "1"
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("JWT_SECRET", "test-only-secret-key-with-32-characters-minimum")

import backend.app.agents.graph as graph_module
from backend.app.db.session import Base, get_db
from backend.app.db import models
from backend.app.db.models import (
    ProductModel,
    CampaignModel,
    CampaignCostAssumptionModel,
    InventorySnapshotModel,
    SupplierReplenishmentModel,
)

from backend.app.main import app
import backend.app.main as main_module


# --------------------------------------------------
# 1. Create an isolated in-memory SQLite database
# --------------------------------------------------

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


# Ensure FastAPI startup uses the in-memory test engine.
main_module.engine = test_engine


# --------------------------------------------------
# 2. Override database dependency
# --------------------------------------------------

def override_get_db():
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------
# 3. Seed test data
# --------------------------------------------------

def seed_test_data(db):

    product_ids = [
        "HOBBIES_1_001",
        "HOBBIES_1_002",
        "HOBBIES_1_004",
    ]

    # Products
    for product_id in product_ids:
        db.add(
            ProductModel(
                product_id=product_id,
                product_name=f"Test Product {product_id}",
                cat_id="HOBBIES_1",
                dept_id="HOBBIES_1",
                store_id="CA_1",
                base_price=10.00,
            )
        )

    db.flush()

    # Campaigns
    campaigns = [
        CampaignModel(
            campaign_id="CAMP-001",
            campaign_name="Test Campaign 001",
            campaign_type="discount",
            start_date=date(2016, 4, 25),
            end_date=date(2016, 5, 1),
            target_product_ids=(
                "HOBBIES_1_001;HOBBIES_1_002"
            ),
            target_product_names="Test Product 001, Test Product 002",
            target_segments="test_segment",
            campaign_budget=5000.00,
            discount_rate=0.10,
            status="candidate",
            scenario_label="test_scenario",
        ),
        CampaignModel(
            campaign_id="CAMP-002",
            campaign_name="Test Campaign 002",
            campaign_type="discount",
            start_date=date(2016, 4, 25),
            end_date=date(2016, 5, 1),
            target_product_ids="HOBBIES_1_001",
            target_product_names="Test Product 001",
            target_segments="test_segment",
            campaign_budget=8500.00,
            discount_rate=0.10,
            status="candidate",
            scenario_label="test_scenario",
        ),
    ]

    db.add_all(campaigns)
    db.flush()

    # Campaign cost assumptions
    for campaign_id in ["CAMP-001", "CAMP-002"]:
        db.add(
            CampaignCostAssumptionModel(
                campaign_id=campaign_id,
                fixed_campaign_cost=800.00,
                cost_per_contact=0.0800,
                discount_cost_assumption="retailer_absorbed",
                logistics_cost_assumption=1.20,
                cost_accounting_method="activity_based_costing",
            )
        )

    # Inventory snapshots
    for product_id in product_ids:
        db.add(
            InventorySnapshotModel(
                product_id=product_id,
                product_name=f"Test Product {product_id}",
                store_id="CA_1",
                on_hand_stock=1000,
                reserved_stock=0,
                available_stock=1000,
                safety_stock=50,
                inventory_updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )

    # Supplier evidence used by proposal approval and activation tests.
    for product_id in product_ids:
        db.add(
            SupplierReplenishmentModel(
                supplier_id=f"SUPP_{product_id}",
                product_id=product_id,
                product_name=f"Test Product {product_id}",
                lead_time_days=4,
                minimum_order_quantity=20,
                replenishment_capacity=200,
                expected_replenishment_date=date(2016, 4, 26),
                supplier_status="active",
            )
        )

    db.commit()


# --------------------------------------------------
# 4. Session-scoped test database fixture
# --------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def setup_test_database():

    previous_overrides = app.dependency_overrides.copy()
    # Save the original graph database session factory.
    previous_graph_session_local = graph_module.SessionLocal

    # Use the same in-memory test database for graph orchestration.
    graph_module.SessionLocal = TestingSessionLocal
    # Create tables in the isolated in-memory database.
    Base.metadata.create_all(bind=test_engine)

    # Override FastAPI database dependency.
    app.dependency_overrides[get_db] = override_get_db

    db = TestingSessionLocal()

    try:
        seed_test_data(db)
    finally:
        db.close()

    yield

    # Restore previous dependency overrides and graph session factory.
    graph_module.SessionLocal = previous_graph_session_local
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous_overrides)

    # Dispose only the in-memory test database.
    test_engine.dispose()


