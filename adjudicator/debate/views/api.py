import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from decimal import Decimal
from adjudicator.debate.models import IPCreditUsage, CreditBalance
import logging

logger = logging.getLogger(__name__)

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')

@require_POST
def analyze_debate(request):
    try:
        data = json.loads(request.body)
        debate_text = data.get('debate_text', '')
        
        # Get client IP
        ip_address = get_client_ip(request)
        
        # Check if IP has remaining credits
        credit_cost = Decimal('1.00')
        if not IPCreditUsage.can_use_credits(ip_address, credit_cost):
            return JsonResponse({
                'error': 'You have reached your credit limit of 15. Please try again later.'
            }, status=429)
            
        # Check global credit balance
        if not CreditBalance.get_credits() >= credit_cost:
            return JsonResponse({
                'error': 'Insufficient global credits'
            }, status=402)

        # Process debate text and create response
        response_data = {
            'status': 'success',
            'message': 'Debate analyzed successfully',
            # Add your debate analysis results here
        }

        # If successful, deduct credits and record IP usage
        if CreditBalance.deduct_credits(credit_cost):
            IPCreditUsage.add_usage(ip_address, credit_cost)
            return JsonResponse(response_data)
        else:
            return JsonResponse({
                'error': 'Failed to deduct credits'
            }, status=402)

    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500) 