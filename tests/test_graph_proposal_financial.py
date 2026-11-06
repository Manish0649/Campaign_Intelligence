from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app.agents import graph


# ---------------------------------------------------------
# Common test data
# ---------------------------------------------------------

def make_test_state(
    expected_contribution=-1055.21,
    budget_status="passed",
    inventory_status="passed",
    selected_campaign_id="CAMP-002",
    include_selected_option=True
):
    """
    Creates a sample LangGraph state for proposal generation.
    """

    feasible_options = []

    if include_selected_option:
        feasible_options.append({
            "campaign_id": selected_campaign_id,
            "campaign_name": "Test Campaign",
            "expected_contribution": expected_contribution,
            "feasibility_status": "feasible_for_review"
        })

    return {
        "decision_result": {
            "selected_campaign_id": selected_campaign_id,
            "framework_used": "laya",
            "objective_values": {
                "contribution": expected_contribution,
                "inventory_suitability": 0.77
            },
            "decision_rationale": "Selected by multi-objective ranking."
        },

        "feasible_options": feasible_options,

        "feasibility_evaluations": {
            selected_campaign_id: {
                "status": "feasible_for_review",
                "budget_validation": budget_status,
                "inventory_validation": inventory_status
            }
        },

        "forecast_version": "m5-dynamic-linear-v2",

        "audit_log": [
            "Test orchestration initialized."
        ]
    }


def make_mock_proposal_repository():
    """
    Creates a mocked ProposalRepository.

    No actual database operation will take place.
    """

    repository = MagicMock()

    repository.save_proposal.return_value = SimpleNamespace(
        proposal_id="PROP-TEST-001",
        campaign_id="CAMP-002",
        forecast_version="m5-dynamic-linear-v2",
        decision_status="selected_by_laya",
        selected_option_id="OPT-1-MULTI-OBJECTIVE",
        budget_validation_status="passed",
        inventory_validation_status="passed",
        approval_status="pending_review",
        created_at=datetime(2026, 11, 5, 10, 0, 0)
    )

    return repository


def mock_database_dependencies(monkeypatch):
    """
    Replaces database-related dependencies with mocks.
    """

    repository = make_mock_proposal_repository()

    monkeypatch.setattr(
        graph,
        "get_db_session",
        lambda config: object()
    )

    monkeypatch.setattr(
        graph,
        "ProposalRepository",
        lambda db: repository
    )

    return repository


# ---------------------------------------------------------
# Test 1: Negative contribution should NOT reject proposal
# ---------------------------------------------------------

def test_negative_contribution_generates_proposal(monkeypatch):

    repository = mock_database_dependencies(monkeypatch)

    state = make_test_state(
        expected_contribution=-1055.21
    )

    result = graph.generate_proposal_node(
        state=state,
        config={}
    )

    proposal = result["generated_proposal"]

    assert result["has_errors"] is False

    assert result["current_step"] == "proposal_generated"

    assert proposal is not None

    assert proposal["approval_status"] == "pending_review"

    financial = proposal["financial_assessment"]

    assert financial["expected_contribution"] == -1055.21

    assert (
        financial["financial_status"]
        == "negative_expected_contribution"
    )

    assert financial["requires_financial_attention"] is True

    assert financial["financial_warning"] is not None

    repository.save_proposal.assert_called_once()

    print("\nTEST 1 PASSED: Negative contribution generated proposal.")


# ---------------------------------------------------------
# Test 2: Positive contribution should generate proposal
# ---------------------------------------------------------

def test_positive_contribution_generates_proposal(monkeypatch):

    repository = mock_database_dependencies(monkeypatch)

    state = make_test_state(
        expected_contribution=500.00
    )

    result = graph.generate_proposal_node(
        state=state,
        config={}
    )

    proposal = result["generated_proposal"]

    assert result["has_errors"] is False

    assert result["current_step"] == "proposal_generated"

    assert proposal is not None

    financial = proposal["financial_assessment"]

    assert financial["expected_contribution"] == 500.00

    assert (
        financial["financial_status"]
        == "positive_expected_contribution"
    )

    assert financial["financial_warning"] is None

    assert financial["requires_financial_attention"] is False

    assert proposal["approval_status"] == "pending_review"

    repository.save_proposal.assert_called_once()

    print("\nTEST 2 PASSED: Positive contribution generated proposal.")


# ---------------------------------------------------------
# Test 3: Budget failure should abort proposal
# ---------------------------------------------------------

def test_negative_contribution_with_failed_budget_aborts(
    monkeypatch
):

    repository = mock_database_dependencies(monkeypatch)

    state = make_test_state(
        expected_contribution=-1055.21,
        budget_status="failed"
    )

    result = graph.generate_proposal_node(
        state=state,
        config={}
    )

    assert result["generated_proposal"] is None

    assert result["has_errors"] is True

    assert result["current_step"] == "proposal_aborted"

    assert (
        result["error_message"]
        == "Budget or inventory validation did not pass."
    )

    # Repository must not be used when validation fails.
    repository.save_proposal.assert_not_called()

    print("\nTEST 3 PASSED: Failed budget aborted proposal.")


# ---------------------------------------------------------
# Test 4: Missing selected campaign should abort proposal
# ---------------------------------------------------------

def test_missing_selected_campaign_aborts(monkeypatch):

    repository = mock_database_proposal_repository = (
        make_mock_proposal_repository()
    )

    monkeypatch.setattr(
        graph,
        "get_db_session",
        lambda config: object()
    )

    monkeypatch.setattr(
        graph,
        "ProposalRepository",
        lambda db: repository
    )

    state = make_test_state(
        expected_contribution=-1055.21,
        include_selected_option=False
    )

    result = graph.generate_proposal_node(
        state=state,
        config={}
    )

    assert result["generated_proposal"] is None

    assert result["has_errors"] is True

    assert result["current_step"] == "proposal_aborted"

    assert (
        result["error_message"]
        == "Selected campaign was not found in "
           "the feasible options."
    )

    repository.save_proposal.assert_not_called()

    print("\nTEST 4 PASSED: Missing selected campaign aborted proposal.")


# ---------------------------------------------------------
# Test 5: Failed inventory should abort proposal
# ---------------------------------------------------------

def test_negative_contribution_with_failed_inventory_aborts(
    monkeypatch
):

    repository = mock_database_dependencies(monkeypatch)

    state = make_test_state(
        expected_contribution=-1055.21,
        inventory_status="failed"
    )

    result = graph.generate_proposal_node(
        state=state,
        config={}
    )

    assert result["generated_proposal"] is None

    assert result["has_errors"] is True

    assert result["current_step"] == "proposal_aborted"

    repository.save_proposal.assert_not_called()

    print("\nTEST 5 PASSED: Failed inventory aborted proposal.")


# ---------------------------------------------------------
# Test 6: Zero contribution should generate break-even proposal
# ---------------------------------------------------------

def test_zero_contribution_generates_break_even_proposal(
    monkeypatch
):

    repository = mock_database_dependencies(monkeypatch)

    state = make_test_state(
        expected_contribution=0
    )

    result = graph.generate_proposal_node(
        state=state,
        config={}
    )

    proposal = result["generated_proposal"]

    assert result["has_errors"] is False

    assert proposal is not None

    financial = proposal["financial_assessment"]

    assert financial["expected_contribution"] == 0

    assert financial["financial_status"] == "break_even"

    assert financial["requires_financial_attention"] is True

    assert financial["financial_warning"] is not None

    repository.save_proposal.assert_called_once()

    print("\nTEST 6 PASSED: Break-even proposal generated.")