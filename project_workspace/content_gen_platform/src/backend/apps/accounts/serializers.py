from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ("username", "email", "password", "password2")

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "两次密码不一致"})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password2")
        user = User.objects.create_user(**validated_data)
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    storage_used_mb = serializers.SerializerMethodField()
    storage_quota_mb = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "email", "storage_used_mb", "storage_quota_mb", "created_at")
        read_only_fields = ("id", "email", "storage_used_mb", "storage_quota_mb", "created_at")

    def get_storage_used_mb(self, obj):
        return round(obj.used_storage_bytes / (1024**2), 2)

    def get_storage_quota_mb(self, obj):
        return round(obj.storage_quota_bytes / (1024**2), 2)
