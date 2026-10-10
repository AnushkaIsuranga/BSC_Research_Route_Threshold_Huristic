import unittest
import unittest.mock
from .router import (
    get_routing_decision,
    build_decision_matrix_graph,
    build_naive_graph,
    MockChatModel,
    NaiveRouteDecision
)

class TestAgenticRouter(unittest.TestCase):
    
    def test_decision_matrix_hysteresis(self):
        # mock thresholds
        thresholds_dict = {
            "hm_clothes_100": {
                "recall_danger_zones": [(0.4705, 1.0)],
                "latency_danger_zones": [(0.2037, 0.2037)],
                "margin": 0.01
            }
        }
        
        # low selectivity -> safe -> pre-filter
        self.assertEqual(get_routing_decision("hm_clothes_100", 0.01, thresholds_dict), "pre-filter")
        
        # safely in between danger zones -> pre-filter
        self.assertEqual(get_routing_decision("hm_clothes_100", 0.15, thresholds_dict), "pre-filter")
        
        # exactly on latency danger -> post-filter
        self.assertEqual(get_routing_decision("hm_clothes_100", 0.2037, thresholds_dict), "post-filter")
        
        # exactly on the lower margin boundary of latency danger (0.2037 - 0.01 = 0.1937) -> post-filter
        self.assertEqual(get_routing_decision("hm_clothes_100", 0.1937, thresholds_dict), "post-filter")

        # inside the lower margin (0.2037 - 0.009 = 0.1947) -> post-filter
        self.assertEqual(get_routing_decision("hm_clothes_100", 0.1947, thresholds_dict), "post-filter")

        # outside the lower margin (0.2037 - 0.011 = 0.1927) -> pre-filter
        self.assertEqual(get_routing_decision("hm_clothes_100", 0.1927, thresholds_dict), "pre-filter")
        
        # well above latency danger but below recall collapse margin -> pre-filter
        self.assertEqual(get_routing_decision("hm_clothes_100", 0.30, thresholds_dict), "pre-filter")
        
        # outside margin of recall collapse (0.4705 - 0.011 = 0.4595) -> pre-filter
        self.assertEqual(get_routing_decision("hm_clothes_100", 0.4595, thresholds_dict), "pre-filter")

        # exactly on margin of recall collapse (0.4705 - 0.01 = 0.4605) -> post-filter
        self.assertEqual(get_routing_decision("hm_clothes_100", 0.4605, thresholds_dict), "post-filter")

        # inside margin of recall collapse (0.4705 - 0.005) -> post-filter
        self.assertEqual(get_routing_decision("hm_clothes_100", 0.4655, thresholds_dict), "post-filter")
        
        # above recall collapse -> post-filter
        self.assertEqual(get_routing_decision("hm_clothes_100", 0.50, thresholds_dict), "post-filter")
        
    def test_safe_table_routes_pre_filter(self):
        # A table that was profiled but had no danger zones (all nulls)
        thresholds_dict = {
            "hm_clothes_50": {
                "recall_danger_zones": [],
                "latency_danger_zones": []
            }
        }
        # Extremely high selectivity (normally recall collapse territory)
        self.assertEqual(get_routing_decision("hm_clothes_50", 0.99, thresholds_dict), "pre-filter")
        # Danger zone selectivity
        self.assertEqual(get_routing_decision("hm_clothes_50", 0.2037, thresholds_dict), "pre-filter")

    def test_missing_thresholds_raises_error(self):
        thresholds_dict = {}
        with self.assertRaises(ValueError):
            get_routing_decision("hm_clothes_missing", 0.10, thresholds_dict)

    @unittest.mock.patch("src.phase_b_router.router.execute_vector_search")
    def test_langgraph_decision_matrix(self, mock_exec):
        mock_exec.side_effect = lambda state, route: f"{route} executed"
        thresholds_dict = {
            "hm_clothes_100": {
                "recall_danger_zones": [(0.4705, 1.0)],
                "latency_danger_zones": [(0.2037, 0.2037)]
            }
        }
        graph = build_decision_matrix_graph(thresholds_dict)
        
        # Should route to pre-filter (safe)
        state1 = {
            "question": "test1",
            "estimated_selectivity": 0.10,
            "correlation_level": "hm_clothes_100",
            "chosen_route": "",
            "final_answer": "",
            "sub_queries": []
        }
        res1 = graph.invoke(state1)
        self.assertEqual(res1["chosen_route"], "pre-filter")
        self.assertEqual(res1["final_answer"], "pre-filter executed")
        
        # Should route to post-filter (due to latency danger zone)
        state2 = {
            "question": "test2",
            "estimated_selectivity": 0.2037,
            "correlation_level": "hm_clothes_100",
            "chosen_route": "",
            "final_answer": "",
            "sub_queries": []
        }
        res2 = graph.invoke(state2)
        self.assertEqual(res2["chosen_route"], "post-filter")
        self.assertEqual(res2["final_answer"], "post-filter executed")

    @unittest.mock.patch("src.phase_b_router.router.execute_vector_search")
    def test_naive_router_multi_query(self, mock_exec):
        mock_exec.side_effect = lambda state, route: f"{route} executed"
        # Mock LLM returning pre-filter and 2 sub-queries (Item 10)
        mock_llm = MockChatModel(
            NaiveRouteDecision(
                route="pre-filter", 
                sub_queries=["What is the color?", "What is the size?"]
            )
        )
        
        graph = build_naive_graph(mock_llm)
        state = {
            "question": "What is the color and size of this shirt?",
            "estimated_selectivity": 0.0,
            "correlation_level": "",
            "chosen_route": "",
            "final_answer": "",
            "sub_queries": []
        }
        
        res = graph.invoke(state)
        self.assertEqual(res["chosen_route"], "pre-filter")
        self.assertEqual(res["final_answer"], "pre-filter executed")
        self.assertEqual(len(res["sub_queries"]), 2)
        self.assertEqual(res["sub_queries"][0], "What is the color?")

    @unittest.mock.patch.dict("os.environ", {}, clear=True)
    @unittest.mock.patch("src.phase_b_router.router.psycopg2")
    @unittest.mock.patch("src.phase_b_router.router.get_embedding_client")
    def test_missing_ai_env_vars(self, mock_get_emb, mock_psycopg):
        from .router import execute_vector_search
        
        mock_emb = unittest.mock.Mock()
        mock_emb.embed_query.return_value = [0.0] * 768
        mock_get_emb.return_value = mock_emb
        
        mock_cursor = mock_psycopg.connect.return_value.cursor.return_value.__enter__.return_value
        mock_cursor.fetchall.return_value = []
        
        with self.assertRaises(RuntimeError) as ctx:
            execute_vector_search({"question": "test", "chosen_route": "pre-filter", "final_answer": "", "sub_queries": [], "ticker": "A", "year": "2020"}, "pre-filter")
        self.assertIn("must be configured", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
