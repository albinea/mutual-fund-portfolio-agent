from datetime import date

from django.db import models


class PortfolioImport(models.Model):
    """Metadata for a parsed portfolio statement; the original file is not retained."""

    class SourceFormat(models.TextChoices):
        CSV = "csv", "CSV"
        XLSX = "xlsx", "XLSX"

    user_id = models.CharField(max_length=255, db_index=True)
    source_file_name = models.CharField(max_length=255)
    source_format = models.CharField(max_length=10, choices=SourceFormat.choices)
    snapshot_date = models.DateField(default=date.today)
    imported_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-imported_at"]


class ImportedHolding(models.Model):
    """A normalized fund holding produced from one portfolio statement import."""

    portfolio_import = models.ForeignKey(
        PortfolioImport,
        on_delete=models.CASCADE,
        related_name="holdings",
    )
    fund_name = models.CharField(max_length=255)
    category = models.CharField(max_length=100, default="Imported")
    units = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    invested_amount = models.DecimalField(max_digits=18, decimal_places=2)
    current_value = models.DecimalField(max_digits=18, decimal_places=2)


class FundDisclosureImport(models.Model):
    """Metadata for a manually uploaded, dated mutual-fund disclosure dataset."""

    class SourceFormat(models.TextChoices):
        CSV = "csv", "CSV"
        XLSX = "xlsx", "XLSX"

    source_file_name = models.CharField(max_length=255)
    source_format = models.CharField(max_length=10, choices=SourceFormat.choices)
    source_name = models.CharField(max_length=255, default="Manual disclosure upload")
    source_url = models.URLField(blank=True)
    disclosure_date = models.DateField(default=date.today)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-disclosure_date", "-imported_at"]


class FundDisclosureHolding(models.Model):
    """A company/security position and its weight in a fund disclosure snapshot."""

    disclosure_import = models.ForeignKey(
        FundDisclosureImport,
        on_delete=models.CASCADE,
        related_name="holdings",
    )
    fund_name = models.CharField(max_length=255)
    normalized_fund_name = models.CharField(max_length=255, db_index=True)
    company_name = models.CharField(max_length=255)
    isin = models.CharField(max_length=32, blank=True)
    sector = models.CharField(max_length=120, blank=True)
    holding_weight = models.DecimalField(max_digits=8, decimal_places=4)


class WatchlistItem(models.Model):
    """A development-only watchlist keyed by the API user identity."""

    user_id = models.CharField(max_length=255, db_index=True)
    symbol = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "symbol"],
                name="unique_user_watchlist_symbol",
            )
        ]
        ordering = ["-created_at"]
