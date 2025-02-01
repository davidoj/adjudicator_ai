print("Loading context processors module!")  # This will print when the module is imported

def debate_context(request):
    """Make debate context available to all templates"""
    print("Context processor called!")  # This should print for every request
    context = {}
    if hasattr(request, 'resolver_match') and request.resolver_match:
        print(f"URL name: {request.resolver_match.url_name}")
        if request.resolver_match.url_name == 'result':
            debate_id = request.resolver_match.kwargs.get('debate_id')
            print(f"Debate ID: {debate_id}")
            from .models import Debate
            try:
                debate = Debate.objects.get(id=debate_id)
                print(f"Found debate, original text length: {len(debate.original_text)}")
                context['original_text'] = debate.original_text
            except Debate.DoesNotExist:
                print("Debate not found")
                pass
    print(f"Context returned: {context}")
    return context 