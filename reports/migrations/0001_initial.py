from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("plants", "0004_taskresult"),
    ]

    operations = [
        migrations.CreateModel(
            name="Report",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("period", models.CharField(choices=[("DAILY", "Daily"), ("WEEKLY", "Weekly"), ("MONTHLY", "Monthly")], max_length=20)),
                ("start_at", models.DateTimeField()),
                ("end_at", models.DateTimeField()),
                ("file_name", models.CharField(max_length=255)),
                ("file_path", models.CharField(max_length=600)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("SUCCESS", "Success"), ("FAILURE", "Failure")], default="PENDING", max_length=20)),
                ("error_message", models.TextField(blank=True, null=True)),
                ("airflow_dag_id", models.CharField(blank=True, max_length=255, null=True)),
                ("airflow_run_id", models.CharField(blank=True, max_length=255, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reports", to=settings.AUTH_USER_MODEL)),
                ("plant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="reports", to="plants.solarplant")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]

