from django.core.management.base import BaseCommand
import json
from datetime import datetime
from debate.models import Debate, LLMInteraction

class Command(BaseCommand):
    help = 'Export all debates and their LLM interactions to JSON files'

    def handle(self, *args, **options):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Export debates
        debates_data = []
        for debate in Debate.objects.all():
            debates_data.append({
                'id': debate.id,
                'created_at': debate.created_at.isoformat(),
                'original_text': debate.original_text,
                'belligerent_1': debate.belligerent_1,
                'belligerent_2': debate.belligerent_2,
                'summary_1': debate.summary_1,
                'summary_2': debate.summary_2,
                'winner': debate.winner,
                'credit_cost': str(debate.credit_cost),  # Convert Decimal to string
                'analysis': debate.analysis,
                'evaluation': debate.evaluation,
                'judgment': debate.judgment,
                'evaluation_approval': debate.evaluation_approval,
                'judgment_approval': debate.judgment_approval
            })
        
        with open(f'debates_{timestamp}.json', 'w', encoding='utf-8') as f:
            json.dump(debates_data, f, indent=2, ensure_ascii=False)
        
        # Export LLM interactions
        interactions_data = []
        for interaction in LLMInteraction.objects.all():
            interactions_data.append({
                'debate_id': interaction.debate.id,
                'timestamp': interaction.timestamp.isoformat(),
                'prompt_name': interaction.prompt_name,
                'prompt_text': interaction.prompt_text,
                'response': interaction.response,
                'model_used': interaction.model_used,
                'success': interaction.success,
                'error_message': interaction.error_message
            })
        
        with open(f'llm_interactions_{timestamp}.json', 'w', encoding='utf-8') as f:
            json.dump(interactions_data, f, indent=2, ensure_ascii=False)
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully exported debates to debates_{timestamp}.json and '
                f'LLM interactions to llm_interactions_{timestamp}.json'
            )
        ) 