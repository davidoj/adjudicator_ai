from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('debate.urls')),  # Let debate.urls handle all debate routes
] 