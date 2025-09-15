import os
from django.core.exceptions import ValidationError
from django.conf import settings


ALLOWED_EXTENSIONS = ('.pdf',)
ALLOWED_MIME_TYPES = ('application/pdf',)


def validate_pdf_extension(value):
    name = value.name
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError('Invalid file extension. Only PDF files are allowed.')


def validate_pdf_mime(file_obj):
    # file_obj should be an UploadedFile
    content_type = getattr(file_obj, 'content_type', None)
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        raise ValidationError('Invalid MIME type. Only application/pdf allowed.')


def validate_file_size(file_obj):
    max_size = getattr(settings, 'MAX_UPLOAD_SIZE', 10 * 1024 * 1024)
    if file_obj.size > max_size:
        raise ValidationError(f'File too large. Limit is {max_size} bytes.')