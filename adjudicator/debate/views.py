from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseForbidden, StreamingHttpResponse
from .models import Debate, CreditBalance
import requests
import os
import time
from decimal import Decimal
import re
import logging
from datetime import datetime
from django.contrib import messages
import json
import google.generativeai as genai

OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
HEADERS = {
    'Authorization': f'Bearer {OPENROUTER_API_KEY}',
    'HTTP-Referer': 'https://adjudicator.ai',  # Your site URL
}

def setup_llm_logger():
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Create a logger
    logger = logging.getLogger('llm_calls')
    logger.setLevel(logging.DEBUG)
    
    # Create a file handler with today's date
    today = datetime.now().strftime('%Y-%m-%d')
    handler = logging.FileHandler(os.path.join(log_dir, f'llm_calls_{today}.log'))
    handler.setLevel(logging.DEBUG)
    
    # Create a formatter
    formatter = logging.Formatter('%(asctime)s\n%(message)s\n' + '-'*80 + '\n')
    handler.setFormatter(formatter)
    
    # Add the handler to the logger
    logger.addHandler(handler)
    return logger

def make_llm_call(prompt, use_openrouter=False, role='system'):
    logger = setup_llm_logger()
    logger.debug("=== LLM Call ===\nPrompt:\n%s", prompt)
    
    try:
        # Load appropriate system prompt based on role
        if role == 'summarizer':
            system_prompt = load_prompt('summarizer.txt')
        else:
            system_prompt = load_prompt('system.txt')
            principles = load_prompt('principles.txt')
            system_prompt = system_prompt.format(principles=principles)
        
        if use_openrouter:
            response = requests.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers=HEADERS,
                json={
                    'model': 'deepseek/deepseek-chat',
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': prompt}
                    ]
                }
            )
            
            # Log the response
            logger.debug("Status Code: %d", response.status_code)
            logger.debug("Full Response:\n%s", response.text)
            
            if response.status_code != 200:
                error_msg = "API returned status code {}: {}".format(response.status_code, response.text)
                logger.error(error_msg)
                raise Exception(error_msg)
                
            response_json = response.json()
            content = response_json['choices'][0]['message']['content']
        else:
            # Use Gemini
            GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
            genai.configure(api_key=GOOGLE_API_KEY)
            
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            chat = model.start_chat(history=[
                {'role': 'user', 'parts': [system_prompt]},
                {'role': 'model', 'parts': ['Understood. I will follow the provided instructions.']}
            ])
            
            response = chat.send_message(prompt)
            content = response.text
            
            # Log the response
            logger.debug("Gemini Response:\n%s", content)
            
        return content
        
    except Exception as e:
        logger.error("Error making LLM call: %s", str(e))
        raise

def load_prompt(filename):
    prompt_path = os.path.join(os.path.dirname(__file__), 'prompts', filename)
    with open(prompt_path) as f:
        return f.read().strip()

def extract_tag(tag, content, required=True):
    # Make the regex pattern more lenient with whitespace
    match = re.search(f'<{tag}>\s*(.*?)\s*</{tag}>', content, re.DOTALL)
    if match:
        return match.group(1).strip()
    if required:
        logging.error(f"Failed to find required tag {tag} in response:\n{content}")
        raise ValueError(f"Analysis failed: Could not identify {tag} in the debate")
    return None

def analyze_debate(text):
    try:
        print("\nStarting debate analysis...")
        logger = setup_llm_logger()
        
        print("Step 1/3: Analyzing arguments...")
        analysis_prompt = load_prompt('analyze.txt')
        analysis = make_llm_call(
            analysis_prompt.format(
                text=text,
                text_party_1="{first party name}",
                text_party_2="{second party name}"
            ),
            role='summarizer'  # Use summarizer prompt for first call
        )
        
        # Extract structured data using XML-style tags with error handling
        belligerent_1 = extract_tag('p1', analysis)
        belligerent_2 = extract_tag('p2', analysis)
        summary_1 = extract_tag('s1', analysis)
        summary_2 = extract_tag('s2', analysis)

        time.sleep(1)

        print("Step 2/3: Evaluating argument interactions...")
        evaluation = make_llm_call(
            load_prompt('evaluate.txt').format(structured_arguments=analysis)
        )
        
        time.sleep(1)

        print("Step 3/3: Determining final judgment...")
        judgment = make_llm_call(
            load_prompt('judge.txt').format(evaluations=evaluation)
        )
        
        winner = extract_tag('winner', judgment)

        return {
            'belligerent_1': belligerent_1,
            'belligerent_2': belligerent_2,
            'summary_1': summary_1,
            'summary_2': summary_2,
            'winner': winner,
            'analysis': analysis,
            'evaluation': evaluation,
            'judgment': judgment
        }
    except ValueError as e:
        # Handle expected format errors
        logger.error("Analysis failed: %s", str(e))
        raise
    except Exception as e:
        # Handle unexpected errors
        logger.error("Error in analyze_debate: %s", str(e))
        raise

def get_credits():
    return CreditBalance.get_credits()

