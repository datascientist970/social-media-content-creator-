from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('process/', views.process, name='process'),
    path('result/', views.result, name='result'),
]