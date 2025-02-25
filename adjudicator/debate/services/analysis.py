import re
import time
import logging
from .llm import make_llm_call, load_prompt, validate_xml_response

logger = logging.getLogger('llm_calls')

def extract_tag(tag, content, required=True):
    match = re.search(fr'<{tag}>\s*(.*?)\s*</{tag}>', content, re.DOTALL)
    if match:
        return match.group(1).strip()
    if required:
        logging.error(f"Failed to find required tag {tag} in response:\n{content}")
        print(f'failed to find {tag} in:\n{content}')
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

def perform_analysis(text, debate_id=None, progress_callback=None):
    """
    Core analysis logic with progress tracking
    
    Args:
        text (str): The debate text to analyze
        debate_id (int): Optional debate ID for logging
        progress_callback (callable): Function to call with progress updates
        
    Returns:
        dict: The analysis results
    """
    logger = logging.getLogger('llm_calls')
    
    # Set of expected tags for each stage
    analysis_expected_tags = ['debate_title', 'p1', 'p2', 's1', 's2', 'complexity']
    evaluation_expected_tags = ['argument_map', 'direct_interactions', 'decisive_factors', 'uncertainties']
    judgment_expected_tags = ['winner', 'reasoning', 'strength', 'strengthening_advice']
    
    # Update progress
    def update_progress(status):
        if progress_callback:
            # Make sure we don't use 'complete' in progress updates
            if status.get('stage') == 'complete':
                status['stage'] = 'processing_complete'
            progress_callback(status)
    
    # Step 1: Initial Analysis
    update_progress({'stage': 'analysis', 'percent': 10, 'message': 'Identifying participants and arguments...'})
    
    analysis_prompt = load_prompt('analyze.txt')
    analysis = make_llm_call(
        analysis_prompt.format(
            text=text,
            text_party_1="{first party name}",
            text_party_2="{second party name}"
        ),
        role='summarizer',
        debate_id=debate_id,
        prompt_name='analyze',
        expected_tags=analysis_expected_tags,
        user_update_callback=update_progress
    )
    
    # Extract real names and title before anonymizing
    belligerent_1 = extract_tag('p1', analysis)
    belligerent_2 = extract_tag('p2', analysis)
    summary_1 = extract_tag('s1', analysis)
    summary_2 = extract_tag('s2', analysis)
    debate_title = extract_tag('debate_title', analysis)

    # Send a progress update with the title
    if progress_callback:
        progress_callback({
            'stage': 'title_extracted',
            'percent': 25,
            'message': f'Identified debate: {debate_title}',
            'title': debate_title,
            'belligerent_1': belligerent_1,
            'belligerent_2': belligerent_2,
            'summary_1': summary_1[:100] + "...",
            'summary_2': summary_2[:100] + "..."
        })
    
    # Send participant summaries as snippets
    update_progress({
        'stage': 'participants', 
        'percent': 30, 
        'message': f'Identified participants: {belligerent_1} vs {belligerent_2}',
        'content_type': 'participants',
        'content_snippet': f"{belligerent_1}: {summary_1[:100]}...\n\n{belligerent_2}: {summary_2[:100]}..."
    })

    # Remove the name tags from analysis before passing to evaluate
    anonymized_analysis = re.sub(r'<p1>.*?</p1>', 'P1', analysis)
    anonymized_analysis = re.sub(r'<p2>.*?</p2>', 'P2', anonymized_analysis)

    update_progress({'stage': 'evaluation', 'percent': 40, 'message': 'Evaluating arguments...'})
    time.sleep(1)

    # Step 2: Evaluation (using anonymized analysis)
    evaluation = make_llm_call(
        load_prompt('evaluate.txt').format(structured_arguments=anonymized_analysis),
        debate_id=debate_id,
        prompt_name='evaluate',
        expected_tags=evaluation_expected_tags,
        user_update_callback=update_progress
    )
    
    # Extract a snippet of the evaluation and send it
    try:
        eval_snippet = extract_tag('argument_map', evaluation)
        update_progress({
            'stage': 'evaluation_progress', 
            'percent': 60, 
            'message': 'Arguments evaluated',
            'content_type': 'evaluation',
            'content_snippet': eval_snippet[:200] + "..."
        })
    except:
        pass
    
    update_progress({'stage': 'judgment', 'percent': 70, 'message': 'Determining final judgment...'})
    time.sleep(1)

    # Step 3: Final Judgment (using anonymized evaluation)
    judgment = make_llm_call(
        load_prompt('judge.txt').format(evaluations=evaluation),
        debate_id=debate_id,
        prompt_name='judge',
        expected_tags=judgment_expected_tags,
        user_update_callback=update_progress
    )
    
    winner = extract_tag('winner', judgment)
    
    # Send the winner as a snippet
    try:
        reasoning = extract_tag('reasoning', judgment)
        update_progress({
            'stage': 'judgment_progress', 
            'percent': 80, 
            'message': f'Judgment: {winner} wins',
            'content_type': 'judgment',
            'content_snippet': f"Winner: {winner}\n\nReasoning: {reasoning[:150]}..."
        })
    except:
        pass
    
    update_progress({'stage': 'formatting', 'percent': 85, 'message': 'Formatting results...'})
    
    # Format the evaluation and judgment for better readability
    evaluation_formatted = make_llm_call(
        load_prompt('format_evaluation.txt').format(text=evaluation),
        role='copywriter',
        debate_id=debate_id,
        prompt_name='format_evaluation',
        user_update_callback=update_progress
    )
    
    time.sleep(1)
    
    judgment_formatted = make_llm_call(
        load_prompt('format_judgment.txt').format(text=judgment),
        role='copywriter',
        debate_id=debate_id,
        prompt_name='format_judgment',
        user_update_callback=update_progress
    )
    
    update_progress({'stage': 'processing_complete', 'percent': 100, 'message': 'Analysis complete!'})
    
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