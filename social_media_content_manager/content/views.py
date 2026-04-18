import json
import logging
import uuid
import re
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render, redirect
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .services import (
    JobService,
    MediaProcessor,
    RateLimiter,
    RequestContext,
    ServiceError,
    ValidationError,
    get_content_engine,
)

logger = logging.getLogger(__name__)

# Try to import analytics modules
try:
    from .ab_testing import ABTestingService
    from .analytics import AnalyticsService
    HAS_ANALYTICS = True
except ImportError:
    HAS_ANALYTICS = False
    # Create placeholder classes if files don't exist yet
    class ABTestingService:
        @staticmethod
        def get_variant(user_id, test_name): return 'A'
        @staticmethod
        def get_prompt_for_variant(variant, test_name): return None
        @staticmethod
        def record_result(test_name, variant, user_id, content_type, generated_content): pass
        @staticmethod
        def get_test_results(test_name): return {"error": "Not implemented"}
        @staticmethod
        def create_test(name, description, variant_a_prompt, variant_b_prompt, traffic_split): return True
    
    class AnalyticsService:
        @staticmethod
        def track_content(content_id, user_id, platform, content_type, text): pass
        @staticmethod
        def update_metrics(content_id, metrics): return True
        @staticmethod
        def get_user_dashboard(user_id): return {"total_posts": 0, "platform_stats": {}, "best_posts": [], "total_engagement": 0, "total_reach": 0}


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def _get_user_id(request: HttpRequest) -> str:
    """Get or create user ID for tracking"""
    try:
        if request.user.is_authenticated:
            return str(request.user.id)
    except:
        pass
    
    # Use session or create one
    if not request.session.session_key:
        request.session.create()
    
    return f"anon_{request.session.session_key}"



def _format_result_for_template(result: dict, description: str) -> dict:
    """Format the engine result - NO WATERMARK, consistent child"""
    
    youtube_data = result.get('youtube', {})
    instagram_data = result.get('instagram', {})
    tiktok_data = result.get('tiktok', {})
    twitter_data = result.get('twitter', {})
    linkedin_data = result.get('linkedin', {})
    pinterest_data = result.get('pinterest', {})
    facebook_data = result.get('facebook', {})
    
    # YouTube - ensure no emoji in titles
    youtube_title = youtube_data.get('title', description[:70])
    youtube_title = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', '', youtube_title)
    
    youtube_description = youtube_data.get('description', f"{description}")
    youtube_tags = youtube_data.get('tags', 'financial literacy, kids savings, parenting')
    
    # Instagram
    instagram_caption = instagram_data.get('caption', f"{description}")
    instagram_hashtags = instagram_data.get('hashtags', '#consciousparenting #kidsandmoney')
    
    # Clean Instagram hashtags
    if isinstance(instagram_hashtags, str):
        instagram_hashtags = re.sub(r'#\s+', '#', instagram_hashtags)
        instagram_hashtags = re.sub(r'\s+', ' ', instagram_hashtags)
    
    # TikTok
    tiktok_caption = tiktok_data.get('caption', description[:100])
    tiktok_hashtags = tiktok_data.get('hashtags', '#moneytok #parentsoftiktok')
    
    # Twitter - fix truncation
    twitter_tweet = twitter_data.get('tweet', description[:200])
    if twitter_tweet.endswith('...') or twitter_tweet.endswith('…'):
        # Remove incomplete truncation
        twitter_tweet = twitter_tweet.replace('…', '').replace('...', '').strip()
        # Add period if needed
        if not twitter_tweet.endswith(('.', '!', '?')):
            twitter_tweet += '.'
    twitter_hashtags = twitter_data.get('hashtags', '#parenting #financialliteracy')
    
    # LinkedIn - remove duplicate hashtags and casual language
    linkedin_post = linkedin_data.get('post', description)
    # Remove casual language
    linkedin_post = re.sub(r'\b(tbh|ngl|lol|omg|honestly|real talk)\b', '', linkedin_post, flags=re.IGNORECASE)
    # Clean up extra spaces
    linkedin_post = re.sub(r'\s+', ' ', linkedin_post).strip()
    
    linkedin_hashtags = linkedin_data.get('hashtags', '#FinancialLiteracy #ChildDevelopment')
    # Fix double hashtags
    linkedin_hashtags = re.sub(r'##+', '#', linkedin_hashtags)
    
    # Facebook
    facebook_post = facebook_data.get('post', instagram_caption)
    facebook_hashtags = facebook_data.get('hashtags', instagram_hashtags.replace(' ', ', '))
    
    # Pinterest
    pinterest_title = pinterest_data.get('title', youtube_title)
    pinterest_description = pinterest_data.get('description', youtube_description)
    pinterest_hashtags = pinterest_data.get('hashtags', '')
    
    return {
        'youtube': {
            'title': youtube_title,
            'description': youtube_description,
            'tags': youtube_tags
        },
        'instagram': {
            'caption': instagram_caption,
            'hashtags': instagram_hashtags
        },
        'facebook': {
            'post': facebook_post,
            'hashtags': facebook_hashtags
        },
        'linkedin': {
            'post': linkedin_post,
            'hashtags': linkedin_hashtags
        },
        'twitter': {
            'tweet': twitter_tweet,
            'hashtags': twitter_hashtags
        },
        'tiktok': {
            'caption': tiktok_caption,
            'hashtags': tiktok_hashtags
        },
        'pinterest': {
            'title': pinterest_title,
            'description': pinterest_description,
            'hashtags': pinterest_hashtags
        }
    }


