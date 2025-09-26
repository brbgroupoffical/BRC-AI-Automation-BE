from rest_framework import serializers
from .validators import validate_pdf_extension, validate_pdf_mime, validate_file_size
from .models import GRNAutomation, AutomationStep


class AutomationUploadSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)
    filename = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = GRNAutomation
        fields = ("id", "file", "filename", "status", "case_type", "created_at", "completed_at")
        read_only_fields = ("id", "status", "created_at", "completed_at")

    def get_filename(self, obj):
        return obj.original_filename or (obj.file.name.split("/")[-1] if obj.file else None)

    def validate_file(self, value):
        validate_pdf_extension(value)
        validate_pdf_mime(value)
        validate_file_size(value)
        return value

    def create(self, validated_data):
        user = self.context["request"].user
        uploaded_file = validated_data.pop("file")
        
        # ✅ use case_type from context, not from validated_data
        case_type = self.context.get("case_type", GRNAutomation.CaseType.ONE_TO_ONE)

        automation = GRNAutomation.objects.create(
            user=user,
            file=uploaded_file,
            original_filename=uploaded_file.name,
            case_type=case_type,
        )

        AutomationStep.objects.create(
            automation=automation,
            step_name=AutomationStep.Step.UPLOAD,
            status=AutomationStep.Status.SUCCESS,
            message="File uploaded successfully"
        )

        return automation


class AutomationStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutomationStep
        fields = ("id", "step_name", "status", "updated_at", "message")


class GRNAutomationSerializer(serializers.ModelSerializer):
    steps = AutomationStepSerializer(many=True, read_only=True)
    filename = serializers.SerializerMethodField()

    class Meta:
        model = GRNAutomation
        fields = ("id", "filename", "status", "case_type", "created_at", "completed_at", "steps")

    def get_filename(self, obj):
        return obj.original_filename or (obj.file.name.split("/")[-1] if obj.file else None)


class VendorCodeSerializer(serializers.Serializer):
    vendor_code = serializers.CharField(required=True, max_length=50)


class GRNMatchRequestSerializer(serializers.Serializer):
    vendor_code = serializers.CharField(required=True, max_length=50)
    grn_po = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=True,
        allow_empty=False
    )

