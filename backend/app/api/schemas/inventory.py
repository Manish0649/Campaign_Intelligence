from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class InventorySnapshotBase(BaseModel):
    product_id: str
    product_name: str
    store_id: str = "CA_1"
    on_hand_stock: int = Field(..., ge=0)
    reserved_stock: int = Field(..., ge=0)
    available_stock: int = Field(..., ge=0)
    safety_stock: int = Field(..., ge=0)
    inventory_updated_at: datetime

class InventorySnapshotResponse(InventorySnapshotBase):
    model_config = ConfigDict(from_attributes=True)

class SupplierReplenishmentBase(BaseModel):
    supplier_id: str
    product_id: str
    product_name: str
    lead_time_days: Optional[int] = Field(None, description="Supplier lead time in days. None if missing.")
    minimum_order_quantity: int = Field(..., gt=0)
    replenishment_capacity: int = Field(..., gt=0)
    expected_replenishment_date: date
    supplier_status: str = Field(..., description="'active' or 'suspended'")

class SupplierReplenishmentResponse(SupplierReplenishmentBase):
    model_config = ConfigDict(from_attributes=True)

