import logging
from datetime import datetime, timezone

from app.models.mydata import MergeContext, MyDataConsent, MyDataContract

logger = logging.getLogger("graphrag.mydata")

# Synthetic customer data for demo purposes.
# In production this would come from the MyData API (GET /v2/insu/insurances).
_SYNTHETIC_CUSTOMERS: dict[str, dict] = {
    "CUSTOMER_PARK": {
        "customer_id": "CUSTOMER_PARK",
        "customer_name": "박지영",
        "contracts": [
            {
                "contract_id": "CONTRACT_001",
                "policy_id": "Policy#hwl_h_whole_life",
                "policy_name": "한화생명 H종신보험 무배당",
                "product_type": "whole_life",
                "contract_status": "active",
                "start_date": "2020-03-15",
                "premium_amount": 300000,
                "coverage_amount": 100000000,
            },
            {
                "contract_id": "CONTRACT_002",
                "policy_id": "Policy#hwl_ehealthins",
                "policy_name": "한화생명 e건강보험 무배당",
                "product_type": "health",
                "contract_status": "active",
                "start_date": "2021-07-01",
                "premium_amount": 150000,
                "coverage_amount": 50000000,
            },
        ],
    },
    "CUSTOMER_KIM": {
        "customer_id": "CUSTOMER_KIM",
        "customer_name": "김민수",
        "contracts": [
            {
                "contract_id": "CONTRACT_003",
                "policy_id": "Policy#hwl_signature_h_cancer",
                "policy_name": "한화생명 시그니처H암보험 무배당",
                "product_type": "cancer",
                "contract_status": "active",
                "start_date": "2022-01-10",
                "premium_amount": 80000,
                "coverage_amount": 30000000,
            },
            {
                "contract_id": "CONTRACT_004",
                "policy_id": "Policy#hwl_pocket_fracture",
                "policy_name": "한화생명 포켓골절보험 무배당",
                "product_type": "fracture",
                "contract_status": "active",
                "start_date": "2023-05-20",
                "premium_amount": 15000,
                "coverage_amount": 10000000,
            },
        ],
    },
    "CUSTOMER_LEE": {
        "customer_id": "CUSTOMER_LEE",
        "customer_name": "이준혁",
        "contracts": [
            {
                "contract_id": "CONTRACT_005",
                "policy_id": "Policy#hwl_hcareins_nodividend",
                "policy_name": "한화생명 H간병보험 무배당",
                "product_type": "care",
                "contract_status": "active",
                "start_date": "2021-11-01",
                "premium_amount": 200000,
                "coverage_amount": 50000000,
            },
            {
                "contract_id": "CONTRACT_006",
                "policy_id": "Policy#hwl_ceo_h_term",
                "policy_name": "한화생명 경영인H정기보험 무배당",
                "product_type": "term",
                "contract_status": "active",
                "start_date": "2022-06-15",
                "premium_amount": 500000,
                "coverage_amount": 300000000,
            },
        ],
    },
    "CUSTOMER_CHOI": {
        "customer_id": "CUSTOMER_CHOI",
        "customer_name": "최서연",
        "contracts": [
            {
                "contract_id": "CONTRACT_007",
                "policy_id": "Policy#hwl_ecancer_nonrenewal",
                "policy_name": "한화생명 e암보험(비갱신형) 무배당",
                "product_type": "cancer",
                "contract_status": "active",
                "start_date": "2023-02-01",
                "premium_amount": 60000,
                "coverage_amount": 20000000,
            },
            {
                "contract_id": "CONTRACT_008",
                "policy_id": "Policy#hwl_inheritance_h",
                "policy_name": "한화생명 상속H종신보험 무배당",
                "product_type": "whole_life",
                "contract_status": "active",
                "start_date": "2019-08-20",
                "premium_amount": 400000,
                "coverage_amount": 200000000,
            },
        ],
    },
    "CUSTOMER_JUNG": {
        "customer_id": "CUSTOMER_JUNG",
        "customer_name": "정하나",
        "contracts": [
            {
                "contract_id": "CONTRACT_009",
                "policy_id": "Policy#hwl_needai_cancer",
                "policy_name": "한화생명 Need AI 암보험 무배당",
                "product_type": "cancer",
                "contract_status": "active",
                "start_date": "2024-01-15",
                "premium_amount": 45000,
                "coverage_amount": 20000000,
            },
            {
                "contract_id": "CONTRACT_010",
                "policy_id": "Policy#hwl_signature_h_health",
                "policy_name": "한화생명 시그니처H통합건강보험 납입면제형 무배당",
                "product_type": "health",
                "contract_status": "active",
                "start_date": "2023-09-01",
                "premium_amount": 120000,
                "coverage_amount": 50000000,
            },
        ],
    },
    "CUSTOMER_HAN": {
        "customer_id": "CUSTOMER_HAN",
        "customer_name": "한도윤",
        "contracts": [
            {
                "contract_id": "CONTRACT_011",
                "policy_id": "Policy#hwl_zeroh_term_life",
                "policy_name": "한화생명 제로백H종신보험 무배당",
                "product_type": "whole_life",
                "contract_status": "active",
                "start_date": "2022-04-01",
                "premium_amount": 250000,
                "coverage_amount": 100000000,
            },
            {
                "contract_id": "CONTRACT_012",
                "policy_id": "Policy#hwl_diabetes",
                "policy_name": "한화생명 H당뇨보험 무배당",
                "product_type": "diabetes",
                "contract_status": "active",
                "start_date": "2023-11-10",
                "premium_amount": 70000,
                "coverage_amount": 30000000,
            },
        ],
    },
    "CUSTOMER_SONG": {
        "customer_id": "CUSTOMER_SONG",
        "customer_name": "송민지",
        "contracts": [
            {
                "contract_id": "CONTRACT_013",
                "policy_id": "Policy#hwl_carebackcareplus",
                "policy_name": "한화생명 케어백간병플러스보험 무배당",
                "product_type": "care",
                "contract_status": "active",
                "start_date": "2022-08-15",
                "premium_amount": 180000,
                "coverage_amount": 50000000,
            },
            {
                "contract_id": "CONTRACT_014",
                "policy_id": "Policy#hwl_sangsaeng_friend",
                "policy_name": "한화생명 상생친구 보장보험 무배당",
                "product_type": "guarantee",
                "contract_status": "active",
                "start_date": "2021-03-20",
                "premium_amount": 100000,
                "coverage_amount": 50000000,
            },
        ],
    },
    "CUSTOMER_YOON": {
        "customer_id": "CUSTOMER_YOON",
        "customer_name": "윤재호",
        "contracts": [
            {
                "contract_id": "CONTRACT_015",
                "policy_id": "Policy#hwl_h_whole_life",
                "policy_name": "한화생명 H종신보험 무배당",
                "product_type": "whole_life",
                "contract_status": "active",
                "start_date": "2019-12-01",
                "premium_amount": 350000,
                "coverage_amount": 150000000,
            },
            {
                "contract_id": "CONTRACT_016",
                "policy_id": "Policy#hwl_signature_h_cancer",
                "policy_name": "한화생명 시그니처H암보험 무배당",
                "product_type": "cancer",
                "contract_status": "active",
                "start_date": "2021-06-01",
                "premium_amount": 90000,
                "coverage_amount": 30000000,
            },
            {
                "contract_id": "CONTRACT_017",
                "policy_id": "Policy#hwl_pocket_fracture",
                "policy_name": "한화생명 포켓골절보험 무배당",
                "product_type": "fracture",
                "contract_status": "active",
                "start_date": "2022-09-10",
                "premium_amount": 15000,
                "coverage_amount": 10000000,
            },
        ],
    },
    "CUSTOMER_KANG": {
        "customer_id": "CUSTOMER_KANG",
        "customer_name": "강수빈",
        "contracts": [
            {
                "contract_id": "CONTRACT_018",
                "policy_id": "Policy#hwl_ehealthins",
                "policy_name": "한화생명 e건강보험 무배당",
                "product_type": "health",
                "contract_status": "active",
                "start_date": "2020-05-01",
                "premium_amount": 130000,
                "coverage_amount": 50000000,
            },
            {
                "contract_id": "CONTRACT_019",
                "policy_id": "Policy#hwl_ecancer_nonrenewal",
                "policy_name": "한화생명 e암보험(비갱신형) 무배당",
                "product_type": "cancer",
                "contract_status": "active",
                "start_date": "2021-10-15",
                "premium_amount": 55000,
                "coverage_amount": 20000000,
            },
            {
                "contract_id": "CONTRACT_020",
                "policy_id": "Policy#hwl_hcareins_nodividend",
                "policy_name": "한화생명 H간병보험 무배당",
                "product_type": "care",
                "contract_status": "active",
                "start_date": "2023-01-20",
                "premium_amount": 160000,
                "coverage_amount": 50000000,
            },
        ],
    },
    "CUSTOMER_LIM": {
        "customer_id": "CUSTOMER_LIM",
        "customer_name": "임태현",
        "contracts": [
            {
                "contract_id": "CONTRACT_021",
                "policy_id": "Policy#hwl_inheritance_h",
                "policy_name": "한화생명 상속H종신보험 무배당",
                "product_type": "whole_life",
                "contract_status": "active",
                "start_date": "2020-09-01",
                "premium_amount": 450000,
                "coverage_amount": 200000000,
            },
            {
                "contract_id": "CONTRACT_022",
                "policy_id": "Policy#hwl_needai_cancer",
                "policy_name": "한화생명 Need AI 암보험 무배당",
                "product_type": "cancer",
                "contract_status": "active",
                "start_date": "2024-03-01",
                "premium_amount": 50000,
                "coverage_amount": 20000000,
            },
            {
                "contract_id": "CONTRACT_023",
                "policy_id": "Policy#hwl_zeroback_h_whole",
                "policy_name": "한화생명 제로백H종신보험 간편가입 무배당",
                "product_type": "whole_life",
                "contract_status": "active",
                "start_date": "2023-07-15",
                "premium_amount": 200000,
                "coverage_amount": 100000000,
            },
        ],
    },
}