# =========================================================
# UI VIEWS
# =========================================================

def home(request: HttpRequest):
    """Homepage with content generation form"""
    return render(request, "content/home.html")


def result(request: HttpRequest):
    """Display results from session"""
    result_data = request.session.get('result')
    
    # Also check for content_id in URL params
    content_id = request.GET.get('content_id')
    
    if not result_data and content_id:
        # Try to get from cache if needed
        from django.core.cache import cache
        cached_result = cache.get(f'content_result_{content_id}')
        if cached_result:
            result_data = cached_result
    
    if not result_data:
        messages.error(request, 'No results found. Please generate content first.')
        return redirect('home')
    
    return render(request, "content/result.html", {
        'description': result_data.get('description', ''),
        'social': result_data.get('social', {}),
        'content_id': result_data.get('content_id', content_id)
    })


# =========================================================
# HEALTH CHECK
# =========================================================

def api_status(request: HttpRequest):
    """Simple health check for frontend polling"""
    try:
        return JsonResponse({
            "success": True,
            "status": "online",
            "service": "gemini",
            "time": now().isoformat(),
            "async_available": JobService.is_available()
        })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "status": "offline",
            "error": str(e)
        }, status=500)


# =========================================================
# CORE PROCESS ENDPOINT (FRONTEND USES THIS)
# =========================================================

