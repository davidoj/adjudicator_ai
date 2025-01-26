from django.shortcuts import render, redirect
from django.contrib import messages
from ..models import Debate, CreditBalance
from ..services.analysis import perform_analysis, parse_evaluation_table
from decimal import Decimal
import logging

logger = logging.getLogger('llm_calls')

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

def home(request):
    if request.method == 'POST':
        text = request.POST.get('debate_text')
        
        try:
            result = analyze_debate(text)
        except ValueError as e:
            messages.error(request, str(e))
            return render(request, 'debate/home.html', {
                'credits': 999,
                'debate_text': text,
                'error': str(e)
            })
        except Exception as e:
            messages.error(request, "An unexpected error occurred during analysis. Please try again.")
            return render(request, 'debate/home.html', {
                'credits': 999,
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
            credit_cost=Decimal('1.0'),
            analysis=result['analysis'],
            evaluation=result['evaluation'],
            judgment=result['judgment']
        )
        
        return redirect('result', debate_id=debate.id)
    
    return render(request, 'debate/home.html', {'credits': 999})

def result(request, debate_id):
    debate = Debate.objects.get(id=debate_id)
    evaluation_tables = parse_evaluation_table(debate.evaluation, debate.judgment)
    return render(request, 'debate/result.html', {
        'debate': debate,
        'evaluation_tables': evaluation_tables,
        'parse_failed': evaluation_tables is None
    }) 