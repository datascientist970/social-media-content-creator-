import json
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from django.core.cache import cache

class ABTestingService:
    
    @staticmethod
    def get_variant(user_id: str, test_name: str = "default_prompt") -> str:
        """Determine which variant a user gets"""
        cache_key = f"ab_test:variant:{test_name}:{user_id}"
        
        # Check cache first
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        # Get active test configuration
        test_config = cache.get(f"ab_test:config:{test_name}")
        if not test_config:
            return 'A'
        
        # Deterministic assignment based on user_id hash
        hash_val = int(hashlib.md5(f"{user_id}:{test_name}".encode()).hexdigest()[:8], 16)
        is_variant_b = (hash_val % 100) < (test_config.get('traffic_split', 0.5) * 100)
        
        variant = 'B' if is_variant_b else 'A'
        
        # Cache for 1 hour
        cache.set(cache_key, variant, 3600)
        
        return variant
    
    @staticmethod
    def get_prompt_for_variant(variant: str, test_name: str = "default_prompt") -> str:
        """Get the prompt for a specific variant"""
        test_config = cache.get(f"ab_test:config:{test_name}")
        if not test_config:
            return None
        
        return test_config.get(f'variant_{variant.lower()}_prompt')
    
    @staticmethod
    def record_result(test_name: str, variant: str, user_id: str, content_type: str, generated_content: Dict):
        """Record A/B test result in cache"""
        result_key = f"ab_test:result:{test_name}:{user_id}:{int(time.time())}"
        
        result_data = {
            'test_name': test_name,
            'variant': variant,
            'user_id': user_id,
            'content_type': content_type,
            'generated_content': generated_content,
            'timestamp': datetime.now().isoformat(),
            'engagement_score': None  # Will be updated later
        }
        
        # Store for 30 days
        cache.set(result_key, result_data, 30 * 24 * 3600)
        
        # Add to test results list
        results_list_key = f"ab_test:results:{test_name}"
        results_list = cache.get(results_list_key, [])
        results_list.append(result_key)
        cache.set(results_list_key, results_list, 30 * 24 * 3600)
    
    @staticmethod
    def create_test(name: str, description: str, variant_a_prompt: str, variant_b_prompt: str, traffic_split: float = 0.5):
        """Create a new A/B test in cache"""
        test_config = {
            'name': name,
            'description': description,
            'variant_a_prompt': variant_a_prompt,
            'variant_b_prompt': variant_b_prompt,
            'traffic_split': traffic_split,
            'is_active': True,
            'created_at': datetime.now().isoformat()
        }
        
        cache.set(f"ab_test:config:{name}", test_config, 7 * 24 * 3600)  # Store for 7 days
        return True
    
    @staticmethod
    def get_test_results(test_name: str) -> Dict:
        """Get results for a specific test from cache"""
        test_config = cache.get(f"ab_test:config:{test_name}")
        if not test_config:
            return {"error": "Test not found"}
        
        results_list_key = f"ab_test:results:{test_name}"
        result_keys = cache.get(results_list_key, [])
        
        variant_a_results = []
        variant_b_results = []
        
        for key in result_keys:
            result = cache.get(key)
            if result:
                if result['variant'] == 'A':
                    variant_a_results.append(result)
                else:
                    variant_b_results.append(result)
        
        # Calculate average engagement scores
        a_scores = [r.get('engagement_score', 0) for r in variant_a_results if r.get('engagement_score')]
        b_scores = [r.get('engagement_score', 0) for r in variant_b_results if r.get('engagement_score')]
        
        avg_a = sum(a_scores) / len(a_scores) if a_scores else 0
        avg_b = sum(b_scores) / len(b_scores) if b_scores else 0
        
        return {
            "test_name": test_name,
            "variant_a": {
                "samples": len(variant_a_results),
                "avg_engagement": avg_a,
                "with_engagement": len(a_scores)
            },
            "variant_b": {
                "samples": len(variant_b_results),
                "avg_engagement": avg_b,
                "with_engagement": len(b_scores)
            },
            "winning_variant": "B" if avg_b > avg_a else "A" if avg_a > avg_b else "Tie"
        }
    
    @staticmethod
    def update_engagement_score(test_name: str, user_id: str, score: float):
        """Update engagement score for a user's test result"""
        # Find the most recent result for this user
        results_list_key = f"ab_test:results:{test_name}"
        result_keys = cache.get(results_list_key, [])
        
        for key in reversed(result_keys):  # Check most recent first
            result = cache.get(key)
            if result and result['user_id'] == user_id and result.get('engagement_score') is None:
                result['engagement_score'] = score
                cache.set(key, result, 30 * 24 * 3600)
                break