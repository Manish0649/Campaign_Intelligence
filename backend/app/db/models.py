from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Date,
    DateTime,
    Numeric,
    ForeignKey,
    CheckConstraint,
    JSON,
)
from backend.app.db.session import Base


def utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class ProductModel(Base):
    __tablename__ = "dim_products"
    __table_args__ = (CheckConstraint("base_price > 0", name="ck_products_positive_price"),)

    product_id = Column(String(50), primary_key=True, index=True)
    product_name = Column(String(255), nullable=False)
    cat_id = Column(String(50), nullable=False)
    dept_id = Column(String(50), nullable=False)
    store_id = Column(String(20), nullable=False)
    base_price = Column(Numeric(10, 2), nullable=False)

class DailySalesModel(Base):
    __tablename__ = "fct_daily_sales"
    __table_args__ = (
        CheckConstraint("sales_units >= 0", name="ck_daily_sales_nonnegative_units"),
        CheckConstraint("sell_price > 0", name="ck_daily_sales_positive_price"),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_daily_sales_valid_month"),
        CheckConstraint("is_weekend IN (0, 1)", name="ck_daily_sales_weekend_flag"),
        CheckConstraint("snap_flag IN (0, 1)", name="ck_daily_sales_snap_flag"),
    )

    product_id = Column(String(50), ForeignKey("dim_products.product_id", ondelete="CASCADE"), primary_key=True)
    store_id = Column(String(20), primary_key=True)
    date = Column(Date, primary_key=True, index=True)
    sales_units = Column(Integer, nullable=False)
    sell_price = Column(Numeric(10, 2), nullable=False)
    weekday = Column(String(20), nullable=False)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    is_weekend = Column(Integer, nullable=False)
    event_name = Column(String(100), default="None")
    snap_flag = Column(Integer, nullable=False)

class InventorySnapshotModel(Base):
    __tablename__ = "fct_inventory_snapshots"
    __table_args__ = (
        CheckConstraint("on_hand_stock >= 0", name="ck_inventory_on_hand_nonnegative"),
        CheckConstraint("reserved_stock >= 0", name="ck_inventory_reserved_nonnegative"),
        CheckConstraint("available_stock >= 0", name="ck_inventory_available_nonnegative"),
        CheckConstraint("safety_stock >= 0", name="ck_inventory_safety_nonnegative"),
    )

    product_id = Column(String(50), ForeignKey("dim_products.product_id", ondelete="CASCADE"), primary_key=True)
    store_id = Column(String(20), primary_key=True, default="CA_1")
    product_name = Column(String(255), nullable=False)
    on_hand_stock = Column(Integer, nullable=False)
    reserved_stock = Column(Integer, nullable=False)
    available_stock = Column(Integer, nullable=False)
    safety_stock = Column(Integer, nullable=False)
    inventory_updated_at = Column(DateTime, nullable=False, default=utcnow_naive)

class SupplierReplenishmentModel(Base):
    __tablename__ = "fct_supplier_replenishment"
    __table_args__ = (
        CheckConstraint("lead_time_days IS NULL OR lead_time_days > 0", name="ck_supplier_positive_lead_time"),
        CheckConstraint("minimum_order_quantity > 0", name="ck_supplier_positive_moq"),
        CheckConstraint("replenishment_capacity > 0", name="ck_supplier_positive_capacity"),
        CheckConstraint("supplier_status IN ('active', 'suspended')", name="ck_supplier_valid_status"),
    )

    supplier_id = Column(String(50), primary_key=True)
    product_id = Column(String(50), ForeignKey("dim_products.product_id", ondelete="CASCADE"), primary_key=True)
    product_name = Column(String(255), nullable=False)
    lead_time_days = Column(Integer, nullable=True)
    minimum_order_quantity = Column(Integer, nullable=False)
    replenishment_capacity = Column(Integer, nullable=False)
    expected_replenishment_date = Column(Date, nullable=False)
    supplier_status = Column(String(50), nullable=False)

class CampaignModel(Base):
    __tablename__ = "dim_campaigns"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_campaign_valid_date_range"),
        CheckConstraint("campaign_budget > 0", name="ck_campaign_positive_budget"),
        CheckConstraint("discount_rate BETWEEN 0 AND 1", name="ck_campaign_discount_range"),
    )

    campaign_id = Column(String(50), primary_key=True, index=True)
    campaign_name = Column(String(255), nullable=False)
    campaign_type = Column(String(100), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    target_product_ids = Column(String(255), nullable=False)
    target_product_names = Column(String(500), nullable=False)
    target_segments = Column(String(100), nullable=False)
    campaign_budget = Column(Numeric(12, 2), nullable=False)
    discount_rate = Column(Numeric(5, 4), nullable=False)
    status = Column(String(50), nullable=False, default="candidate")
    scenario_label = Column(String(255), nullable=False)

class CampaignCostAssumptionModel(Base):
    __tablename__ = "fct_campaign_cost_assumptions"
    __table_args__ = (
        CheckConstraint("fixed_campaign_cost >= 0", name="ck_cost_fixed_nonnegative"),
        CheckConstraint("cost_per_contact >= 0", name="ck_cost_contact_nonnegative"),
        CheckConstraint("logistics_cost_assumption >= 0", name="ck_cost_logistics_nonnegative"),
    )

    campaign_id = Column(String(50), ForeignKey("dim_campaigns.campaign_id", ondelete="CASCADE"), primary_key=True)
    fixed_campaign_cost = Column(Numeric(10, 2), nullable=False, default=Decimal("800.00"))
    cost_per_contact = Column(Numeric(10, 4), nullable=False, default=Decimal("0.0800"))
    discount_cost_assumption = Column(String(100), nullable=False, default="retailer_absorbed")
    logistics_cost_assumption = Column(Numeric(10, 2), nullable=False, default=Decimal("1.20"))
    cost_accounting_method = Column(String(100), nullable=False, default="activity_based_costing")

class CampaignProposalModel(Base):
    __tablename__ = "fct_campaign_proposals"
    __table_args__ = (
        CheckConstraint("approval_status IN ('approved', 'pending_review', 'rejected')", name="ck_proposal_valid_approval_status"),
    )

    proposal_id = Column(String(50), primary_key=True, index=True)
    campaign_id = Column(String(50), ForeignKey("dim_campaigns.campaign_id", ondelete="CASCADE"), nullable=False, index=True)
    forecast_version = Column(String(100), nullable=False, default="m5-dynamic-linear-v2")
    decision_status = Column(String(100), nullable=False)
    selected_option_id = Column(String(100), nullable=False, default="OPT-1-STANDARD")
    budget_validation_status = Column(String(100), nullable=False)
    inventory_validation_status = Column(String(100), nullable=False)
    approval_status = Column(String(50), nullable=False, default="pending_review")
    approver_id = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow_naive)
    approved_at = Column(DateTime, nullable=True)
    activated_at = Column(DateTime, nullable=True)



class ProposalAuditEventModel(Base):
    __tablename__ = "fct_proposal_audit_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('proposal_created', 'proposal_approved', 'proposal_rejected', 'proposal_activated')",
            name="ck_proposal_audit_event_type",
        ),
    )

    event_id = Column(String(36), primary_key=True)
    proposal_id = Column(
        String(50),
        ForeignKey("fct_campaign_proposals.proposal_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = Column(String(50), nullable=False)
    actor_id = Column(String(100), nullable=False)
    actor_role = Column(String(50), nullable=False)
    details = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utcnow_naive, index=True)
