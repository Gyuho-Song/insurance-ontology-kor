#!/usr/bin/env python3
"""
Create the 'ontology-vectors' OpenSearch Serverless index with k-NN + Nori mappings.

Usage:
    # Using environment variables (recommended for new environments)
    export OPENSEARCH_ENDPOINT=https://xxx.us-east-1.aoss.amazonaws.com
    export AWS_REGION=us-east-1
    python3 scripts/create_opensearch_index.py

    # Using CLI args
    python3 scripts/create_opensearch_index.py \
        --endpoint https://xxx.us-east-1.aoss.amazonaws.com \
        --region us-east-1

    # Delete and recreate
    python3 scripts/create_opensearch_index.py --recreate
"""
import argparse
import json
import os
import sys

import boto3
import requests
from requests_aws4auth import AWS4Auth

INDEX_NAME = "ontology-vectors"

INDEX_BODY = {
    "settings": {
        "index": {
            "knn": True,
            "knn.algo_param.ef_search": 512,
        }
    },
    "mappings": {
        "properties": {
            "entity_id": {"type": "keyword"},
            "node_type": {"type": "keyword"},
            "node_label": {
                "type": "text",
                "analyzer": "nori",
                "fields": {
                    "raw": {"type": "keyword"}
                },
            },
            "text_content": {"type": "text", "analyzer": "nori"},
            "product_name": {"type": "keyword"},
            "document_id": {"type": "keyword"},
            "embedding": {
                "type": "knn_vector",
                "dimension": 1024,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "nmslib",
                    "parameters": {
                        "ef_construction": 512,
                        "m": 16,
                    },
                },
            },
        }
    },
}


def main():
    parser = argparse.ArgumentParser(description="Create OpenSearch ontology-vectors index")
    parser.add_argument("--endpoint", type=str,
                        default=os.environ.get("OPENSEARCH_ENDPOINT",
                                               "https://svwxdwdbvvoryvl1l1k5.us-west-2.aoss.amazonaws.com"),
                        help="OpenSearch Serverless endpoint URL")
    parser.add_argument("--region", type=str,
                        default=os.environ.get("AWS_REGION", "us-west-2"),
                        help="AWS region")
    parser.add_argument("--recreate", action="store_true",
                        help="Delete existing index and recreate")
    args = parser.parse_args()

    endpoint = args.endpoint.rstrip("/")
    region = args.region

    # Auth
    session = boto3.Session(region_name=region)
    credentials = session.get_credentials().get_frozen_credentials()
    auth = AWS4Auth(credentials.access_key, credentials.secret_key, region, "aoss",
                    session_token=credentials.token)

    def request(method, path, body=None):
        url = f"{endpoint}/{path}"
        headers = {"Content-Type": "application/json"}
        resp = requests.request(method, url, json=body, headers=headers, auth=auth, timeout=30)
        return resp

    # Check if index exists
    print(f"Endpoint: {endpoint}")
    print(f"Region:   {region}")
    print(f"Index:    {INDEX_NAME}")
    print()

    resp = request("HEAD", INDEX_NAME)
    index_exists = resp.status_code == 200

    if index_exists and not args.recreate:
        print(f"Index '{INDEX_NAME}' already exists. Use --recreate to delete and recreate.")
        # Show current mapping
        resp = request("GET", f"{INDEX_NAME}/_mapping")
        if resp.status_code == 200:
            print(f"\nCurrent mapping:")
            print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
        sys.exit(0)

    if index_exists and args.recreate:
        print(f"Deleting existing index '{INDEX_NAME}'...")
        resp = request("DELETE", INDEX_NAME)
        if resp.status_code >= 400:
            print(f"  DELETE failed: {resp.status_code} {resp.text[:200]}")
            sys.exit(1)
        print("  Deleted.")

    # Create index
    print(f"Creating index '{INDEX_NAME}' with k-NN + Nori mappings...")
    resp = request("PUT", INDEX_NAME, INDEX_BODY)
    if resp.status_code >= 400:
        print(f"  CREATE failed: {resp.status_code} {resp.text[:300]}")
        sys.exit(1)

    print(f"  Created successfully!")
    print(f"\nIndex settings:")
    print(f"  - k-NN: enabled (HNSW, nmslib, cosinesimil)")
    print(f"  - Embedding dimension: 1536 (Bedrock Titan v2)")
    print(f"  - Text analyzer: Nori (Korean morphological)")
    print(f"  - node_label.raw: keyword (exact match/wildcard)")
    print(f"  - ef_construction: 512, m: 16")


if __name__ == "__main__":
    main()
