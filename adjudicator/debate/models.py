from django.db import models
from decimal import Decimal

class Debate(models.Model):
    class ApprovalStatus(models.TextChoices):
        APPROVED = 'approved', 'Approved'
        DISAPPROVED = 'disapproved', 'Disapproved'
    
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
    evaluation_approval = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        null=True,
        blank=True
    )
    judgment_approval = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        null=True,
        blank=True
    )
    evaluation_approvals = models.IntegerField(default=0)
    evaluation_disapprovals = models.IntegerField(default=0)
    judgment_approvals = models.IntegerField(default=0)
    judgment_disapprovals = models.IntegerField(default=0)
    title = models.CharField(max_length=255, null=True, blank=True)
    evaluation_formatted = models.TextField(null=True, blank=True)
    judgment_formatted = models.TextField(null=True, blank=True)

    @property
    def evaluation_approval_score(self):
        return self.evaluation_approvals - self.evaluation_disapprovals
        
    @property
    def judgment_approval_score(self):
        return self.judgment_approvals - self.judgment_disapprovals

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

class LLMInteraction(models.Model):
    debate = models.ForeignKey(Debate, on_delete=models.CASCADE, related_name='llm_interactions')
    timestamp = models.DateTimeField(auto_now_add=True)
    prompt_name = models.CharField(max_length=100)  # e.g., 'analyze', 'evaluate', 'judge'
    prompt_text = models.TextField()
    response = models.TextField()
    model_used = models.CharField(max_length=100)  # e.g., 'deepseek-chat', 'gemini-2.0-flash-exp'
    success = models.BooleanField(default=True)
    error_message = models.TextField(null=True, blank=True)
    
    class Meta:
        ordering = ['timestamp'] 

class ApprovalRecord(models.Model):
    debate = models.ForeignKey(Debate, on_delete=models.CASCADE)
    ip_address = models.GenericIPAddressField()
    field = models.CharField(max_length=20)  # 'evaluation' or 'judgment'
    value = models.CharField(max_length=20)  # 'approved' or 'disapproved'
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('debate', 'ip_address', 'field') 

class IPCreditUsage(models.Model):
    ip_address = models.GenericIPAddressField(primary_key=True)
    credits_used = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    last_updated = models.DateTimeField(auto_now=True)

    @classmethod
    def can_use_credits(cls, ip_address, amount):
        usage, created = cls.objects.get_or_create(ip_address=ip_address)
        return usage.credits_used + Decimal(str(amount)) <= 15

    @classmethod
    def add_usage(cls, ip_address, amount):
        usage, created = cls.objects.get_or_create(ip_address=ip_address)
        usage.credits_used += Decimal(str(amount))
        usage.save()
        return usage.credits_used 