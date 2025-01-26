from django.contrib import admin
from django.urls import path, include
from debate import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('result/<int:debate_id>/', views.result, name='result'),
    path('analyze-stream/', views.analyze_stream, name='analyze_stream'),
] 