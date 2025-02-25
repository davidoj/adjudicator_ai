from django.urls import path
from .views.pages import home, result, update_approval, hall_of_fame
from .views.analysis import analyze_stream
from .views.debug import debug_info

urlpatterns = [
    path('', home, name='home'),
    path('analyze-stream/', analyze_stream, name='analyze_stream'),
    path('result/<int:debate_id>/', result, name='result'),
    path('debate/<int:debate_id>/approve/', update_approval, name='update_approval'),
    path('hall-of-fame/', hall_of_fame, name='hall_of_fame'),
    path('debug/', debug_info, name='debug'),
] 