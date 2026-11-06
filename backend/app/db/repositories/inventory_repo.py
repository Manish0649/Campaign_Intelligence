
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from backend.app.db.models import (
    InventorySnapshotModel,
    SupplierReplenishmentModel,
)


class InventoryRepository:
    def __init__(self, db: Session):
        if db is None:
            raise ValueError(
                "InventoryRepository requires a valid SQLAlchemy session."
            )

        self.db = db

    def get_inventory_snapshot(
        self,
        product_id: str,
        store_id: str = "CA_1",
    ) -> Optional[Dict[str, Any]]:
        try:
            snapshot = (
                self.db.query(InventorySnapshotModel)
                .filter(
                    InventorySnapshotModel.product_id == product_id,
                    InventorySnapshotModel.store_id == store_id,
                )
                .first()
            )

            if snapshot is None:
                return None

            return {
                "product_id": snapshot.product_id,
                "product_name": snapshot.product_name,
                "store_id": snapshot.store_id,
                "on_hand_stock": int(snapshot.on_hand_stock),
                "reserved_stock": int(snapshot.reserved_stock),
                "available_stock": int(snapshot.available_stock),
                "safety_stock": int(snapshot.safety_stock),
                "inventory_updated_at": snapshot.inventory_updated_at,
            }

        except Exception as exc:
            self.db.rollback()
            raise RuntimeError(
                f"Failed to fetch inventory snapshot for product "
                f"'{product_id}' at store '{store_id}'."
            ) from exc

    def get_supplier_replenishment(
        self,
        product_id: str,
    ) -> Optional[Dict[str, Any]]:
        try:
            supplier = (
                self.db.query(SupplierReplenishmentModel)
                .filter(
                    SupplierReplenishmentModel.product_id == product_id
                )
                .first()
            )

            if supplier is None:
                return None

            return {
                "supplier_id": supplier.supplier_id,
                "product_id": supplier.product_id,
                "product_name": supplier.product_name,
                "lead_time_days": (
                    int(supplier.lead_time_days)
                    if supplier.lead_time_days is not None
                    else None
                ),
                "minimum_order_quantity": int(
                    supplier.minimum_order_quantity
                ),
                "replenishment_capacity": int(
                    supplier.replenishment_capacity
                ),
                "expected_replenishment_date": (
                    supplier.expected_replenishment_date
                ),
                "supplier_status": supplier.supplier_status,
            }

        except Exception as exc:
            self.db.rollback()
            raise RuntimeError(
                f"Failed to fetch supplier replenishment for "
                f"product '{product_id}'."
            ) from exc
