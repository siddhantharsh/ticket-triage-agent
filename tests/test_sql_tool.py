from app.tools.sql_tool import lookup_customer_context


def test_lookup_known_customer_without_order_resolves_latest_order(test_db):
    result = lookup_customer_context("CUST-003", None, db_path=test_db)
    assert result["found"] is True
    assert result["customer_id"] == "CUST-003"
    assert result["plan_tier"] == "enterprise"
    assert result["order_id"] == "ORD-1004"
    assert result["status"] == "delivered"


def test_lookup_known_customer_with_specific_order(test_db):
    result = lookup_customer_context("CUST-002", "ORD-1003", db_path=test_db)
    assert result["found"] is True
    assert result["order_id"] == "ORD-1003"
    assert result["status"] == "pending"


def test_lookup_order_belonging_to_different_customer_is_ignored(test_db):
    result = lookup_customer_context("CUST-002", "ORD-1004", db_path=test_db)
    assert result["found"] is True
    assert result["status"] is None


def test_lookup_unknown_customer_returns_not_found(test_db):
    result = lookup_customer_context("CUST-999", None, db_path=test_db)
    assert result == {
        "customer_id": "CUST-999",
        "order_id": None,
        "status": None,
        "plan_tier": None,
        "found": False,
    }


def test_lookup_without_customer_id_returns_not_found(test_db):
    result = lookup_customer_context(None, None, db_path=test_db)
    assert result["found"] is False