# In-memory consent state (session-scoped for demo).
_consent_store: dict[str, bool] = {}


class MyDataService:
    def list_customers(self) -> list[dict]:
        """Return summary of all demo customers (for frontend customer selector)."""
        result = []
        for cid, data in _SYNTHETIC_CUSTOMERS.items():
            contracts_summary = [
                {"policy_name": c["policy_name"], "product_type": c["product_type"]}
                for c in data["contracts"]
            ]
            result.append({
                "customer_id": data["customer_id"],
                "customer_name": data["customer_name"],
                "contract_count": len(data["contracts"]),
                "contracts": contracts_summary,
            })
        return result

    def get_customer(self, customer_id: str) -> MyDataConsent | None:
        """Return customer profile with consent status, or None if unknown."""
        data = _SYNTHETIC_CUSTOMERS.get(customer_id)
        if not data:
            return None
        contracts = [MyDataContract(**c) for c in data["contracts"]]
        consented = _consent_store.get(customer_id, False)
        return MyDataConsent(
            customer_id=data["customer_id"],
            customer_name=data["customer_name"],
            consented=consented,
            consent_timestamp=(
                datetime.now(timezone.utc).isoformat() if consented else None
            ),
            contracts=contracts if consented else [],
        )

    def grant_consent(self, customer_id: str) -> MyDataConsent | None:
        """Grant MyData consent for the customer."""
        data = _SYNTHETIC_CUSTOMERS.get(customer_id)
        if not data:
            return None
        _consent_store[customer_id] = True
        contracts = [MyDataContract(**c) for c in data["contracts"]]
        return MyDataConsent(
            customer_id=data["customer_id"],
            customer_name=data["customer_name"],
            consented=True,
            consent_timestamp=datetime.now(timezone.utc).isoformat(),
            contracts=contracts,
        )

    def revoke_consent(self, customer_id: str) -> MyDataConsent | None:
        """Revoke MyData consent for the customer."""
        data = _SYNTHETIC_CUSTOMERS.get(customer_id)
        if not data:
            return None
        _consent_store[customer_id] = False
        return MyDataConsent(
            customer_id=data["customer_id"],
            customer_name=data["customer_name"],
            consented=False,
            consent_timestamp=None,
            contracts=[],
        )

    def get_contracts(self, customer_id: str) -> list[MyDataContract]:
        """Return contracts only if consent is granted."""
        if not _consent_store.get(customer_id, False):
            return []
        data = _SYNTHETIC_CUSTOMERS.get(customer_id)
        if not data:
            return []
        return [MyDataContract(**c) for c in data["contracts"]]

    def build_merge_context(
        self, customer_id: str, entry_policy_ids: list[str],
        *, consent_verified: bool = False,
    ) -> MergeContext | None:
        """Build an in-memory merge context for subgraph augmentation.

        Returns None if:
        - Customer not found
        - Consent not granted (skipped when consent_verified=True)
        - No contracts match entry_policy_ids (when provided)

        When consent_verified=True the caller has already confirmed consent
        (e.g. from the request body), so the per-pod _consent_store check is
        bypassed.  This avoids failures in multi-replica deployments where the
        consent grant may have been handled by a different pod.
        """
        if not consent_verified and not _consent_store.get(customer_id, False):
            return None

        data = _SYNTHETIC_CUSTOMERS.get(customer_id)
        if not data:
            return None

        contracts = [MyDataContract(**c) for c in data["contracts"]]
        if not contracts:
            return None

        # Filter to contracts matching entry policies if any policy IDs given
        if entry_policy_ids:
            matching = [c for c in contracts if c.policy_id in entry_policy_ids]
            # If no match, include all active contracts (query may be general)
            if not matching:
                matching = [c for c in contracts if c.contract_status == "active"]
        else:
            matching = [c for c in contracts if c.contract_status == "active"]

        if not matching:
            return None

        customer_node_id = f"Customer#{data['customer_name']}"
        customer_node = {
            "id": customer_node_id,
            "type": "Customer",
            "label": data["customer_name"],
            "properties": {
                "customer_id": data["customer_id"],
                "customer_name": data["customer_name"],
                "contract_count": len(matching),
            },
        }

        owns_edges = []
        activated_policy_ids = []
        for contract in matching:
            owns_edges.append(
                {
                    "source": customer_node_id,
                    "target": contract.policy_id,
                    "type": "OWNS",
                    "properties": {
                        "contract_id": contract.contract_id,
                        "start_date": contract.start_date,
                        "product_type": contract.product_type,
                        "contract_status": contract.contract_status,
                        "premium_amount": contract.premium_amount,
                    },
                }
            )
            activated_policy_ids.append(contract.policy_id)

        logger.info(
            f"MyData merge context built: customer={data['customer_name']}, "
            f"contracts={len(matching)}, activated_policies={activated_policy_ids}"
        )

        return MergeContext(
            customer_node=customer_node,
            owns_edges=owns_edges,
            activated_policy_ids=activated_policy_ids,
        )


def reset_consent_store():
    """Reset in-memory consent state. Used by tests."""
    _consent_store.clear()
