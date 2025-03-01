import re
import time
import logging
from .llm import make_llm_call, load_prompt

logger = logging.getLogger('llm_calls')

class AnalysisPipeline:
    def __init__(self, stages=None):
        self.stages = stages or []
        
    def process(self, context):
        """
        Process the input through all pipeline stages
        
        Args:
            context (dict): The initial context containing at minimum 'text'
            
        Returns:
            dict: The final result after all processing stages
        """
        for stage in self.stages:
            try:
                context = stage.process(context)
            except Exception as e:
                logger.error(f"Error in pipeline stage {stage.__class__.__name__}: {str(e)}")
                if context.get('progress_callback'):
                    context['progress_callback']({
                        'stage': 'error',
                        'message': f"Error in {stage.__class__.__name__}: {str(e)}",
                        'percent': 0
                    })
                raise
                
        return context

class PipelineStage:
    """Base class for all pipeline stages"""
    
    def __init__(self, debate_id=None):
        self.debate_id = debate_id
    
    def process(self, context):
        """
        Process the input context and return updated context
        
        Args:
            context (dict): The input context
            
        Returns:
            dict: The updated context
        """
        # Base implementation does nothing
        return context
    
    def update_progress(self, context, status):
        """Helper method to update progress if callback exists"""
        if context.get('progress_callback'):
            context['progress_callback'](status)