def home(request):
    if request.method == 'POST':
        text = request.POST.get('debate_text')
        
        # Temporarily disabled credit check
        # required_credits = Decimal('1.0')
        # if not CreditBalance.deduct_credits(required_credits):
        #     return HttpResponseForbidden("Not enough credits available")
            
        try:
            result = analyze_debate(text)
        except ValueError as e:
            # Handle format errors
            messages.error(request, str(e))
            return render(request, 'debate/home.html', {
                'credits': 999,  # Temporary placeholder
                'debate_text': text,  # Preserve the user's input
                'error': str(e)
            })
        except Exception as e:
            # Handle unexpected errors
            messages.error(request, "An unexpected error occurred during analysis. Please try again.")
            return render(request, 'debate/home.html', {
                'credits': 999,  # Temporary placeholder
                'debate_text': text,
                'error': "Analysis failed. Please ensure your text contains a clear debate or argument."
            })
            
        debate = Debate.objects.create(
            original_text=text,
            belligerent_1=result['belligerent_1'],
            belligerent_2=result['belligerent_2'],
            summary_1=result['summary_1'],
            summary_2=result['summary_2'],
            winner=result['winner'],
            credit_cost=Decimal('1.0'),  # Temporary placeholder
            analysis=result['analysis'],
            evaluation=result['evaluation'],
            judgment=result['judgment']
        )
        
        return redirect('result', debate_id=debate.id)
    
    return render(request, 'debate/home.html', {'credits': 999})  # Temporary placeholder

def parse_evaluation_table(evaluation_text, judgment_text=None):
    """Parse evaluation text into a structured table format"""
    logger = setup_llm_logger()
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

def result(request, debate_id):
    debate = Debate.objects.get(id=debate_id)
    evaluation_tables = parse_evaluation_table(debate.evaluation, debate.judgment)
    return render(request, 'debate/result.html', {
        'debate': debate,
        'evaluation_tables': evaluation_tables,
        'parse_failed': evaluation_tables is None
    })

def analyze_stream(request):
    if request.method == 'POST':
        # Store the debate text in session
        request.session['debate_text'] = request.POST.get('debate_text')
        return JsonResponse({'status': 'ok'})
    
    # For GET requests, check if we have debate text in session
    text = request.session.get('debate_text')
    if not text:
        return HttpResponseForbidden()
        
    def event_stream():
        try:
            # Step 1: Initial Analysis
            yield "data: " + json.dumps({
                'stage': 'analyzing',
                'message': 'Identifying participants and arguments...'
            }) + "\n\n"
            
            analysis = make_llm_call(
                load_prompt('analyze.txt').format(
                    text=text,
                    text_party_1="{first party name}",
                    text_party_2="{second party name}"
                ),
                role='summarizer'  # Use summarizer prompt for first call
            )
            
            belligerent_1 = extract_tag('p1', analysis)
            belligerent_2 = extract_tag('p2', analysis)
            summary_1 = extract_tag('s1', analysis)
            summary_2 = extract_tag('s2', analysis)
            
            yield "data: " + json.dumps({
                'stage': 'initial_analysis',
                'belligerent_1': belligerent_1,
                'belligerent_2': belligerent_2,
                'summary_1': summary_1,
                'summary_2': summary_2
            }) + "\n\n"
            
            time.sleep(1)
            
            # Step 2: Evaluation
            yield "data: " + json.dumps({
                'stage': 'evaluating',
                'message': 'Evaluating argument interactions...'
            }) + "\n\n"
            
            evaluation = make_llm_call(
                load_prompt('evaluate.txt').format(structured_arguments=analysis)
            )
            
            yield "data: " + json.dumps({
                'stage': 'evaluation',
                'evaluation': evaluation
            }) + "\n\n"
            
            time.sleep(1)
            
            # Step 3: Final Judgment
            yield "data: " + json.dumps({
                'stage': 'judging',
                'message': 'Determining final judgment...'
            }) + "\n\n"
            
            judgment = make_llm_call(
                load_prompt('judge.txt').format(evaluations=evaluation)
            )
            
            winner = extract_tag('winner', judgment)
            
            # Save to database
            debate = Debate.objects.create(
                original_text=text,
                belligerent_1=belligerent_1,
                belligerent_2=belligerent_2,
                summary_1=summary_1,
                summary_2=summary_2,
                winner=winner,
                credit_cost=Decimal('1.0'),
                analysis=analysis,
                evaluation=evaluation,
                judgment=judgment
            )
            
            yield "data: " + json.dumps({
                'stage': 'complete',
                'winner': winner,
                'judgment': judgment,
                'redirect': f'/result/{debate.id}/'
            }) + "\n\n"
            
            # Clean up session after complete
            del request.session['debate_text']
            
        except Exception as e:
            if 'debate_text' in request.session:
                del request.session['debate_text']
            yield "data: " + json.dumps({
                'stage': 'error',
                'message': str(e)
            }) + "\n\n"
    
    return StreamingHttpResponse(event_stream(), content_type='text/event-stream') 