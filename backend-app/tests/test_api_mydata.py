"""Tests for /v1/mydata endpoints."""

import httpx
import pytest

from app.services.mydata_service import reset_consent_store


@pytest.fixture
def mock_app_state(mock_neptune, mock_opensearch, mock_bedrock, mock_embedding, mock_s3):
    from app.main import app

    app.state.neptune = mock_neptune
    app.state.opensearch = mock_opensearch
    app.state.bedrock = mock_bedrock
    app.state.embedding = mock_embedding
    app.state.s3 = mock_s3
    return app


@pytest.fixture(autouse=True)
def _clean_consent():
    reset_consent_store()
    yield
    reset_consent_store()


class TestConsentEndpoint:
    async def test_consent_grant(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/mydata/consent",
                json={"customer_id": "CUSTOMER_PARK", "action": "grant"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["consented"] is True
            assert data["customer_name"] == "박지영"
            assert len(data["contracts"]) == 2

    async def test_consent_revoke(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            # Grant first
            await client.post(
                "/v1/mydata/consent",
                json={"customer_id": "CUSTOMER_PARK", "action": "grant"},
            )
            # Then revoke
            response = await client.post(
                "/v1/mydata/consent",
                json={"customer_id": "CUSTOMER_PARK", "action": "revoke"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["consented"] is False
            assert data["contracts"] == []

    async def test_consent_unknown_customer_404(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/mydata/consent",
                json={"customer_id": "CUSTOMER_UNKNOWN", "action": "grant"},
            )
            assert response.status_code == 404

    async def test_consent_invalid_action_400(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/mydata/consent",
                json={"customer_id": "CUSTOMER_PARK", "action": "invalid"},
            )
            assert response.status_code == 400


class TestContractsEndpoint:
    async def test_get_contracts_with_consent(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            # Grant consent first
            await client.post(
                "/v1/mydata/consent",
                json={"customer_id": "CUSTOMER_PARK", "action": "grant"},
            )
            response = await client.get(
                "/v1/mydata/contracts", params={"customer_id": "CUSTOMER_PARK"}
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data["contracts"]) == 2

    async def test_get_contracts_without_consent(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/v1/mydata/contracts", params={"customer_id": "CUSTOMER_PARK"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["contracts"] == []


class TestCustomerEndpoint:
    async def test_get_customer_profile(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/v1/mydata/customer", params={"customer_id": "CUSTOMER_PARK"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["customer_name"] == "박지영"
            assert data["customer_id"] == "CUSTOMER_PARK"

    async def test_unknown_customer_404(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/v1/mydata/customer", params={"customer_id": "CUSTOMER_UNKNOWN"}
            )
            assert response.status_code == 404
