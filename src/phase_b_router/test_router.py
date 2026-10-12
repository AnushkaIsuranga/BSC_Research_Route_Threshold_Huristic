import unittest
import unittest.mock
from src.phase_b_router.policy import get_routing_decision

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

if __name__ == "__main__":
    unittest.main()
