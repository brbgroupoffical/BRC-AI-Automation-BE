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
    file_url = serializers.SerializerMethodField()
    user_email = serializers.EmailField(source="user.email", read_only=True) 
    
    class Meta:
        model = GRNAutomation
        fields = (
            "id",
            "filename",
            "file_url",  # Added this field
            "status",
            "case_type",
            "created_at",
            "completed_at",
            "steps",
            "user_email",  
        )
    
    def get_filename(self, obj):
        return obj.original_filename or (obj.file.name.split("/")[-1] if obj.file else None)
    
    def get_file_url(self, obj):
        """Return the full URL to access the PDF file"""
        if obj.file:
            request = self.context.get('request')
            if request is not None:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None
    

class VendorCodeSerializer(serializers.Serializer):
    vendor_code = serializers.CharField(required=True, max_length=50)


class GRNMatchRequestSerializer(serializers.Serializer):
    vendor_code = serializers.CharField(required=True, max_length=50)
    grn_po = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=True,
        allow_empty=False
    )


class TotalStatsSerializer(serializers.Serializer):
    total_count = serializers.IntegerField()
    total_success = serializers.IntegerField()
    total_failed = serializers.IntegerField()


class CaseTypeStatsSerializer(serializers.Serializer):
    case_type = serializers.CharField()
    success = serializers.IntegerField()
    failed = serializers.IntegerField()
    total = serializers.IntegerField()


# serializers.py
from rest_framework import serializers
from .models import GRNAutomation, ValidationResult, DocumentLine
from decimal import Decimal


class DocumentLineSerializer(serializers.ModelSerializer):
    """Serializer for DocumentLine model"""
    
    class Meta:
        model = DocumentLine
        fields = [
            'id',
            'line_num',
            'remaining_open_quantity',
        ]
        read_only_fields = ['id']


class ValidationResultSerializer(serializers.ModelSerializer):
    """Serializer for ValidationResult model"""
    document_lines = DocumentLineSerializer(many=True, read_only=True)
    
    class Meta:
        model = ValidationResult
        fields = [
            'id',
            'automation',
            'invoice_date',
            'validation_status',
            'card_code',
            'doc_entry',
            'doc_date',
            'bpl_id',
            'posting_status',
            'posting_message',
            'document_lines',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'automation', 'created_at', 'updated_at']


class DocumentLineUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating DocumentLine"""
    
    class Meta:
        model = DocumentLine
        fields = ['id', 'line_num', 'remaining_open_quantity']
        read_only_fields = ['id']
    
    def validate_remaining_open_quantity(self, value):
        """Ensure quantity is positive"""
        if value <= 0:
            raise serializers.ValidationError("Remaining open quantity must be greater than 0")
        return value


class ValidationResultUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating ValidationResult.
    Only allows updating: invoice_date, doc_date, and document_lines
    """
    document_lines = DocumentLineUpdateSerializer(many=True, required=False)
    
    class Meta:
        model = ValidationResult
        fields = [
            'invoice_date',
            'doc_date',
            'document_lines',
        ]
    
    def validate(self, attrs):
        """Check if invoice is already posted"""
        instance = self.instance
        
        if instance and instance.posting_status == ValidationResult.PostingStatus.POSTED:
            raise serializers.ValidationError(
                "Cannot update invoice that has already been posted. "
                "Posting status is 'posted'."
            )
        
        return attrs
    
    def update(self, instance, validated_data):
        """Update ValidationResult and related document lines"""
        # Extract document_lines if provided
        document_lines_data = validated_data.pop('document_lines', None)
        
        # Update ValidationResult fields
        instance.invoice_date = validated_data.get('invoice_date', instance.invoice_date)
        instance.doc_date = validated_data.get('doc_date', instance.doc_date)
        instance.save()
        
        # Update document lines if provided
        if document_lines_data is not None:
            # Create a map of existing lines
            existing_lines = {line.id: line for line in instance.document_lines.all()}
            
            for line_data in document_lines_data:
                line_id = line_data.get('id')
                
                if line_id and line_id in existing_lines:
                    # Update existing line
                    doc_line = existing_lines[line_id]
                    doc_line.line_num = line_data.get('line_num', doc_line.line_num)
                    doc_line.remaining_open_quantity = line_data.get(
                        'remaining_open_quantity',
                        doc_line.remaining_open_quantity
                    )
                    doc_line.save()
                elif not line_id:
                    # Create new line (only if id not provided)
                    DocumentLine.objects.create(
                        validation_result=instance,
                        line_num=line_data.get('line_num'),
                        remaining_open_quantity=line_data.get('remaining_open_quantity')
                    )
        
        return instance


class ValidationResultListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing validation results"""
    document_lines_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ValidationResult
        fields = [
            'id',
            'invoice_date',
            'validation_status',
            'card_code',
            'doc_entry',
            'posting_status',
            'posting_message',
            'document_lines_count',
            'created_at',
        ]
        read_only_fields = fields
    
    def get_document_lines_count(self, obj):
        return obj.document_lines.count()