@csrf_exempt
@require_http_methods(["POST"])
def process(request: HttpRequest):
    """
    Main entry point used by frontend.
    Handles text, image, video and redirects to result page.
    """

    user_id = _get_user_id(request)
    context = RequestContext(user_id=user_id)

    try:
        content_type = request.POST.get("content_type", "text")
        text = request.POST.get("text_content", "").strip()
        image = request.FILES.get("image")
        video = request.FILES.get("video")
        
        # Get optional description for media files (CRITICAL for video/image)
        media_description = request.POST.get("media_description", "").strip()

        # =====================================================
        # RATE LIMIT
        # =====================================================
        allowed, rl_meta = RateLimiter.check_and_increment(
            user_id=user_id,
            limit=int(getattr(settings, "AI_RATE_LIMIT", 20)),
            window_seconds=int(getattr(settings, "AI_RATE_WINDOW_SECONDS", 3600))
        )

        if not allowed:
            messages.error(request, f"Rate limit exceeded. Please wait {rl_meta.get('retry_after', 60)} seconds.")
            return redirect('home')

        engine = get_content_engine()
        result = None
        description = ""

        # =====================================================
        # TEXT
        # =====================================================
        if content_type == "text":
            if not text:
                messages.error(request, "Text content is required")
                return redirect('home')

            result = engine.generate_from_text(text=text, context=context)
            description = text[:300]

        # =====================================================
        # IMAGE
        # =====================================================
        elif content_type == "image":
            if image:
                image_path = MediaProcessor.save_uploaded_file(image, prefix="image")
                
                # Pass user description as user_text option
                options = {}
                if media_description:
                    options["user_text"] = media_description
                    context.log("info", "using_image_description", description=media_description[:100])
                
                result = engine.generate_from_image(
                    image_path=image_path, 
                    context=context, 
                    options=options
                )
                
                description = f"Image: {image.name}"
                if media_description:
                    description += f" - {media_description[:100]}"
                
                MediaProcessor.cleanup_file(image_path)
            else:
                if not text:
                    messages.error(request, "Image or description required")
                    return redirect('home')
                result = engine.generate_from_text(text=text, context=context)
                description = text[:300]

        # =====================================================
        # VIDEO
        # =====================================================
        elif content_type == "video":
            if not video:
                messages.error(request, "Video file required")
                return redirect('home')

            video_path = MediaProcessor.save_uploaded_file(video, prefix="video")
            
            # Pass user description as user_text option (CRITICAL for good results)
            options = {}
            if media_description:
                options["user_text"] = media_description
                context.log("info", "using_video_description", description=media_description[:100])
            
            result = engine.generate_from_video(
                video_path=video_path, 
                context=context, 
                options=options
            )
            
            description = f"Video: {video.name}"
            if media_description:
                description += f" - {media_description[:100]}"
            
            MediaProcessor.cleanup_file(video_path)

        else:
            messages.error(request, "Invalid content type")
            return redirect('home')

        # =====================================================
        # STORE IN SESSION AND REDIRECT TO RESULT PAGE
        # =====================================================
        if result:
            # Format result for template
            formatted_result = _format_result_for_template(result, description)
            
            # Generate a content ID for analytics
            import uuid
            content_id = str(uuid.uuid4())
            
            # Store in session
            request.session['result'] = {
                'description': description,
                'social': formatted_result,
                'content_id': content_id
            }
            
            # Track the content for analytics
            try:
                from .analytics import AnalyticsService
                for platform, platform_data in formatted_result.items():
                    text_content = str(platform_data.get('description' if platform == 'youtube' else 
                                                      'post' if platform == 'facebook' else 
                                                      'caption' if platform in ['instagram', 'tiktok'] else 
                                                      'tweet' if platform == 'twitter' else 
                                                      'title', ''))
                    AnalyticsService.track_content(
                        content_id=f"{content_id}_{platform}",
                        user_id=user_id,
                        platform=platform,
                        content_type=content_type,
                        text=text_content
                    )
            except ImportError:
                pass  # Analytics not installed
            
            # Redirect to the result page
            return redirect('result')
        else:
            messages.error(request, "Failed to generate content. Please try again.")
            return redirect('home')

    except ServiceError as e:
        messages.error(request, e.message)
        return redirect('home')
    except Exception as e:
        logger.exception("Process error")
        messages.error(request, f"Error: {str(e)}")
        return redirect('home')

# =========================================================
# OPTIONAL: DIRECT API GENERATE (ASYNC / CELERY READY)
# =========================================================

@csrf_exempt
@require_http_methods(["POST"])
def api_generate(request: HttpRequest):
    """Advanced endpoint for async jobs (returns JSON, no redirect)"""
    try:
        payload = json.loads(request.body.decode("utf-8"))
        content_type = payload.get("content_type", "text")
        text = payload.get("text", "")

        user_id = _get_user_id(request)
        context = RequestContext(user_id=user_id)
        
        engine = get_content_engine()

        if content_type == "text":
            result = engine.generate_from_text(text=text, context=context)
        else:
            result = engine.generate_from_text(text=text, context=context)

        return JsonResponse({
            "success": True,
            "mode": "sync",
            "result": result
        })

    except Exception as e:
        logger.exception("API generate error")
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


# =========================================================
# ASYNC JOB ENDPOINTS (if using Celery)
# =========================================================

