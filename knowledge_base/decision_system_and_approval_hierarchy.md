# Decision Architecture & Approval Authority Hierarchy

## 1. Principles of Decision Governance
1. **Rule 2 (Domain Owns Feasibility)**: Budget, inventory availability, replenishment timing, and safety stock compliance must remain strictly deterministic.
2. **Rule 3 (Decision Layer Optimizes Feasible Options)**:
   - Frameworks like OpenJEV or Laya can rank, score, or compare feasible campaign alternatives based on multi-objective trade-offs (e.g., maximizing contribution margin vs. minimizing logistics risk).
   - The decision layer **cannot** override hard physical or financial constraints; it cannot make an infeasible campaign valid.
3. **Rule 4 (Agents Coordinate, Humans Approve)**:
   - LLM agents and LangGraph workflows are coordinators and analysts.
   - An AI agent cannot autonomously launch campaigns or authorize inventory commitments. Human approval is strictly required before activation.

## 2. Multi-Tier Financial Approval Authority Hierarchy
Campaign activation requests are governed by spending limits tied to organizational roles:

| Role Code | Role Title | Spending Authority Limit ($) | Approval Capabilities |
| :--- | :--- | :---: | :--- |
| `MGR-MKT` | Campaign Manager | Up to **$7,500** | Standard digital and flash sale campaigns |
| `MGR-STORE` | Store Operations Manager | Up to **$10,000** | Localized store promotions (`CA_1`) |
| `MGR-INV` | Inventory & Supply Manager | Up to **$20,000** | Stock-intensive grocery and replenishment campaigns |
| `APPR-FIN` | Finance Controller | Up to **$50,000** | Multi-channel, high-spend promotional blitzes |
| `DIR-MKT` | Marketing Director | Up to **$100,000** | Cross-department seasonal campaigns |
| `EXEC-DIR` | Executive Vice President | Up to **$250,000** | Enterprise-wide retail events |
| `SYS-ADMIN` | System Administrator | Up to **$1,000,000** | Emergency override authority (strictly audited) |

## 3. Pre-Activation Re-validation Requirement
Even after receiving human sign-off, the system executes an automated re-validation check (`POST /campaigns/proposals/{proposal_id}/approval`):
- Verifies that available inventory has not been consumed by competing orders since proposal creation.
- Confirms that budget limit has not been modified.
- Verifies that supplier status remains `active`.
- If re-validation succeeds, the proposal transitions from `pending_review` to `approved` and audit logs are recorded.

