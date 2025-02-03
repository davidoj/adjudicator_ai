import re
import time
import logging
from .llm import make_llm_call, load_prompt

logger = logging.getLogger('llm_calls')

def extract_tag(tag, content, required=True):
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

def perform_analysis(text, debate_id=None):
    """Core analysis logic shared between streaming and non-streaming paths"""
    logger = logging.getLogger('llm_calls')
    
    # Step 1: Initial Analysis
    analysis_prompt = load_prompt('analyze.txt')
    analysis = make_llm_call(
        analysis_prompt.format(
            text=text,
            text_party_1="{first party name}",
            text_party_2="{second party name}"
        ),
        role='summarizer',
        debate_id=debate_id,
        prompt_name='analyze'
    )
    
    # Extract real names and title before anonymizing
    belligerent_1 = extract_tag('p1', analysis)
    belligerent_2 = extract_tag('p2', analysis)
    summary_1 = extract_tag('s1', analysis)
    summary_2 = extract_tag('s2', analysis)
    debate_title = extract_tag('debate_title', analysis)

    print(f"Debate title (analysis): {debate_title}")

    # Remove the name tags from analysis before passing to evaluate
    anonymized_analysis = re.sub(r'<p1>.*?</p1>', 'P1', analysis)
    anonymized_analysis = re.sub(r'<p2>.*?</p2>', 'P2', anonymized_analysis)

    time.sleep(1)

    # Step 2: Evaluation (using anonymized analysis)
    evaluation = make_llm_call(
        load_prompt('evaluate.txt').format(structured_arguments=anonymized_analysis),
        debate_id=debate_id,
        prompt_name='evaluate'
    )
    
    time.sleep(1)

    # Step 3: Final Judgment (using anonymized evaluation)
    judgment = make_llm_call(
        load_prompt('judge.txt').format(evaluations=evaluation),
        debate_id=debate_id,
        prompt_name='judge'
    )
    
    winner = extract_tag('winner', judgment)
    
    # Format the evaluation and judgment for better readability
    evaluation_formatted = make_llm_call(
        load_prompt('format_evaluation.txt').format(text=evaluation),
        role='copywriter',
        debate_id=debate_id,
        prompt_name='format_evaluation'
    )
    
    time.sleep(1)
    
    judgment_formatted = make_llm_call(
        load_prompt('format_judgment.txt').format(text=judgment),
        role='copywriter',
        debate_id=debate_id,
        prompt_name='format_judgment'
    )
    
    return {
        'belligerent_1': belligerent_1,
        'belligerent_2': belligerent_2,
        'summary_1': summary_1,
        'summary_2': summary_2,
        'winner': winner,
        'analysis': analysis,
        'evaluation': evaluation,
        'evaluation_formatted': evaluation_formatted,
        'judgment': judgment,
        'judgment_formatted': judgment_formatted,
        'title': debate_title
    } 