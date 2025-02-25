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