@csrf_exempt
@require_http_methods(["POST"])
def submit_job(request: HttpRequest):
    """Submit async job and return job_id"""
    try:
        user_id = _get_user_id(request)
        content_type = request.POST.get("content_type", "text")
        text = request.POST.get("text_content", "").strip()
        
        payload = {
            "user_id": user_id,
            "content_type": content_type,
            "text": text,
        }
        
        job_id = JobService.enqueue(payload)
        
        return JsonResponse({
            "success": True,
            "job_id": job_id,
            "status_url": f"/api/job/{job_id}/status"
        })
        
    except Exception as e:
        logger.exception("Submit job error")
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_job_status(request: HttpRequest, job_id: str):
    """Get job status and result"""
    job = JobService.get(job_id)
    
    if not job:
        return JsonResponse({
            "success": False,
            "error": "Job not found"
        }, status=404)
    
    return JsonResponse({
        "success": True,
        "job_id": job_id,
        "status": job.get("status"),
        "result": job.get("result"),
        "error": job.get("error"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at")
    })


def api_job_result(request: HttpRequest):
    """API endpoint for job results - redirect to result page if content exists"""
    result_data = request.session.get('result')
    
    if result_data:
        # Redirect to the result page with the content_id
        content_id = result_data.get('content_id', '')
        return redirect(f'/result/?content_id={content_id}')
    else:
        # No result found, redirect to home
        return redirect('home')


# ============================================================
# A/B TESTING AND ANALYTICS VIEWS
# ============================================================

@csrf_exempt
@require_http_methods(["POST"])
def api_generate_with_ab_test(request: HttpRequest):
    """Generate content with A/B testing"""
    try:
        data = json.loads(request.body.decode("utf-8"))
        user_id = data.get("user_id") or _get_user_id(request)
        content_type = data.get("content_type", "text")
        text = data.get("text", "")
        
        context = RequestContext(user_id=user_id)
        
        # Get A/B test variant
        variant = ABTestingService.get_variant(user_id, "prompt_optimization")
        
        # Get variant-specific prompt
        variant_prompt = ABTestingService.get_prompt_for_variant(variant, "prompt_optimization")
        
        # Generate content with variant prompt
        engine = get_content_engine()
        
        if variant_prompt:
            # Temporarily override system prompt
            original_prompt = engine.SYSTEM_INSTRUCTION
            engine.SYSTEM_INSTRUCTION = variant_prompt
            result = engine.generate_from_text(text=text, context=context)
            engine.SYSTEM_INSTRUCTION = original_prompt
        else:
            result = engine.generate_from_text(text=text, context=context)
        
        # Record result for analytics
        content_id = str(uuid.uuid4())
        ABTestingService.record_result("prompt_optimization", variant, user_id, content_type, result)
        
        # Format result for template
        formatted_result = _format_result_for_template(result, text[:300] if text else "Content")
        
        # Track each platform's content
        if HAS_ANALYTICS:
            try:
                for platform, platform_data in formatted_result.items():
                    text_content = str(platform_data.get('description' if platform == 'youtube' else 
                                                      'post' if platform == 'facebook' else 
                                                      'caption' if platform in ['instagram', 'tiktok'] else 
                                                      'tweet' if platform == 'twitter' else 
                                                      'title', ''))
                    AnalyticsService.track_content(
                        content_id=f"{content_id}_{platform}",
                        user_id=user_id,
                        platform=platform,
                        content_type=content_type,
                        text=text_content
                    )
            except Exception as e:
                logger.warning(f"Analytics tracking failed: {e}")
        
        # Store in session for result page
        request.session['result'] = {
            'description': text[:300] if text else "Content generated",
            'social': formatted_result,
            'content_id': content_id
        }
        
        return JsonResponse({
            "success": True,
            "variant": variant,
            "content_id": content_id,
            "redirect_url": "/result/"
        })
        
    except Exception as e:
        logger.exception("AB test generation failed")
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_update_analytics(request: HttpRequest):
    """Webhook endpoint to update engagement metrics"""
    try:
        data = json.loads(request.body.decode("utf-8"))
        content_id = data.get("content_id")
        metrics = {
            'impressions': data.get('impressions', 0),
            'likes': data.get('likes', 0),
            'comments': data.get('comments', 0),
            'shares': data.get('shares', 0),
            'saves': data.get('saves', 0),
            'clicks': data.get('clicks', 0)
        }
        
        success = AnalyticsService.update_metrics(content_id, metrics)
        
        return JsonResponse({
            "success": success,
            "message": "Analytics updated" if success else "Content not found"
        })
        
    except Exception as e:
        logger.exception("Analytics update failed")
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_get_analytics_dashboard(request: HttpRequest):
    """Get analytics dashboard for current user"""
    user_id = _get_user_id(request)
    dashboard = AnalyticsService.get_user_dashboard(user_id)
    
    return JsonResponse({
        "success": True,
        "dashboard": dashboard
    })


@require_http_methods(["GET"])
def api_get_ab_test_results(request: HttpRequest):
    """Get A/B test results"""
    test_name = request.GET.get('test_name', 'prompt_optimization')
    results = ABTestingService.get_test_results(test_name)
    
    return JsonResponse({
        "success": True,
        "results": results
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_create_ab_test(request: HttpRequest):
    """Create a new A/B test"""
    try:
        data = json.loads(request.body.decode("utf-8"))
        success = ABTestingService.create_test(
            name=data.get('name', 'test'),
            description=data.get('description', ''),
            variant_a_prompt=data.get('variant_a_prompt', ''),
            variant_b_prompt=data.get('variant_b_prompt', ''),
            traffic_split=data.get('traffic_split', 0.5)
        )
        
        return JsonResponse({
            "success": True,
            "message": "A/B test created successfully"
        })
        
    except Exception as e:
        logger.exception("AB test creation failed")
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)