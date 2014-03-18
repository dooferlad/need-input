from django.db import models
from django.conf import settings

class DefaultFilters(models.Model):
    from_date = models.DateField(
        'Date to start displaying data after',
        default=settings.DEFAULT_START_DATE)
    to_date = models.DateField(
        'Date to stop displaying data before',
        default=settings.DEFAULT_END_DATE)
