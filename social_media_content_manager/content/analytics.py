import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from django.core.cache import cache

class AnalyticsService:
    
    @staticmethod
    def track_content(content_id: str, user_id: str, platform: str, content_type: str, text: str):
        """Track generated content in cache"""
        analytics_key = f"analytics:content:{content_id}"
        
        analytics_data = {
            'content_id': content_id,
            'user_id': user_id,
            'platform': platform,
            'content_type': content_type,
            'generated_text': text[:500],
            'impressions': 0,
            'likes': 0,
            'comments': 0,
            'shares': 0,
            'saves': 0,
            'clicks': 0,
            'engagement_rate': 0.0,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        # Store for 90 days
        cache.set(analytics_key, analytics_data, 90 * 24 * 3600)
        
        # Add to user's content list
        user_contents_key = f"analytics:user:{user_id}:contents"
        user_contents = cache.get(user_contents_key, [])
        user_contents.append(content_id)
        cache.set(user_contents_key, user_contents, 90 * 24 * 3600)
        
        # Add to platform list
        platform_contents_key = f"analytics:platform:{platform}:contents"
        platform_contents = cache.get(platform_contents_key, [])
        platform_contents.append(content_id)
        cache.set(platform_contents_key, platform_contents, 90 * 24 * 3600)
    
    @staticmethod
    def update_metrics(content_id: str, metrics: Dict[str, int]) -> bool:
        """Update engagement metrics for a piece of content"""
        analytics_key = f"analytics:content:{content_id}"
        analytic = cache.get(analytics_key)
        
        if not analytic:
            return False
        
        # Update metrics
        for key, value in metrics.items():
            if key in analytic:
                analytic[key] = value
        
        # Calculate engagement rate
        if analytic.get('impressions', 0) > 0:
            total_engagement = analytic.get('likes', 0) + analytic.get('comments', 0) + \
                             analytic.get('shares', 0) + analytic.get('saves', 0)
            analytic['engagement_rate'] = (total_engagement / analytic['impressions']) * 100
        
        analytic['updated_at'] = datetime.now().isoformat()
        
        # Save back to cache
        cache.set(analytics_key, analytic, 90 * 24 * 3600)
        
        # Update platform insights
        AnalyticsService._update_platform_insights(analytic['platform'])
        
        return True
    
    @staticmethod
    def _update_platform_insights(platform: str):
        """Recalculate platform insights from cache"""
        platform_contents_key = f"analytics:platform:{platform}:contents"
        content_ids = cache.get(platform_contents_key, [])
        
        if not content_ids:
            return
        
        # Get last 30 days of data
        thirty_days_ago = datetime.now() - timedelta(days=30)
        recent_analytics = []
        
        for content_id in content_ids:
            analytic = cache.get(f"analytics:content:{content_id}")
            if analytic:
                created_at = datetime.fromisoformat(analytic['created_at'])
                if created_at >= thirty_days_ago:
                    recent_analytics.append(analytic)
        
        if not recent_analytics:
            return
        
        # Calculate average engagement rate
        avg_rate = sum(a.get('engagement_rate', 0) for a in recent_analytics) / len(recent_analytics)
        
        # Analyze best performing hashtags
        all_hashtags = []
        for analytic in recent_analytics:
            hashtags = re.findall(r'#\w+', analytic.get('generated_text', ''))
            all_hashtags.extend(hashtags)
        
        top_hashtags = [h for h, c in Counter(all_hashtags).most_common(10)]
        
        # Extract top keywords
        all_words = []
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being'}
        
        for analytic in recent_analytics:
            words = analytic.get('generated_text', '').lower().split()
            meaningful = [w for w in words if w not in stop_words and len(w) > 3 and not w.startswith('#')]
            all_words.extend(meaningful)
        
        top_keywords = [w for w, c in Counter(all_words).most_common(10)]
        
        # Find best performing time
        hour_performance = {}
        for analytic in recent_analytics:
            created_at = datetime.fromisoformat(analytic['created_at'])
            hour = created_at.hour
            engagement = analytic.get('engagement_rate', 0)
            if hour not in hour_performance:
                hour_performance[hour] = []
            hour_performance[hour].append(engagement)
        
        avg_by_hour = {h: sum(v)/len(v) for h, v in hour_performance.items()}
        best_hour = max(avg_by_hour, key=avg_by_hour.get) if avg_by_hour else 12
        best_time = f"{best_hour:02d}:00"
        
        # Find best performing day
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_performance = {day: [] for day in days}
        
        for analytic in recent_analytics:
            created_at = datetime.fromisoformat(analytic['created_at'])
            day_name = days[created_at.weekday()]
            day_performance[day_name].append(analytic.get('engagement_rate', 0))
        
        avg_by_day = {day: sum(v)/len(v) if v else 0 for day, v in day_performance.items()}
        best_day = max(avg_by_day, key=avg_by_day.get)
        
        # Save platform insights
        insights = {
            'platform': platform,
            'avg_engagement_rate': avg_rate,
            'best_performing_time': best_time,
            'best_performing_day': best_day,
            'top_hashtags': top_hashtags,
            'top_keywords': top_keywords,
            'updated_at': datetime.now().isoformat()
        }
        
        cache.set(f"analytics:insights:{platform}", insights, 7 * 24 * 3600)
    
    @staticmethod
    def get_user_dashboard(user_id: str) -> Dict:
        """Get analytics dashboard for a user from cache"""
        user_contents_key = f"analytics:user:{user_id}:contents"
        content_ids = cache.get(user_contents_key, [])
        
        thirty_days_ago = datetime.now() - timedelta(days=30)
        user_content = []
        
        for content_id in content_ids:
            analytic = cache.get(f"analytics:content:{content_id}")
            if analytic:
                created_at = datetime.fromisoformat(analytic['created_at'])
                if created_at >= thirty_days_ago:
                    user_content.append(analytic)
        
        # Platform breakdown
        platform_stats = {}
        platforms = ['youtube', 'instagram', 'facebook', 'linkedin', 'twitter', 'tiktok', 'pinterest']
        
        for platform in platforms:
            platform_content = [c for c in user_content if c['platform'] == platform]
            if platform_content:
                platform_stats[platform] = {
                    'posts': len(platform_content),
                    'avg_engagement': sum(c.get('engagement_rate', 0) for c in platform_content) / len(platform_content),
                    'total_impressions': sum(c.get('impressions', 0) for c in platform_content)
                }
        
        # Best performing content
        best_content = sorted(user_content, key=lambda x: x.get('engagement_rate', 0), reverse=True)[:5]
        best_posts = [{
            'platform': c['platform'],
            'engagement_rate': c.get('engagement_rate', 0),
            'preview': c.get('generated_text', '')[:100],
            'created_at': c.get('created_at')
        } for c in best_content]
        
        return {
            'total_posts': len(user_content),
            'platform_stats': platform_stats,
            'best_posts': best_posts,
            'total_engagement': sum(c.get('likes', 0) for c in user_content),
            'total_reach': sum(c.get('impressions', 0) for c in user_content)
        }
    
    @staticmethod
    def get_platform_insights(platform: str) -> Optional[Dict]:
        """Get insights for a specific platform"""
        return cache.get(f"analytics:insights:{platform}")