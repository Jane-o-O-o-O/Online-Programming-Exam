from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="error_message",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="notification",
            name="recipient",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AlterField(
            model_name="notification",
            name="category",
            field=models.CharField(
                choices=[("email", "邮件"), ("system", "系统"), ("exam", "考试"), ("security", "安全")],
                default="system",
                max_length=20,
            ),
        ),
    ]
