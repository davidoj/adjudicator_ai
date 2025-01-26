from django.db import models
from decimal import Decimal

class Debate(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    original_text = models.TextField()
    belligerent_1 = models.CharField(max_length=255)
    belligerent_2 = models.CharField(max_length=255)
    summary_1 = models.TextField()
    summary_2 = models.TextField()
    winner = models.CharField(max_length=255)
    credit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    # Add new fields for detailed analysis
    analysis = models.TextField(null=True, blank=True)
    evaluation = models.TextField(null=True, blank=True)
    judgment = models.TextField(null=True, blank=True)

class CreditBalance(models.Model):
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=10.0)  # Start with 10 free credits
    last_updated = models.DateTimeField(auto_now=True)

    @classmethod
    def get_credits(cls):
        balance, created = cls.objects.get_or_create(id=1)
        return balance.balance

    @classmethod
    def deduct_credits(cls, amount):
        balance = cls.objects.get(id=1)
        if balance.balance >= Decimal(str(amount)):  # Convert float to Decimal
            balance.balance -= Decimal(str(amount))
            balance.save()
            return True
        return False 