from django.http import JsonResponse
from django.shortcuts import render
from ..models import Debate

def debug_info(request):
    """A debugging view to show information about recent debates"""
    recent_debates = Debate.objects.order_by('-created_at')[:5]
    
    debates_info = []
    for debate in recent_debates:
        debates_info.append({
            'id': debate.id,
            'title': debate.title,
            'created_at': debate.created_at,
            'url': f'/result/{debate.id}/'
        })
    
    if request.headers.get('Accept') == 'application/json':
        return JsonResponse({'recent_debates': debates_info})
    else:
        return render(request, 'debate/debug.html', {
            'recent_debates': recent_debates
        }) 