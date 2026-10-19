
import re
from datetime import datetime, timezone

class EvidenceGraph:
    """
    Stores investigation evidence as connected nodes and edges.
    """

    def __init__(self):
        self.nodes = []
        self.edges = []

    def add_node(self, node_id: str, node_type: str, data: dict):
        """
        Add a unique evidence node.
        """
        if any(node["id"] == node_id for node in self.nodes):
            raise ValueError(f"Duplicate node ID: {node_id}")

        node = {
            "id": node_id,
            "type": node_type,
            "data": data,
        }

        self.nodes.append(node)
        return node

    def add_edge(self, source: str, target: str, relationship: str):
        """
        Connect two existing evidence nodes.
        """
        node_ids = {node["id"] for node in self.nodes}

        if source not in node_ids or target not in node_ids:
            raise ValueError("Both nodes must exist before adding an edge.")

        edge = {
            "source": source,
            "target": target,
            "relationship": relationship,
        }

        self.edges.append(edge)
        return edge

    def to_dict(self):
        """
        Convert the graph into a JSON-compatible dictionary.
        """
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "nodes": self.nodes,
            "edges": self.edges,
        }


def extract_failed_tests(test_output: str) -> list[str]:
    """
    Extract failed pytest test identifiers from the
    short test summary.
    """
    failed_tests = []

    for line in test_output.splitlines():
        match = re.match(
            r"^FAILED\s+(\S+?)(?:\s+-\s+.*)?$",
            line.strip(),
        )

        if match:
            test_name = match.group(1)

            if test_name not in failed_tests:
                failed_tests.append(test_name)

    return failed_tests

def build_investigation_graph(
    test_result: dict,
    regression_commit: str,
    hypothesis: str,
    reversal_result: dict,
) -> dict:
    """
    Build an evidence graph from a real CausalTrace investigation.
    """

    graph = EvidenceGraph()

    # Node 1: Actual pytest failure
    graph.add_node(
        "test_failure",
        "test_failure",
        {
            "output": test_result["output"],
            "return_code": test_result["return_code"],
        },
    )

    # Node 2: Regression-introducing Git commit
    graph.add_node(
        "regression_commit",
        "git_commit",
        {
            "hash": regression_commit,
        },
    )

    # Node 3: NVIDIA Nemotron's explanation
    graph.add_node(
        "root_cause_hypothesis",
        "ai_hypothesis",
        {
            "model": "nvidia/nemotron-3-super-120b-a12b",
            "explanation": hypothesis,
        },
    )

    # Node 4: Actual reversal experiment
    graph.add_node(
        "reversal_experiment",
        "experiment",
        {
            "verified": reversal_result["verified"],
            "before_return_code": reversal_result.get(
                "before_return_code"
            ),
            "after_return_code": reversal_result.get(
                "after_return_code"
            ),
        },
    )

    # Connect evidence without overstating causality.
    graph.add_edge(
        "test_failure",
        "regression_commit",
        "regression_boundary_associated_with",
    )

    graph.add_edge(
        "regression_commit",
        "root_cause_hypothesis",
        "analyzed_in",
    )

    graph.add_edge(
        "root_cause_hypothesis",
        "reversal_experiment",
        "evaluated_by",
    )

        # Add an evidence node for each failed pytest test.
    failed_tests = test_result.get("failed_ids") or extract_failed_tests(
        test_result.get("output", "")
    )

    for index, test_name in enumerate(failed_tests, start=1):
        node_id = f"failed_test_{index}"

        graph.add_node(
            node_id,
            "failed_test",
            {
                "test_name": test_name,
                "status": "FAILED",
            },
        )

        graph.add_edge(
            node_id,
            "test_failure",
            "contributes_to_failure",
        )

    return graph.to_dict()
