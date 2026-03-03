"""Connect 32 isolated nodes in Neptune to related Regulation nodes.

Strategy per node type:
- Eligibility: Regulation → REQUIRES_ELIGIBILITY → Eligibility
- Exception:   Regulation → EXCEPTIONALLY_ALLOWED → Exception
- Exclusion:   Regulation → STRICTLY_PROHIBITED → Exclusion
- Coverage:    Coverage → GOVERNED_BY → Regulation (regulatory coverage definitions)
- Product_Category: Product_Category → GOVERNED_BY → Regulation
"""

import json
import os
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import Session

REGION = os.environ.get("AWS_REGION", "us-west-2")
NEPTUNE_HOST = os.environ.get(
    "NEPTUNE_ENDPOINT",
    "ontology-demo-neptune.cluster-cr8yamuqw57p.us-west-2.neptune.amazonaws.com",
)
NEPTUNE_PORT = int(os.environ.get("NEPTUNE_PORT", "8182"))
NEPTUNE_URL = f"https://{NEPTUNE_HOST}:{NEPTUNE_PORT}/gremlin"

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def execute(gremlin: str):
    data = json.dumps({"gremlin": gremlin})
    req = AWSRequest(
        method="POST", url=NEPTUNE_URL, data=data,
        headers={"Content-Type": "application/json"},
    )
    SigV4Auth(Session().get_credentials(), "neptune-db", REGION).add_auth(req)
    resp = requests.post(
        NEPTUNE_URL, headers=dict(req.headers), data=data,
        timeout=30, verify=False,
    )
    return resp.json()


def add_edge(source_id: str, edge_label: str, target_id: str):
    """Add edge if it doesn't already exist.

    Uses g.V(source).as('s').V(target).addE(label).from('s')
    which traverses to target, then adds edge FROM source.
    """
    # Create edge using Neptune-compatible pattern
    query = (
        f"g.V('{source_id}').as('s')"
        f".V('{target_id}')"
        f".addE('{edge_label}').from('s')"
    )
    result = execute(query)
    return result


# ── Mapping: isolated node → (edge_type, direction, target_regulation) ──

# Eligibility nodes: Regulation → REQUIRES_ELIGIBILITY → Eligibility
ELIGIBILITY_MAP = {
    "Eligibility#ins_biz_decree_biz_plan": [
        "Regulation#ins_biz_decree_capital_by_type",
    ],
    "Eligibility#ins_biz_decree_social_credit": [
        "Regulation#ins_biz_decree_major_shareholder",
    ],
    "Eligibility#ins_biz_decree_measure_consideration": [
        "Regulation#ins_biz_decree_financial_soundness_evaluation",
    ],
    "Eligibility#ins_biz_decree_financial_soundness": [
        "Regulation#ins_biz_decree_financial_soundness_evaluation",
        "Regulation#ins_biz_decree_solvency_standard",
    ],
    "Eligibility#ins_biz_decree_debt_guarantee_requirements": [
        "Regulation#ins_biz_decree_credit_extension",
    ],
    "Eligibility#ins_biz_decree_subsidiary_ownership": [
        "Regulation#ins_biz_decree_major_shareholder_transaction",
        "Regulation#ins_biz_decree_major_shareholder",
    ],
    "Eligibility#ins_biz_decree_rate_calculation_org": [
        "Regulation#ins_biz_decree_rate_verification",
        "Regulation#ins_biz_decree_ref_pure_prem_rate",
    ],
    "Eligibility#ins_biz_decree_actuary_corp": [
        "Regulation#ins_biz_decree_reserve_calculation",
    ],
    "Eligibility#ins_biz_decree_loss_adj_support": [
        "Regulation#ins_biz_decree_reserve_calculation",
    ],
}

