from django.http import JsonResponse, HttpResponseForbidden, StreamingHttpResponse, HttpResponse
from django.shortcuts import redirect
from decimal import Decimal
import json
import re
import time
import logging
from ..services.llm import make_llm_call, load_prompt
from ..models import Debate
from ..services.analysis import perform_analysis
import csv
from ..models import IPCreditUsage, CreditBalance

logger = logging.getLogger('llm_calls')

def extract_tag(tag, content, required=True):
    # Make the regex pattern more lenient with whitespace
    match = re.search(fr'<{tag}>\s*(.*?)\s*</{tag}>', content, re.DOTALL)
    if match:
        return match.group(1).strip()
    if required:
        logging.error(f"Failed to find required tag {tag} in response:\n{content}")
        raise ValueError(f"Analysis failed: Could not identify {tag} in the debate")
    return None

def parse_evaluation_table(evaluation_text, judgment_text=None):
    """Parse evaluation text into a structured table format"""
    logger.debug("Attempting to parse evaluation text:\n%s", evaluation_text)
    judge_map = False
    try:
        tables = []
        
        # First try to get argument map from judgment if available
        if judgment_text:
            logger.debug("Attempting to parse judgment text:\n%s", judgment_text)
            try:
                map_match = re.search(r'<final_argument_map>(.*?)</final_argument_map>', judgment_text, re.DOTALL)
                if map_match:
                    map_text = map_match.group(1)
                    topic = extract_tag('topic', map_text)
                    p1_arg = extract_tag('p1_argument', map_text)
                    p2_arg = extract_tag('p2_argument', map_text)
                    verdict = extract_tag('verdict', map_text)
                    reason = extract_tag('reason', map_text)
                    
                    tables.append({
                        'topic': topic,
                        'p1_argument': p1_arg,
                        'p2_argument': p2_arg,
                        'outcome': f"{verdict}: {reason}"
                    })
                    logger.debug("Successfully parsed judgment argument map")
                    judge_map = True
            except Exception as e:
                logger.error("Failed to parse judgment map: %s", str(e))
        
        # Then get argument maps from evaluation
        logger.debug("Attempting to parse evaluation text:\n%s", evaluation_text)
        try:
            if not judge_map:
                # Get main argument map
                map_match = re.search(r'<argument_map>(.*?)</argument_map>', evaluation_text, re.DOTALL)
                if map_match:
                    map_text = map_match.group(1)
                    topic = extract_tag('topic', map_text)
                    p1_arg = extract_tag('p1_argument', map_text)
                    p2_arg = extract_tag('p2_argument', map_text)
                    
                    tables.append({
                        'topic': topic,
                        'p1_argument': p1_arg,
                        'p2_argument': p2_arg,
                        'outcome': "Initial argument summary"
                    })
                    logger.debug("Successfully parsed evaluation argument map")
            
            # Get direct interactions
            interactions_match = re.search(r'<direct_interactions>(.*?)</direct_interactions>', evaluation_text, re.DOTALL)
            if interactions_match:
                interactions_text = interactions_match.group(1)
                interaction_matches = re.finditer(r'<interaction>\s*(.*?)\s*</interaction>', interactions_text, re.DOTALL)
                
                for interaction in interaction_matches:
                    interaction_text = interaction.group(1).strip()
                    try:
                        topic = extract_tag('topic', interaction_text)
                        p1_pos = extract_tag('p1_position', interaction_text)
                        p2_pos = extract_tag('p2_position', interaction_text)
                        outcome = extract_tag('outcome', interaction_text)
                        verdict = extract_tag('verdict', outcome)
                        reason = extract_tag('reason', outcome)
                        
                        tables.append({
                            'topic': topic,
                            'p1_argument': p1_pos,
                            'p2_argument': p2_pos,
                            'outcome': f"{verdict}: {reason}"
                        })
                    except Exception as e:
                        logger.error("Failed to parse interaction: %s\nText was:\n%s", str(e), interaction_text)
            
        except Exception as e:
            logger.error("Failed to parse evaluation map: %s", str(e))
        
        if not tables:
            logger.error("No argument maps were successfully parsed")
            return None
            
        return tables
    except Exception as e:
        logger.error("Failed to parse evaluation table: %s\nEvaluation text was:\n%s\nJudgment text was:\n%s", 
                    str(e), evaluation_text, judgment_text)
        return None

def analyze_debate(text):
    try:
        print("\nStarting debate analysis...")
        result = perform_analysis(text)
        return result
    except ValueError as e:
        logger.error("Analysis failed: %s", str(e))
        raise
    except Exception as e:
        logger.error("Error in analyze_debate: %s", str(e))
        raise

def analyze_stream(request):
    if request.method == 'POST':
        request.session['debate_text'] = request.POST.get('debate_text')
        
        # Get client IP and check credits here, before starting analysis
        ip_address = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR'))
        if ip_address:
            ip_address = ip_address.split(',')[0]
            
        # Check if IP has remaining credits
        credit_cost = Decimal('1.00')
        if not IPCreditUsage.can_use_credits(ip_address, credit_cost):
            return JsonResponse({
                'error': 'You have reached your credit limit of 15. Please try again later.'
            }, status=429)
            
        # Record IP usage
        IPCreditUsage.add_usage(ip_address, credit_cost)
        
        return JsonResponse({'status': 'ok'})
    
    text = request.session.get('debate_text')
    if not text:
        return HttpResponseForbidden()
        
    def event_stream():
        try:
            yield "data: " + json.dumps({
                'stage': 'analyzing',
                'message': 'Identifying participants and arguments...'
            }) + "\n\n"
            
            result = perform_analysis(text)
            
            yield "data: " + json.dumps({
                'stage': 'initial_analysis',
                'belligerent_1': result['belligerent_1'],
                'belligerent_2': result['belligerent_2'],
                'summary_1': result['summary_1'],
                'summary_2': result['summary_2']
            }) + "\n\n"
            
            yield "data: " + json.dumps({
                'stage': 'evaluation',
                'evaluation': result['evaluation']
            }) + "\n\n"
            
            debate = Debate.objects.create(
                original_text=text,
                belligerent_1=result['belligerent_1'],
                belligerent_2=result['belligerent_2'],
                summary_1=result['summary_1'],
                summary_2=result['summary_2'],
                winner=result['winner'],
                credit_cost=Decimal('1.0'),
                analysis=result['analysis'],
                evaluation=result['evaluation'],
                judgment=result['judgment'],
                title=result['title'],
                evaluation_formatted=result['evaluation_formatted'],
                judgment_formatted=result['judgment_formatted']
            )
            
            yield "data: " + json.dumps({
                'stage': 'complete',
                'winner': result['winner'],
                'judgment': result['judgment'],
                'redirect': f'/result/{debate.id}/'
            }) + "\n\n"
            
            del request.session['debate_text']
            
        except Exception as e:
            if 'debate_text' in request.session:
                del request.session['debate_text']
            yield "data: " + json.dumps({
                'stage': 'error',
                'message': str(e)
            }) + "\n\n"
    
    return StreamingHttpResponse(event_stream(), content_type='text/event-stream')