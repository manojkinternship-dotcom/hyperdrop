import pytest
from app.core.orchestrator import orchestrator

def test_valid_outcomes():
    data = {
        "outcome": "leave with security",
        "recipient_name": "Ramesh",
        "recipient_role": "security",
        "location": "Gate 1",
        "tower": "Tower B"
    }
    extracted = orchestrator.validate_extracted_outcome(data, order_value=500.0)
    assert extracted.outcome == "leave with security"
    assert extracted.recipient_name == "Ramesh"
    assert extracted.recipient_role == "security"

def test_invalid_outcome_rejected():
    data = {
        "outcome": "throw over balcony"
    }
    with pytest.raises(ValueError) as excinfo:
        orchestrator.validate_extracted_outcome(data, order_value=500.0)
    assert "Invalid outcome" in str(excinfo.value)

def test_relative_handover_requires_recipient_name():
    data = {
        "outcome": "give to relative/neighbour",
        "recipient_role": "relative"
    }
    with pytest.raises(ValueError) as excinfo:
        orchestrator.validate_extracted_outcome(data, order_value=500.0)
    assert "Recipient name is required" in str(excinfo.value)

def test_high_value_order_requires_confirmation():
    data = {
        "outcome": "leave at door",
        "verbal_confirmed": False
    }
    # High value order (₹2500 >= ₹2000 threshold)
    with pytest.raises(ValueError) as excinfo:
        orchestrator.validate_extracted_outcome(data, order_value=2500.0)
    assert "High-value order" in str(excinfo.value)

def test_reschedule_outcome():
    data = {
        "outcome": "reschedule",
        "reschedule_minutes": 20
    }
    extracted = orchestrator.validate_extracted_outcome(data, order_value=400.0)
    assert extracted.outcome == "reschedule"
    assert extracted.reschedule_minutes == 20
