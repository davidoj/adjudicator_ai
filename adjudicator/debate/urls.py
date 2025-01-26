from django.urls import path
from .views import analyze_stream, home, result

urlpatterns = [
    path('', home, name='home'),
    path('analyze-stream/', analyze_stream, name='analyze_stream'),
    path('result/<int:debate_id>/', result, name='result'),
] 