from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

class RegisterSerializer(serializers.ModelSerializer):
    password1 = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True, min_length=8)

    email = serializers.EmailField(
        validators=[UniqueValidator(queryset=User.objects.all(), message=_("A user with that email already exists."))]
    )
    username = serializers.CharField(
        validators=[UniqueValidator(queryset=User.objects.all(), message=_("A user with that username already exists."))]
    )

    class Meta:
        model = User
        fields = ("id", "email", "username", "password1", "password2")
        read_only_fields = ("id",)

    def validate_email(self, value):
        value = value.strip().lower()
        # Only allow emails from the specific domain
        #allowed_domain = "@brc.com.sa"
        #if not value.endswith(allowed_domain):
        #    raise serializers.ValidationError(_("Invalid email"))
        return value

    def validate(self, attrs):
        if attrs.get("password1") != attrs.get("password2"):
            raise serializers.ValidationError({"password2": _("Passwords do not match.")})
        validate_password(attrs.get("password1"))
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password1")
        validated_data.pop("password2", None)
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "username")

class LoginSerializer(TokenObtainPairSerializer):
    """Allow username OR email in the username field."""
    username_field = User.USERNAME_FIELD

    def validate(self, attrs):
        # `username` may actually be username or email
        login = attrs.get(self.username_field)
        password = attrs.get("password")
        if login:
            login = login.strip()
        # Replace username with the actual username if email was provided
        try:
            user = User.objects.get(models.Q(username=login) | models.Q(email__iexact=login))
            attrs[self.username_field] = user.get_username()
        except Exception:
            pass  # Let parent class handle invalid user
        data = super().validate(attrs)
        # Attach simple user profile
        data["user"] = UserSerializer(self.user).data
        return data