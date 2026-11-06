
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session

from backend.app.db.models import (
    CampaignModel,
    CampaignCostAssumptionModel,
    ProductModel,
)
from backend.app.api.schemas.campaign import CampaignCostAssumption


class CampaignRepository:
    def __init__(self, db: Session):
        if db is None:
            raise ValueError(
                "CampaignRepository requires a valid SQLAlchemy session."
            )

        self.db = db

    @staticmethod
    def _campaign_to_dict(campaign: CampaignModel) -> Dict[str, Any]:
        return {
            "campaign_id": campaign.campaign_id,
            "campaign_name": campaign.campaign_name,
            "campaign_type": campaign.campaign_type,
            "start_date": campaign.start_date,
            "end_date": campaign.end_date,
            "target_product_ids": [
                product_id.strip()
                for product_id in (campaign.target_product_ids or "").split(";")
                if product_id.strip()
            ],
            "target_segments": campaign.target_segments,
            "campaign_budget": float(campaign.campaign_budget),
            "discount_rate": float(campaign.discount_rate),
            "status": campaign.status,
            "scenario_label": campaign.scenario_label,
        }

    def get_campaign(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        try:
            campaign = (
                self.db.query(CampaignModel)
                .filter(CampaignModel.campaign_id == campaign_id)
                .first()
            )

            if campaign is None:
                return None

            return self._campaign_to_dict(campaign)

        except Exception as exc:
            self.db.rollback()
            raise RuntimeError(
                f"Failed to fetch campaign '{campaign_id}' from NeonDB."
            ) from exc

    def get_all_campaigns(self) -> List[Dict[str, Any]]:
        try:
            campaigns = self.db.query(CampaignModel).all()

            return [
                self._campaign_to_dict(campaign)
                for campaign in campaigns
            ]

        except Exception as exc:
            self.db.rollback()
            raise RuntimeError(
                "Failed to fetch campaigns from NeonDB."
            ) from exc

    def get_cost_assumption(
        self,
        campaign_id: str,
    ) -> CampaignCostAssumption:
        try:
            cost = (
                self.db.query(CampaignCostAssumptionModel)
                .filter(
                    CampaignCostAssumptionModel.campaign_id == campaign_id
                )
                .first()
            )

            if cost is None:
                raise LookupError(
                    f"No cost assumptions found for campaign '{campaign_id}'."
                )

            return CampaignCostAssumption(
                campaign_id=cost.campaign_id,
                fixed_campaign_cost=float(cost.fixed_campaign_cost),
                cost_per_contact=float(cost.cost_per_contact),
                discount_cost_assumption=cost.discount_cost_assumption,
                logistics_cost_assumption=float(cost.logistics_cost_assumption),
                cost_accounting_method=cost.cost_accounting_method,
            )

        except LookupError:
            raise

        except Exception as exc:
            self.db.rollback()
            raise RuntimeError(
                f"Failed to fetch cost assumptions for campaign '{campaign_id}'."
            ) from exc

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        try:
            product = (
                self.db.query(ProductModel)
                .filter(ProductModel.product_id == product_id)
                .first()
            )

            if product is None:
                return None

            return {
                "product_id": product.product_id,
                "product_name": product.product_name,
                "cat_id": product.cat_id,
                "dept_id": product.dept_id,
                "store_id": product.store_id,
                "base_price": float(product.base_price) if product.base_price is not None else None,
            }

        except Exception as exc:
            self.db.rollback()
            raise RuntimeError(
                f"Failed to fetch product '{product_id}' from NeonDB."
            ) from exc
