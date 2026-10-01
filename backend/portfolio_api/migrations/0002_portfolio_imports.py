import datetime

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio_api", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PortfolioImport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_id", models.CharField(db_index=True, max_length=255)),
                ("source_file_name", models.CharField(max_length=255)),
                ("source_format", models.CharField(choices=[("csv", "CSV"), ("xlsx", "XLSX")], max_length=10)),
                ("snapshot_date", models.DateField(default=datetime.date.today)),
                ("imported_at", models.DateTimeField(auto_now_add=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["-imported_at"]},
        ),
        migrations.CreateModel(
            name="ImportedHolding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fund_name", models.CharField(max_length=255)),
                ("category", models.CharField(default="Imported", max_length=100)),
                ("units", models.DecimalField(decimal_places=4, default=0, max_digits=18)),
                ("invested_amount", models.DecimalField(decimal_places=2, max_digits=18)),
                ("current_value", models.DecimalField(decimal_places=2, max_digits=18)),
                ("portfolio_import", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="holdings", to="portfolio_api.portfolioimport")),
            ],
        ),
    ]
