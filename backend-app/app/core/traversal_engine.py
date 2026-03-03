import logging

from app.models.template import TemplateExecution
from app.models.traversal import ConstraintResult, TraversalPath, TraversalResult

logger = logging.getLogger("graphrag.traversal")

CONSTRAINT_EDGES = {"STRICTLY_PROHIBITED", "EXCEPTIONALLY_ALLOWED"}
EDGE_STYLE_MAP = {
    "STRICTLY_PROHIBITED": "red_blocked",
    "EXCEPTIONALLY_ALLOWED": "green_opened",
    "EXCLUDED_IF": "orange_warning",
    "EXCEPTION_ALLOWED": "blue_exception",
    "CALCULATED_BY": "purple_formula",
    "WAIVES_PREMIUM": "green_opened",
    "OWNS": "default",
}
DELAY_MAP = {
    "node_activated": 200,
    "edge_traversed": 300,
    "constraint_blocked": 500,
    "constraint_opened": 400,
    "merge_node_added": 350,
    "traversal_complete": 200,
}

_NODE_META_KEYS = {"T.id", "T.label", "label", "id"}
_EDGE_META_KEYS = {"T.id", "T.label", "label", "id", "IN", "OUT"}


def _extract_properties(obj: dict, meta_keys: set) -> dict:
    return {k: v for k, v in obj.items() if k not in meta_keys}


class TraversalEngine:
    def __init__(self, neptune):
        self._neptune = neptune

    async def traverse(self, executions: list[TemplateExecution]) -> TraversalResult:
        all_nodes = {}
        all_edges = []
        events = []
        paths = []
        constraints_found = 0
        total_hops = 0
        current_delay = 0

        for execution in executions:
            try:
                raw_results = await self._neptune.execute(execution.gremlin_query)
            except Exception as e:
                logger.error(f"Gremlin execution failed: {e}")
                raw_results = []

            for path_data in raw_results:
                objects = path_data.get("objects", [])
                path_nodes = []
                path_edges = []
                path_constraints = []
                hop = 0

                for i, obj in enumerate(objects):
                    node_id = obj.get("T.id", obj.get("id", f"unknown_{i}"))
                    node_label_raw = obj.get("T.label", obj.get("label", "Unknown"))
                    node_label = node_label_raw
                    display_label = ""

                    label_val = obj.get("label")
                    if isinstance(label_val, list):
                        display_label = label_val[0] if label_val else ""
                    elif isinstance(label_val, str):
                        display_label = label_val

                    # Determine if this is a node or edge based on known edge patterns
                    is_edge = node_label_raw in (
                        "HAS_COVERAGE", "EXCLUDED_IF", "EXCEPTION_ALLOWED",
                        "NO_DIVIDEND_STRUCTURE", "GOVERNED_BY", "SURRENDER_PAYS",
                        "HAS_DISCOUNT", "STRICTLY_PROHIBITED", "EXCEPTIONALLY_ALLOWED",
                        "REQUIRES_ELIGIBILITY", "HAS_RIDER", "HAS_LOAN",
                        "WAIVES_PREMIUM", "CALCULATED_BY", "OWNS",
                    )

                    if is_edge:
                        edge_type = node_label_raw
                        edge_style = EDGE_STYLE_MAP.get(edge_type, "default")

                        # Check constraints
                        if edge_type in CONSTRAINT_EDGES:
                            constraints_found += 1
                            blocked = edge_type == "STRICTLY_PROHIBITED"
                            path_constraints.append(
                                ConstraintResult(
                                    edge_type=edge_type,
                                    blocked=blocked,
                                    reason=display_label if blocked else None,
                                    regulation_id=None,
                                    condition_met=not blocked if not blocked else None,
                                )
                            )
                            event_type = (
                                "constraint_blocked" if blocked else "constraint_opened"
                            )
                            events.append(
                                {
                                    "type": event_type,
                                    "hop": hop,
                                    "delay_ms": current_delay,
                                    "data": {
                                        "edge_type": edge_type,
                                        "edge_style": edge_style,
                                        "blocked_reason": display_label if blocked else None,
                                    },
                                }
                            )
                            current_delay += DELAY_MAP[event_type]
                        else:
                            # Edge traversed event
                            events.append(
                                {
                                    "type": "edge_traversed",
                                    "hop": hop,
                                    "delay_ms": current_delay,
                                    "data": {
                                        "edge_type": edge_type,
                                        "edge_style": edge_style,
                                    },
                                }
                            )
                            current_delay += DELAY_MAP["edge_traversed"]

                        if path_nodes:
                            source_id = path_nodes[-1]["id"]
                            path_edges.append(
                                {
                                    "source": source_id,
                                    "target": "pending",
                                    "type": edge_type,
                                    "properties": _extract_properties(obj, _EDGE_META_KEYS),
                                }
                            )
                    else:
                        # Node
                        node_type = node_label_raw
                        node_info = {
                            "id": node_id,
                            "type": node_type,
                            "label": display_label or node_id,
                            "properties": _extract_properties(obj, _NODE_META_KEYS),
                        }
                        path_nodes.append(node_info)

                        if node_id not in all_nodes:
                            all_nodes[node_id] = node_info
                            event_type = "node_activated"
                            events.append(
                                {
                                    "type": event_type,
                                    "hop": hop,
                                    "delay_ms": current_delay,
                                    "data": {
                                        "node_id": node_id,
                                        "node_type": node_type,
                                        "node_label": display_label or node_id,
                                    },
                                }
                            )
                            current_delay += DELAY_MAP["node_activated"]

                        # Fix pending edge targets
                        if path_edges and path_edges[-1]["target"] == "pending":
                            path_edges[-1]["target"] = node_id
                            all_edges.append(path_edges[-1])

                        hop += 1

                total_hops = max(total_hops, hop)
                paths.append(
                    TraversalPath(
                        nodes=path_nodes,
                        edges=path_edges,
                        constraints=path_constraints,
                        depth=hop,
                    )
                )

        # Traversal complete event
        events.append(
            {
                "type": "traversal_complete",
                "hop": total_hops,
                "delay_ms": current_delay,
                "data": {},
            }
        )

        return TraversalResult(
            paths=paths,
            subgraph_nodes=list(all_nodes.values()),
            subgraph_edges=all_edges,
            traversal_events=events,
            total_hops=total_hops,
            constraints_found=constraints_found,
        )