class InitialAnalysisStage(PipelineStage):
    """Stage for initial analysis of the debate text"""
    
    def process(self, context):
        # Extract required data from context
        text = context['text']
        debate_id = context.get('debate_id')
        
        # Update progress
        self.update_progress(context, {
            'stage': 'analysis', 
            'percent': 10, 
            'message': 'Identifying participants and arguments...'
        })
        
        # Expected tags for validation
        analysis_expected_tags = ['debate_title', 'p1', 'p2', 's1', 's2', 'complexity']
        
        # Make LLM call for initial analysis
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
            user_update_callback=lambda data: self.update_progress(context, data)
        )
        
        # Extract key information
        from .analysis import extract_tag
        belligerent_1 = extract_tag('p1', analysis)
        belligerent_2 = extract_tag('p2', analysis)
        summary_1 = extract_tag('s1', analysis)
        summary_2 = extract_tag('s2', analysis)
        debate_title = extract_tag('debate_title', analysis)
        
        # Update progress with extracted information
        self.update_progress(context, {
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
        self.update_progress(context, {
            'stage': 'participants', 
            'percent': 30, 
            'message': f'Identified participants: {belligerent_1} vs {belligerent_2}',
            'content_type': 'participants',
            'content_snippet': f"{belligerent_1}: {summary_1[:100]}...\n\n{belligerent_2}: {summary_2[:100]}..."
        })
        
        # Anonymize the analysis for next stages
        anonymized_analysis = re.sub(r'<p1>.*?</p1>', 'P1', analysis)
        anonymized_analysis = re.sub(r'<p2>.*?</p2>', 'P2', anonymized_analysis)
        
        # Update context with results
        context.update({
            'analysis': analysis,
            'anonymized_analysis': anonymized_analysis,
            'belligerent_1': belligerent_1,
            'belligerent_2': belligerent_2,
            'summary_1': summary_1,
            'summary_2': summary_2,
            'title': debate_title
        })
        
        return context

class EvaluationStage(PipelineStage):
    """Stage for evaluating the debate arguments"""
    
    def process(self, context):
        # Extract required data from context
        anonymized_analysis = context['anonymized_analysis']
        debate_id = context.get('debate_id')
        
        # Update progress
        self.update_progress(context, {
            'stage': 'evaluation', 
            'percent': 40, 
            'message': 'Evaluating arguments...'
        })
        
        # Expected tags for validation
        evaluation_expected_tags = ['argument_map', 'direct_interactions', 'decisive_factors', 'uncertainties']
        
        # Make LLM call for evaluation
        evaluation = make_llm_call(
            load_prompt('evaluate.txt').format(structured_arguments=anonymized_analysis),
            debate_id=debate_id,
            prompt_name='evaluate',
            expected_tags=evaluation_expected_tags,
            user_update_callback=lambda data: self.update_progress(context, data)
        )
        
        # Extract a snippet of the evaluation and send it
        try:
            from .analysis import extract_tag, parse_evaluation_table
            eval_snippet = extract_tag('argument_map', evaluation)
            
            # Parse the argument map into a more readable format
            parsed_tables = parse_evaluation_table(evaluation)
            if parsed_tables and len(parsed_tables) > 0:
                # Format the first table in a more readable way
                table = parsed_tables[0]
                readable_snippet = f"Topic: {table['topic']}\n\n"
                readable_snippet += f"P1's Argument: {table['p1_argument'][:100]}...\n\n"
                readable_snippet += f"P2's Argument: {table['p2_argument'][:100]}...\n\n"
                readable_snippet += f"Outcome: {table['outcome']}"
                
                self.update_progress(context, {
                    'stage': 'evaluation_progress', 
                    'percent': 60, 
                    'message': 'Arguments evaluated',
                    'content_type': 'evaluation',
                    'content_snippet': readable_snippet
                })
            else:
                # Fall back to the raw XML if parsing fails
                self.update_progress(context, {
                    'stage': 'evaluation_progress', 
                    'percent': 60, 
                    'message': 'Arguments evaluated',
                    'content_type': 'evaluation',
                    'content_snippet': eval_snippet[:200] + "..."
                })
        except Exception as e:
            logger.error(f"Error formatting evaluation snippet: {str(e)}")
            # Still try to send a basic update if formatting fails
            try:
                eval_snippet = extract_tag('argument_map', evaluation)
                self.update_progress(context, {
                    'stage': 'evaluation_progress', 
                    'percent': 60, 
                    'message': 'Arguments evaluated',
                    'content_type': 'evaluation',
                    'content_snippet': eval_snippet[:200] + "..."
                })
            except:
                pass
        
        # Update context with results
        context['evaluation'] = evaluation
        
        return context

class JudgmentStage(PipelineStage):
    """Stage for determining the final judgment"""
    
    def process(self, context):
        # Extract required data from context
        evaluation = context['evaluation']
        debate_id = context.get('debate_id')
        
        # Update progress
        self.update_progress(context, {
            'stage': 'judgment', 
            'percent': 70, 
            'message': 'Determining final judgment...'
        })
        
        # Expected tags for validation
        judgment_expected_tags = ['winner', 'reasoning', 'strength', 'strengthening_advice']
        
        # Make LLM call for judgment
        judgment = make_llm_call(
            load_prompt('judge.txt').format(evaluations=evaluation),
            debate_id=debate_id,
            prompt_name='judge',
            expected_tags=judgment_expected_tags,
            user_update_callback=lambda data: self.update_progress(context, data)
        )
        
        # Extract winner but don't send it as a snippet
        try:
            from .analysis import extract_tag
            winner = extract_tag('winner', judgment)
            
            # Update progress without revealing the winner
            self.update_progress(context, {
                'stage': 'judgment_progress', 
                'percent': 80, 
                'message': 'Judgment complete',
                'content_type': 'judgment',
                'content_snippet': 'The final judgment has been determined. You will see the results on the next page.'
            })
            
            # Update context with results
            context['judgment'] = judgment
            context['winner'] = winner
            
        except Exception as e:
            logger.error(f"Error extracting judgment data: {str(e)}")
            raise
        
        return context

class FormattingStage(PipelineStage):
    """Stage for formatting the results for better readability"""
    
    def process(self, context):
        # Extract required data from context
        evaluation = context['evaluation']
        judgment = context['judgment']
        debate_id = context.get('debate_id')
        
        # Update progress
        self.update_progress(context, {
            'stage': 'formatting', 
            'percent': 85, 
            'message': 'Formatting results...'
        })
        
        # Format the evaluation for better readability
        evaluation_formatted = make_llm_call(
            load_prompt('format_evaluation.txt').format(text=evaluation),
            role='copywriter',
            debate_id=debate_id,
            prompt_name='format_evaluation',
            user_update_callback=lambda data: self.update_progress(context, data)
        )
        
        # Format the judgment for better readability
        judgment_formatted = make_llm_call(
            load_prompt('format_judgment.txt').format(text=judgment),
            role='copywriter',
            debate_id=debate_id,
            prompt_name='format_judgment',
            user_update_callback=lambda data: self.update_progress(context, data)
        )
        
        # Update context with formatted results
        context['evaluation_formatted'] = evaluation_formatted
        context['judgment_formatted'] = judgment_formatted
        
        # Final progress update
        self.update_progress(context, {
            'stage': 'processing_complete', 
            'percent': 100, 
            'message': 'Analysis complete!'
        })
        
        return context 