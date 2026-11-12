"""Numerical mechanism checks only: no model, database, or semantic quality claims."""

import unittest

import numpy as np

from evals.community_catalog_poc.demo import diverse_representatives, normalize, rank, route


class RoutingChecks(unittest.TestCase):
    def setUp(self):
        # B's centroid points away from the query, hiding its very relevant Boundary worker.
        self.names = ["Alpha", "Beta", "Boundary", "Delta", "Echo", "Foxtrot", "Golf"]
        self.vectors = normalize([[0.8, 0.6], [0.8, 0.6], [1, 0], [0, 1],
                                  [-0.6, 0.8], [-0.8, 0.6], [-1, 0]])
        self.groups = {"A": [0, 1, 3], "B": [2, 4, 5, 6]}
        self.communities = [{"id": name, "size": len(members),
                             "centroid": normalize(self.vectors[members].mean(axis=0)).tolist()}
                            for name, members in self.groups.items()]
        self.query = np.array([1, 0], dtype=np.float32)

    def fetch(self, identifiers):
        return [{"name": self.names[i], "embedding": self.vectors[i]}
                for identifier in identifiers for i in self.groups[identifier]]

    def test_subset_can_omit_global_neighbor_and_widening_recovers_it(self):
        flat = rank(self.names, self.vectors, self.query)
        narrow = route(self.communities, self.query, 1, self.fetch, len(self.names))
        wide = route(self.communities, self.query, 2, self.fetch, len(self.names))
        self.assertEqual(flat[0]["name"], "Boundary")
        self.assertNotIn("Boundary", [r["name"] for r in narrow["top5"]])
        self.assertEqual(wide["top5"][0]["name"], "Boundary")
        self.assertEqual(narrow["candidate_count"], 3)
        self.assertEqual(narrow["total_explicit_comparisons"], 5)

    def test_all_communities_equal_flat_with_ties_unique_names_and_clamping(self):
        flat = rank(self.names, self.vectors, self.query)
        wide = route(self.communities, self.query, 999, self.fetch, len(self.names))
        self.assertEqual(wide["top5"], flat)
        self.assertEqual([r["name"] for r in flat[1:3]], ["Alpha", "Beta"])
        self.assertEqual(len({r["name"] for r in wide["top5"]}), 5)
        self.assertEqual(wide["candidate_count"], len(self.names))
        self.assertEqual(wide["total_explicit_comparisons"], len(self.names) + len(self.groups))
        self.assertTrue(wide["covers_entire_catalog"])

    def test_diverse_representatives_recover_hidden_neighbor_and_count_all_work(self):
        enriched = []
        for community in self.communities:
            representatives, names, _ = diverse_representatives(community["centroid"], self.fetch([community["id"]]))
            enriched.append({**community, "representatives": representatives, "representative_names": names})
        narrow = route(enriched, self.query, 1, self.fetch, len(self.names))
        self.assertEqual(narrow["selected_communities"][0]["id"], "B")
        self.assertEqual(narrow["top5"][0]["name"], "Boundary")
        self.assertEqual(narrow["representative_comparisons"], 6)
        self.assertEqual(narrow["total_explicit_comparisons"], 6 + len(self.groups["B"]))
        wide = route(enriched, self.query, 999, self.fetch, len(self.names))
        self.assertEqual(wide["top5"], rank(self.names, self.vectors, self.query))

    def test_diverse_selection_is_order_independent_with_ties_and_singletons(self):
        members = [{"name": name, "embedding": [1, 0]} for name in ["Zulu", "Alpha", "Beta"]]
        forward = diverse_representatives([1, 0], members)
        backward = diverse_representatives([1, 0], list(reversed(members)))
        self.assertEqual(forward, backward)
        self.assertEqual(forward[1], [None, "Alpha", "Beta"])
        representatives, names, comparisons = diverse_representatives([1, 0], members[:1])
        self.assertEqual(representatives, [[1, 0], [1, 0]])
        self.assertEqual(names, [None, "Zulu"])
        self.assertEqual(comparisons, 1)


if __name__ == "__main__":
    unittest.main()
