from rest_framework import serializers

class AttachmentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
