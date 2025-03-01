from django.http import JsonResponse, HttpResponseForbidden, StreamingHttpResponse, HttpResponse
from decimal import Decimal
import json
import re
import time
import logging
from ..models import Debate
from ..services.analysis import perform_analysis
import csv
from ..models import IPCreditUsage


logger = logging.getLogger('llm_calls')

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
        # Track last update percentage for smoother progress
        last_percent = 0
        analysis_snippets = {}
        
        def send_progress_update(data):
            nonlocal last_percent, analysis_snippets
            
            # Save data in appropriate category if it has content
            if 'content_snippet' in data and data.get('content_type'):
                content_type = data.get('content_type')
                analysis_snippets[content_type] = data.get('content_snippet')
            
            # Always update the percentage if it's bigger than last update
            if data.get('percent', 0) > last_percent:
                last_percent = data.get('percent', 0)
            
            # Include any snippets we've collected so far
            response_data = {
                'stage': data.get('stage', 'processing'),
                'message': data.get('message', 'Processing...'),
                'percent': last_percent,
                'snippets': analysis_snippets
            }
            
            # Return the formatted event
            return "data: " + json.dumps(response_data) + "\n\n"
        
        try:
            # Initial loading state
            yield "data: " + json.dumps({
                'stage': 'analyzing',
                'message': 'Identifying participants and arguments...',
                'percent': 5,
                'snippets': {}
            }) + "\n\n"
            
            # Create a queue for progress updates
            from queue import Queue
            import queue
            update_queue = Queue()
            
            def queue_update(data):
                update_queue.put(data)
                
            # Start analysis in a separate thread
            import threading
            result = {'data': None, 'error': None}
            
            def run_analysis():
                try:
                    result['data'] = perform_analysis(text, progress_callback=queue_update)
                except Exception as e:
                    result['error'] = str(e)
                finally:
                    # Mark completion
                    update_queue.put({'stage': '_done'})
            
            # Start analysis thread
            analysis_thread = threading.Thread(target=run_analysis)
            analysis_thread.start()
            
            # Process updates as they come in
            while True:
                try:
                    # Get next update, wait up to 0.5 seconds
                    update = update_queue.get(timeout=0.5)
                    
                    # Check if analysis is complete
                    if update.get('stage') == '_done':
                        break
                        
                    # Send the update
                    yield send_progress_update(update)
                    
                except queue.Empty:
                    # Send heartbeat to keep connection open
                    yield "data: {\"heartbeat\": true}\n\n"
            
            # Analysis is complete, check for error
            if result['error']:
                raise Exception(result['error'])
                
            # Get the analysis result
            result = result['data']
            
            # Create debate record
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
            
            debate_id = debate.id
            logger.info(f"Created debate with ID: {debate_id}")
            redirect_url = f'/result/{debate_id}/'
            
            # Send the final completion data as a progress update
            final_data = {
                'stage': 'complete',
                'message': 'Analysis complete!',
                'percent': 100,
                'redirect': redirect_url,
                'debate_id': debate_id,
                'winner': result['winner'],
                'judgment': result['judgment']
            }
            
            # Send the final update with all the necessary data
            yield "data: " + json.dumps(final_data) + "\n\n"
            
            del request.session['debate_text']
            
        except Exception as e:
            if 'Resource has been exhausted' in str(e) or '429' in str(e):
                yield "data: " + json.dumps({
                    'stage': 'error',
                    'message': (
                        "I'm currently using free-tier API access while testing. "
                        "Please wait a minute and try again. "
                        "Rate limits will be increased once cost controls are in place."
                    ),
                    'percent': 0
                }) + "\n\n"
            else:
                # Handle other errors
                yield "data: " + json.dumps({
                    'stage': 'error',
                    'message': str(e),
                    'percent': 0
                }) + "\n\n"

            if 'debate_text' in request.session:
                del request.session['debate_text']
    
    return StreamingHttpResponse(event_stream(), content_type='text/event-stream')