from django.core.management.base import BaseCommand
from debate.models import CreditBalance, IPCreditUsage

class Command(BaseCommand):
    help = 'Resets all credit balances to their default values'

    def handle(self, *args, **options):
        # Reset global credit balance
        global_balance, _ = CreditBalance.objects.get_or_create(id=1)
        global_balance.balance = 10.0
        global_balance.save()
        
        # Reset all IP credit usage
        IPCreditUsage.objects.all().update(credits_used=0)
        
        self.stdout.write(self.style.SUCCESS('Successfully reset all credit balances')) 