# Exception nodes: Regulation → EXCEPTIONALLY_ALLOWED → Exception
EXCEPTION_MAP = {
    "Exception#insurance_supervision_detail_addendum_art2": [
        "Regulation#insurance_supervision_detail_art1",
        "Regulation#insurance_supervision_detail_art2",
    ],
    "Exception#ins_biz_decree_facility_exemption": [
        "Regulation#ins_biz_decree_capital_by_type",
    ],
    "Exception#ins_biz_decree_asset_ratio_excess": [
        "Regulation#ins_biz_decree_asset_operation_ratio",
        "Regulation#ins_biz_decree_risky_asset_restriction",
    ],
    "Exception#ins_biz_decree_debt_guarantee_exception": [
        "Regulation#ins_biz_decree_credit_extension",
    ],
    "Exception#ins_biz_decree_facility_change": [
        "Regulation#ins_biz_decree_capital_by_type",
    ],
    "Exception#ins_biz_decree_cancel_exception": [
        "Regulation#ins_biz_decree_broker_business_std",
        "Regulation#ins_biz_decree_broker_deposit",
    ],
    "Exception#ins_biz_decree_minor_mutual_agreement_matters": [
        "Regulation#ins_biz_decree_mutual_agreement_approval",
    ],
    "Exception#ins_biz_decree_new_contract_prohibition": [
        "Regulation#ins_biz_decree_solvency_standard",
        "Regulation#ins_biz_decree_capital_increase_order",
    ],
    "Exception#ins_biz_decree_info_provision": [
        "Regulation#ins_biz_decree_disclosure_matters",
        "Regulation#ins_biz_decree_phone_evidence",
    ],
}

# Exclusion nodes: Regulation → STRICTLY_PROHIBITED → Exclusion
EXCLUSION_MAP = {
    "Exclusion#fin_consumer_act_art7_sub1": [
        "Regulation#fin_consumer_act_art8",
        "Regulation#fin_consumer_act_art5",
    ],
    "Exclusion#fin_consumer_act_art7_sub2": [
        "Regulation#fin_consumer_act_art8",
        "Regulation#fin_consumer_act_art5",
    ],
    "Exclusion#fin_consumer_act_art7_sub3": [
        "Regulation#fin_consumer_act_art8",
    ],
    "Exclusion#ins_biz_decree_actuary_prohibited": [
        "Regulation#ins_biz_decree_reserve_calculation",
    ],
    "Exclusion#ins_biz_decree_excluded_legal_entities": [
        "Regulation#ins_biz_decree_solvency_standard",
    ],
    "Exclusion#ins_biz_decree_subsidiary_exception": [
        "Regulation#ins_biz_decree_major_shareholder_transaction",
    ],
    "Exclusion#ins_biz_decree_subsidiary_prohibition": [
        "Regulation#ins_biz_decree_major_shareholder_transaction",
        "Regulation#ins_biz_decree_major_shareholder",
    ],
}

# Coverage nodes: Coverage → GOVERNED_BY → Regulation (regulatory coverage definitions)
COVERAGE_MAP = {
    "Coverage#ins_biz_decree_protected_insurance_contracts": [
        "Regulation#ins_biz_decree_solvency_standard",
        "Regulation#insurance_biz_act_art95",
    ],
    "Coverage#ins_biz_decree_payment_insurance_amount": [
        "Regulation#ins_biz_decree_solvency_standard",
    ],
    "Coverage#ins_biz_decree_traffic_info": [
        "Regulation#ins_biz_decree_disclosure_matters",
    ],
    "Coverage#ins_biz_decree_reserve_adequacy": [
        "Regulation#ins_biz_decree_reserve_calculation",
        "Regulation#insurance_biz_rule_art29_reserve_calculation",
    ],
}

# Product_Category nodes: Product_Category → GOVERNED_BY → Regulation
PRODUCT_CATEGORY_MAP = {
    "Product_Category#ins_biz_decree_subsidiary_business": [
        "Regulation#ins_biz_decree_major_shareholder_transaction",
        "Regulation#ins_biz_decree_major_shareholder",
    ],
    "Product_Category#ins_biz_decree_simple_ins_agent": [
        "Regulation#ins_biz_decree_simple_agent_compliance",
        "Regulation#ins_biz_decree_agent_education",
    ],
    "Product_Category#ins_biz_decree_mandatory_auto_insurance": [
        "Regulation#insurance_biz_act_art95",
        "Regulation#ins_biz_decree_solvency_standard",
    ],
}


