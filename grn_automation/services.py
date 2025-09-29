from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q
from .models import GRNAutomation


def get_total_stats(user=None, days: int = 1):
    since = timezone.now() - timedelta(days=days)
    qs = GRNAutomation.objects.filter(created_at__gte=since)

    # if user is provided and not staff → filter to that user
    if user and not user.is_staff:
        qs = qs.filter(user=user)

    return qs.aggregate(
        total_count=Count("id"),
        total_success=Count("id", filter=Q(status=GRNAutomation.Status.COMPLETED)),
        total_failed=Count("id", filter=Q(status=GRNAutomation.Status.FAILED)),
    )


def get_case_type_stats(case_type: str, user=None, days: int = 1):
    since = timezone.now() - timedelta(days=days)
    qs = GRNAutomation.objects.filter(created_at__gte=since, case_type=case_type)

    # if user is provided and not staff → filter to that user
    if user and not user.is_staff:
        qs = qs.filter(user=user)

    success_count = qs.filter(status=GRNAutomation.Status.COMPLETED).count()
    failed_count = qs.filter(status=GRNAutomation.Status.FAILED).count()
    total_count = qs.count()   # 👈 count everything

    return {
        "case_type": case_type,
        "success": success_count,
        "failed": failed_count,
        "total": total_count,
    }
