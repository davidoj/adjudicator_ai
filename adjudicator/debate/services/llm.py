import os
import logging
from datetime import datetime
import requests
import google.generativeai as genai
import re
import time

OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
HEADERS = {
    'Authorization': f'Bearer {OPENROUTER_API_KEY}',
    'HTTP-Referer': 'https://adjudicator.ai',
}

def setup_llm_logger():
    log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger('llm_calls')
    logger.setLevel(logging.DEBUG)
    
    today = datetime.now().strftime('%Y-%m-%d')
    handler = logging.FileHandler(os.path.join(log_dir, f'llm_calls_{today}.log'))
    handler.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter('%(asctime)s\n%(message)s\n' + '-'*80 + '\n')
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    return logger

def load_prompt(filename):
    prompt_path = os.path.join(os.path.dirname(__file__), '..', 'prompts', filename)
    with open(prompt_path) as f:
        return f.read().strip()

def validate_xml_response(response, expected_tags, prompt_name):
    """
    Validate that the LLM response contains all expected XML tags.
    
    Args:
        response (str): The LLM response text
        expected_tags (list): List of tag names that must be present
        prompt_name (str): The name of the prompt for logging
        
    Returns:
        tuple: (is_valid, missing_tags)
    """
    logger = logging.getLogger('llm_calls')
    missing_tags = []
    
    for tag in expected_tags:
        if not re.search(f'<{tag}>(.*?)</{tag}>', response, re.DOTALL):
            missing_tags.append(tag)
    
    if missing_tags:
        logger.warning(f"Response for {prompt_name} missing tags: {', '.join(missing_tags)}")
        return False, missing_tags
    
    return True, []

def make_llm_call(prompt, use_openrouter=False, role='system', debate_id=None, prompt_name=None, 
                  expected_tags=None, max_retries=2, user_update_callback=None):
    """
    Make an LLM call with validation and retry logic
    
    Args:
        prompt (str): The prompt to send to the LLM
        use_openrouter (bool): Whether to use OpenRouter or Gemini
        role (str): The role for the LLM ('system', 'summarizer', etc.)
        debate_id (int): The ID of the debate for logging
        prompt_name (str): Name of the prompt being used
        expected_tags (list): List of XML tags that must be in the response
        max_retries (int): Maximum number of retry attempts
        user_update_callback (callable): Function to call with progress updates
        
    Returns:
        str: The LLM response
    """
    logger = setup_llm_logger()
    logger.debug("=== LLM Call ===\nPrompt:\n%s", prompt)
    
    # Send update to user if callback provided
    if user_update_callback and prompt_name:
        user_update_callback({
            'status': 'processing',
            'stage': prompt_name,
            'message': f"Processing {prompt_name} step..."
        })
    
    attempt = 0
    content = None
    model_used = None
    
    while attempt <= max_retries:
        attempt += 1
        
        try:
            # Set up system prompt based on role
            if role == 'summarizer':
                system_prompt = load_prompt('summarizer.txt')
            else:
                system_prompt = load_prompt('system.txt')
                principles = load_prompt('principles.txt')
                system_prompt = system_prompt.format(principles=principles)
            
            # Modify prompt for retries to emphasize format requirements
            current_prompt = prompt
            if attempt > 1:
                reminder = "IMPORTANT: Your response MUST include all the XML tags specified in the instructions. Make sure to properly open and close all tags."
                current_prompt = f"{reminder}\n\n{prompt}"
                
                if user_update_callback:
                    user_update_callback({
                        'status': 'retrying',
                        'stage': prompt_name,
                        'attempt': attempt,
                        'message': f"Retrying {prompt_name} step (attempt {attempt}/{max_retries+1})..."
                    })
            
            # Make the actual API call
            if use_openrouter:
                # OpenRouter implementation
                response = requests.post(
                    'https://openrouter.ai/api/v1/chat/completions',
                    headers=HEADERS,
                    json={
                        'model': 'deepseek/deepseek-chat',
                        'messages': [
                            {'role': 'system', 'content': system_prompt},
                            {'role': 'user', 'content': current_prompt}
                        ]
                    }
                )
                
                logger.debug("Status Code: %d", response.status_code)
                logger.debug("Full Response:\n%s", response.text)
                
                if response.status_code != 200:
                    error_msg = f"API returned status code {response.status_code}: {response.text}"
                    logger.error(error_msg)
                    raise Exception(error_msg)
                    
                response_json = response.json()
                content = response_json['choices'][0]['message']['content']
                model_used = 'deepseek/deepseek-chat'
            else:
                # Gemini implementation
                GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
                genai.configure(api_key=GOOGLE_API_KEY)
                
                model = genai.GenerativeModel('gemini-2.0-flash')
                chat = model.start_chat(history=[
                    {'role': 'user', 'parts': [system_prompt]},
                    {'role': 'model', 'parts': ['Understood. I will follow the provided instructions.']}
                ])
                
                response = chat.send_message(current_prompt)
                content = response.text
                model_used = 'gemini-2.0-flash-exp'
                
                logger.debug("Gemini Response:\n%s", content)
            
            # Validate response if expected tags were provided
            if expected_tags:
                is_valid, missing_tags = validate_xml_response(content, expected_tags, prompt_name)
                if not is_valid:
                    if attempt <= max_retries:
                        logger.warning(f"Invalid response format, missing tags: {missing_tags}. Retrying...")
                        time.sleep(1)  # Short delay before retry
                        continue
                    else:
                        logger.error(f"Failed to get valid response after {max_retries+1} attempts")
            
            # Save the interaction if debate_id is provided
            if debate_id and prompt_name:
                from ..models import LLMInteraction, Debate
                debate = Debate.objects.get(id=debate_id)
                LLMInteraction.objects.create(
                    debate=debate,
                    prompt_name=prompt_name,
                    prompt_text=current_prompt,
                    response=content,
                    model_used=model_used
                )
            
            # Success - send update and return content
            if user_update_callback:
                user_update_callback({
                    'status': 'completed',
                    'stage': prompt_name,
                    'message': f"Completed {prompt_name} step"
                })
                
            return content
            
        except Exception as e:
            logger.error("Error making LLM call: %s", str(e))
            
            if attempt <= max_retries:
                time.sleep(2)  # Delay before retry
                continue
                
            # Log the failed attempt if we've exhausted retries
            if debate_id and prompt_name:
                from ..models import LLMInteraction, Debate
                debate = Debate.objects.get(id=debate_id)
                LLMInteraction.objects.create(
                    debate=debate,
                    prompt_name=prompt_name,
                    prompt_text=current_prompt if 'current_prompt' in locals() else prompt,
                    model_used=model_used if model_used else 'unknown',
                    success=False,
                    error_message=str(e)
                )
            
            if user_update_callback:
                user_update_callback({
                    'status': 'error',
                    'stage': prompt_name,
                    'message': f"Error in {prompt_name} step: {str(e)}"
                })
                
            raise 