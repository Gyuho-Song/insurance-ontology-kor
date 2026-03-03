import pytest

from app.models.mydata import MergeContext, MyDataConsent, MyDataContract
from app.services.mydata_service import MyDataService, reset_consent_store


@pytest.fixture(autouse=True)
def _clean_consent():
    """Reset consent state before each test."""
    reset_consent_store()
    yield
    reset_consent_store()


@pytest.fixture
def svc():
    return MyDataService()


class TestGetCustomer:
    def test_get_synthetic_customer(self, svc):
        customer = svc.get_customer("CUSTOMER_PARK")
        assert customer is not None
        assert customer.customer_name == "박지영"
        assert customer.customer_id == "CUSTOMER_PARK"
        assert customer.consented is False
        assert customer.contracts == []  # Not consented yet

    def test_get_unknown_customer(self, svc):
        assert svc.get_customer("CUSTOMER_UNKNOWN") is None


class TestConsent:
    def test_grant_consent(self, svc):
        result = svc.grant_consent("CUSTOMER_PARK")
        assert result is not None
        assert result.consented is True
        assert result.consent_timestamp is not None
        assert len(result.contracts) == 2

    def test_revoke_consent(self, svc):
        svc.grant_consent("CUSTOMER_PARK")
        result = svc.revoke_consent("CUSTOMER_PARK")
        assert result is not None
        assert result.consented is False
        assert result.consent_timestamp is None
        assert result.contracts == []

    def test_grant_unknown_customer(self, svc):
        assert svc.grant_consent("CUSTOMER_UNKNOWN") is None

    def test_revoke_unknown_customer(self, svc):
        assert svc.revoke_consent("CUSTOMER_UNKNOWN") is None


class TestGetContracts:
    def test_get_contracts_with_consent(self, svc):
        svc.grant_consent("CUSTOMER_PARK")
        contracts = svc.get_contracts("CUSTOMER_PARK")
        assert len(contracts) == 2
        assert all(isinstance(c, MyDataContract) for c in contracts)

    def test_get_contracts_without_consent(self, svc):
        contracts = svc.get_contracts("CUSTOMER_PARK")
        assert contracts == []

    def test_get_contracts_unknown_customer(self, svc):
        contracts = svc.get_contracts("CUSTOMER_UNKNOWN")
        assert contracts == []

    def test_contracts_link_to_neptune_policy_ids(self, svc):
        svc.grant_consent("CUSTOMER_PARK")
        contracts = svc.get_contracts("CUSTOMER_PARK")
        for c in contracts:
            assert c.policy_id.startswith("Policy#")

    def test_contract_product_types(self, svc):
        svc.grant_consent("CUSTOMER_PARK")
        contracts = svc.get_contracts("CUSTOMER_PARK")
        types = {c.product_type for c in contracts}
        assert "whole_life" in types
        assert "health" in types


class TestBuildMergeContext:
    def test_build_merge_context_with_consent(self, svc):
        svc.grant_consent("CUSTOMER_PARK")
        ctx = svc.build_merge_context("CUSTOMER_PARK", [])
        assert ctx is not None
        assert isinstance(ctx, MergeContext)
        assert ctx.customer_node["type"] == "Customer"
        assert len(ctx.owns_edges) == 2
        assert len(ctx.activated_policy_ids) == 2

    def test_build_merge_context_without_consent(self, svc):
        ctx = svc.build_merge_context("CUSTOMER_PARK", [])
        assert ctx is None

    def test_build_merge_context_matching_policies(self, svc):
        svc.grant_consent("CUSTOMER_PARK")
        ctx = svc.build_merge_context(
            "CUSTOMER_PARK", ["Policy#hwl_h_whole_life"]
        )
        assert ctx is not None
        assert len(ctx.owns_edges) == 1
        assert ctx.activated_policy_ids == ["Policy#hwl_h_whole_life"]

    def test_build_merge_context_no_matching_falls_back(self, svc):
        """When entry_policy_ids don't match, include all active contracts."""
        svc.grant_consent("CUSTOMER_PARK")
        ctx = svc.build_merge_context(
            "CUSTOMER_PARK", ["Policy#nonexistent"]
        )
        assert ctx is not None
        assert len(ctx.owns_edges) == 2  # Falls back to all active

    def test_merge_context_customer_node_shape(self, svc):
        svc.grant_consent("CUSTOMER_PARK")
        ctx = svc.build_merge_context("CUSTOMER_PARK", [])
        node = ctx.customer_node
        assert node["id"] == "Customer#박지영"
        assert node["type"] == "Customer"
        assert node["label"] == "박지영"
        assert "customer_id" in node["properties"]
        assert "contract_count" in node["properties"]

    def test_merge_context_owns_edge_shape(self, svc):
        svc.grant_consent("CUSTOMER_PARK")
        ctx = svc.build_merge_context("CUSTOMER_PARK", [])
        for edge in ctx.owns_edges:
            assert edge["source"] == "Customer#박지영"
            assert edge["target"].startswith("Policy#")
            assert edge["type"] == "OWNS"
            assert "contract_id" in edge["properties"]
            assert "start_date" in edge["properties"]
            assert "product_type" in edge["properties"]

    def test_merge_context_activated_policy_ids(self, svc):
        svc.grant_consent("CUSTOMER_PARK")
        ctx = svc.build_merge_context("CUSTOMER_PARK", [])
        assert "Policy#hwl_h_whole_life" in ctx.activated_policy_ids
        assert "Policy#hwl_ehealthins" in ctx.activated_policy_ids

    def test_build_merge_context_unknown_customer(self, svc):
        ctx = svc.build_merge_context("CUSTOMER_UNKNOWN", [])
        assert ctx is None
