import os
import logging
from datetime import datetime
import requests
import google.generativeai as genai

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

def make_llm_call(prompt, use_openrouter=False, role='system', debate_id=None, prompt_name=None):
    logger = setup_llm_logger()
    logger.debug("=== LLM Call ===\nPrompt:\n%s", prompt)
    
    try:
        if role == 'summarizer':
            system_prompt = load_prompt('summarizer.txt')
        else:
            system_prompt = load_prompt('system.txt')
            principles = load_prompt('principles.txt')
            system_prompt = system_prompt.format(principles=principles)
        
        content = None
        model_used = None
        
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
            GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
            genai.configure(api_key=GOOGLE_API_KEY)
            
            model = genai.GenerativeModel('gemini-2.0-flash')
            chat = model.start_chat(history=[
                {'role': 'user', 'parts': [system_prompt]},
                {'role': 'model', 'parts': ['Understood. I will follow the provided instructions.']}
            ])
            
            response = chat.send_message(prompt)
            content = response.text
            model_used = 'gemini-2.0-flash-exp'
            
            logger.debug("Gemini Response:\n%s", content)

        # Save the interaction if debate_id is provided
        if debate_id and prompt_name:
            from ..models import LLMInteraction, Debate
            debate = Debate.objects.get(id=debate_id)
            LLMInteraction.objects.create(
                debate=debate,
                prompt_name=prompt_name,
                prompt_text=prompt,
                response=content,
                model_used=model_used
            )
            
        return content
        
    except Exception as e:
        logger.error("Error making LLM call: %s", str(e))
        if debate_id and prompt_name:
            from ..models import LLMInteraction, Debate
            debate = Debate.objects.get(id=debate_id)
            LLMInteraction.objects.create(
                debate=debate,
                prompt_name=prompt_name,
                prompt_text=prompt,
                model_used=model_used if model_used else 'unknown',
                success=False,
                error_message=str(e)
            )
        raise 