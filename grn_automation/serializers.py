from rest_framework import serializers
from django.contrib.auth.models import User
from .models import GRNAutomation
from .validators import validate_pdf_extension, validate_pdf_mime, validate_file_size
from rest_framework import serializers
from .models import GRNAutomation, AutomationStep


class AutomationUploadSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)
    file_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = GRNAutomation
        fields = ("id", "file", "file_url", "created_at", "completed_at")
        read_only_fields = ("id", "created_at", "completed_at")

    def get_file_url(self, obj):
        return obj.file.url if obj.file else None

    def validate_file(self, value):
        validate_pdf_extension(value)
        validate_pdf_mime(value)
        validate_file_size(value)
        return value

    def create(self, validated_data):
        user = self.context["request"].user
        automation = GRNAutomation.objects.create(user=user, **validated_data)

        # Prepopulate steps
        pipeline_steps = [
            "upload",
            "sap_login",
            "extraction",
            "fetch_open_grn",
            "filter_grn",
            "validation",
            "booked",
        ]
        for step in pipeline_steps:
            AutomationStep.objects.create(automation=automation, step_name=step)

        # Mark upload as SUCCESS immediately
        AutomationStep.objects.filter(
            automation=automation, step_name="upload"
        ).update(status=AutomationStep.Status.SUCCESS)

        return automation
    
        # 🔹 Always use a dummy user for now
        # user, _ = User.objects.get_or_create(username="testuser", defaults={"password": "testpass"})
        # return GRNAutomation.objects.create(user=user, **validated_data)

        # # Attach a dummy user for now (replace with request.user later)
        # user = self.context['request'].user if self.context['request'].user.is_authenticated else None
        # return GRNAutomation.objects.create(user=user, **validated_data)

        
class AutomationStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutomationStep
        fields = ("id", "step_name", "status", "updated_at", "error_message")


class GRNAutomationSerializer(serializers.ModelSerializer):
    steps = AutomationStepSerializer(many=True, read_only=True)

    class Meta:
        model = GRNAutomation
        fields = ("id", "file", "created_at", "completed_at", "steps")
