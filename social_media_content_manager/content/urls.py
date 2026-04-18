# content/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('result/', views.result, name='result'),
    path('process/', views.process, name='process'),
    path('api-status/', views.api_status, name='api_status'),
    # path('api-job/result/', views.api_job_result, name='api_job_result'),  # If you have this
    
    # A/B Testing and Analytics endpoints (ADD THESE)
    path('api/generate-with-ab-test/', views.api_generate_with_ab_test, name='api_generate_ab_test'),
    path('api/update-analytics/', views.api_update_analytics, name='api_update_analytics'),
    path('api/analytics-dashboard/', views.api_get_analytics_dashboard, name='api_analytics_dashboard'),
    path('api/ab-test-results/', views.api_get_ab_test_results, name='api_ab_test_results'),
    path('api/create-ab-test/', views.api_create_ab_test, name='api_create_ab_test'),
]