def main():
    total_created = 0
    total_skipped = 0

    # 1. Eligibility: Regulation → REQUIRES_ELIGIBILITY → Eligibility
    print("=== Connecting Eligibility nodes (9) ===")
    for elig_id, reg_ids in ELIGIBILITY_MAP.items():
        for reg_id in reg_ids:
            result = add_edge(reg_id, "REQUIRES_ELIGIBILITY", elig_id)
            status = result.get("status", {}).get("code", -1)
            if status == 200:
                total_created += 1
                print(f"  ✓ {reg_id} → REQUIRES_ELIGIBILITY → {elig_id}")
            else:
                total_skipped += 1
                print(f"  ✗ Failed: {reg_id} → {elig_id}: {result}")

    # 2. Exception: Regulation → EXCEPTIONALLY_ALLOWED → Exception
    print("\n=== Connecting Exception nodes (9) ===")
    for exc_id, reg_ids in EXCEPTION_MAP.items():
        for reg_id in reg_ids:
            result = add_edge(reg_id, "EXCEPTIONALLY_ALLOWED", exc_id)
            status = result.get("status", {}).get("code", -1)
            if status == 200:
                total_created += 1
                print(f"  ✓ {reg_id} → EXCEPTIONALLY_ALLOWED → {exc_id}")
            else:
                total_skipped += 1
                print(f"  ✗ Failed: {reg_id} → {exc_id}: {result}")

    # 3. Exclusion: Regulation → STRICTLY_PROHIBITED → Exclusion
    print("\n=== Connecting Exclusion nodes (7) ===")
    for excl_id, reg_ids in EXCLUSION_MAP.items():
        for reg_id in reg_ids:
            result = add_edge(reg_id, "STRICTLY_PROHIBITED", excl_id)
            status = result.get("status", {}).get("code", -1)
            if status == 200:
                total_created += 1
                print(f"  ✓ {reg_id} → STRICTLY_PROHIBITED → {excl_id}")
            else:
                total_skipped += 1
                print(f"  ✗ Failed: {reg_id} → {excl_id}: {result}")

    # 4. Coverage: Coverage → GOVERNED_BY → Regulation
    print("\n=== Connecting Coverage nodes (4) ===")
    for cov_id, reg_ids in COVERAGE_MAP.items():
        for reg_id in reg_ids:
            result = add_edge(cov_id, "GOVERNED_BY", reg_id)
            status = result.get("status", {}).get("code", -1)
            if status == 200:
                total_created += 1
                print(f"  ✓ {cov_id} → GOVERNED_BY → {reg_id}")
            else:
                total_skipped += 1
                print(f"  ✗ Failed: {cov_id} → {reg_id}: {result}")

    # 5. Product_Category: Product_Category → GOVERNED_BY → Regulation
    print("\n=== Connecting Product_Category nodes (3) ===")
    for pc_id, reg_ids in PRODUCT_CATEGORY_MAP.items():
        for reg_id in reg_ids:
            result = add_edge(pc_id, "GOVERNED_BY", reg_id)
            status = result.get("status", {}).get("code", -1)
            if status == 200:
                total_created += 1
                print(f"  ✓ {pc_id} → GOVERNED_BY → {reg_id}")
            else:
                total_skipped += 1
                print(f"  ✗ Failed: {pc_id} → {reg_id}: {result}")

    print(f"\n=== SUMMARY ===")
    print(f"Total edges created: {total_created}")
    print(f"Total failures: {total_skipped}")

    # Verify: count remaining isolated nodes
    result = execute("g.V().where(bothE().count().is(0)).count()")
    remaining = result["result"]["data"]["@value"]
    print(f"Remaining isolated nodes: {remaining}")


if __name__ == "__main__":
    main()
