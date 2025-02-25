from django.shortcuts import render, redirect
from django.contrib import messages
from ..models import Debate, CreditBalance, ApprovalRecord
from ..services.analysis import perform_analysis, parse_evaluation_table
from decimal import Decimal
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import json
from django.db import models
from ..models import IPCreditUsage

logger = logging.getLogger('llm_calls')

def home(request):
    ip_address = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR'))
    if ip_address:
        ip_address = ip_address.split(',')[0]
    
    # Get IP-specific credit usage
    usage, created = IPCreditUsage.objects.get_or_create(ip_address=ip_address)
    credits_remaining = max(15 - usage.credits_used, 0)
    
    prefill_text = request.GET.get('prefill', '').strip()
    return render(request, 'debate/home.html', {
        'credits': credits_remaining,
        'debate_text': prefill_text,
        'total_credits_used': usage.credits_used
    })

def result(request, debate_id):
    debate = Debate.objects.get(id=debate_id)
    evaluation_tables = parse_evaluation_table(debate.evaluation_formatted, debate.judgment_formatted)
    return render(request, 'debate/result.html', {
        'debate': debate,
        'evaluation_tables': evaluation_tables,
        'parse_failed': evaluation_tables is None,
        'original_text': debate.original_text
    })

@require_POST
def update_approval(request, debate_id):
    try:
        data = json.loads(request.body)
        debate = Debate.objects.get(id=debate_id)
        
        field = data['field']
        value = data['value']
        ip_address = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR'))
        
        # Check if this IP has already voted
        existing_record = ApprovalRecord.objects.filter(
            debate=debate,
            ip_address=ip_address,
            field=field
        ).first()
        
        if existing_record:
            if existing_record.value == value:
                # Remove the vote if clicking the same button again
                if field == 'evaluation':
                    if value == 'approved':
                        debate.evaluation_approvals = models.F('evaluation_approvals') - 1
                    else:
                        debate.evaluation_disapprovals = models.F('evaluation_disapprovals') - 1
                else:  # judgment
                    if value == 'approved':
                        debate.judgment_approvals = models.F('judgment_approvals') - 1
                    else:
                        debate.judgment_disapprovals = models.F('judgment_disapprovals') - 1
                existing_record.delete()
                value = None
            else:
                # Change vote from approve to disapprove or vice versa
                if field == 'evaluation':
                    if value == 'approved':
                        debate.evaluation_approvals = models.F('evaluation_approvals') + 1
                        debate.evaluation_disapprovals = models.F('evaluation_disapprovals') - 1
                    else:
                        debate.evaluation_approvals = models.F('evaluation_approvals') - 1
                        debate.evaluation_disapprovals = models.F('evaluation_disapprovals') + 1
                else:  # judgment
                    if value == 'approved':
                        debate.judgment_approvals = models.F('judgment_approvals') + 1
                        debate.judgment_disapprovals = models.F('judgment_disapprovals') - 1
                    else:
                        debate.judgment_approvals = models.F('judgment_approvals') - 1
                        debate.judgment_disapprovals = models.F('judgment_disapprovals') + 1
                existing_record.value = value
                existing_record.save()
        else:
            # New vote
            if field == 'evaluation':
                if value == 'approved':
                    debate.evaluation_approvals = models.F('evaluation_approvals') + 1
                else:
                    debate.evaluation_disapprovals = models.F('evaluation_disapprovals') + 1
            else:  # judgment
                if value == 'approved':
                    debate.judgment_approvals = models.F('judgment_approvals') + 1
                else:
                    debate.judgment_disapprovals = models.F('judgment_disapprovals') + 1
            
            ApprovalRecord.objects.create(
                debate=debate,
                ip_address=ip_address,
                field=field,
                value=value
            )
        
        if field == 'evaluation':
            debate.evaluation_approval = value
        else:
            debate.judgment_approval = value
            
        debate.save()
        
        return JsonResponse({
            'success': True,
            'new_value': value
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)

def hall_of_fame(request):
    # Get debates with positive approval scores
    top_debates = Debate.objects.annotate(
        total_score=models.F('evaluation_approvals') - models.F('evaluation_disapprovals') + 
                   models.F('judgment_approvals') - models.F('judgment_disapprovals')
    ).filter(
        total_score__gt=0
    ).order_by('-created_at')[:10]
    
    return render(request, 'debate/hall_of_fame.html', {
        'top_debates': top_debates
    }) 