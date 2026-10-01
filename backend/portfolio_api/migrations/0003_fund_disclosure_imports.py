import datetime

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio_api", "0002_portfolio_imports"),
    ]

    operations = [
        migrations.CreateModel(
            name="FundDisclosureImport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_file_name", models.CharField(max_length=255)),
                ("source_format", models.CharField(choices=[("csv", "CSV"), ("xlsx", "XLSX")], max_length=10)),
                ("source_name", models.CharField(default="Manual disclosure upload", max_length=255)),
                ("source_url", models.URLField(blank=True)),
                ("disclosure_date", models.DateField(default=datetime.date.today)),
                ("imported_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-disclosure_date", "-imported_at"]},
        ),
        migrations.CreateModel(
            name="FundDisclosureHolding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fund_name", models.CharField(max_length=255)),
                ("normalized_fund_name", models.CharField(db_index=True, max_length=255)),
                ("company_name", models.CharField(max_length=255)),
                ("isin", models.CharField(blank=True, max_length=32)),
                ("sector", models.CharField(blank=True, max_length=120)),
                ("holding_weight", models.DecimalField(decimal_places=4, max_digits=8)),
                ("disclosure_import", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="holdings", to="portfolio_api.funddisclosureimport")),
            ],
        ),
    ]
