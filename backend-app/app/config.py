from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Neptune
    neptune_endpoint: str = "localhost"
    neptune_port: int = 8182

    # OpenSearch
    opensearch_endpoint: str = "localhost"
    opensearch_index: str = "ontology-vectors"

    # Bedrock
    bedrock_region: str = "us-west-2"
    bedrock_sonnet_model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    bedrock_haiku_model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"

    # S3
    mock_cache_bucket: str = "ontology-demo-mock-cache-767884848530"
    parsed_bucket: str = "ontology-demo-parsed-data-767884848530"

    # Performance tuning
    vector_search_top_k: int = 5
    vector_search_threshold: float = 0.5
    max_traversal_depth: int = 4
    topo_faithfulness_threshold: float = 0.85
    validation_timeout: float = 4.0
    embedding_cache_size: int = 256
    neptune_pool_size: int = 16
    neptune_max_workers: int = 16

    # Logging
    log_level: str = "INFO"

    model_config = {"env_prefix": ""}


settings = Settings()
