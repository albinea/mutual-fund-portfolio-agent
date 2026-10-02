from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0003_chatmessage_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="ragquestionjob",
            name="user_id",
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True),
        ),
    ]
