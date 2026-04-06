from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Extended user model with storage quota tracking."""

    email = models.EmailField(unique=True)
    storage_quota_bytes = models.BigIntegerField(default=2 * 1024**3)  # 2 GB
    used_storage_bytes = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "accounts_user"

    def has_storage_quota(self, file_size_bytes: int) -> bool:
        return (self.used_storage_bytes + file_size_bytes) <= self.storage_quota_bytes

    def consume_storage(self, file_size_bytes: int) -> None:
        User.objects.filter(pk=self.pk).update(
            used_storage_bytes=models.F("used_storage_bytes") + file_size_bytes
        )

    def release_storage(self, file_size_bytes: int) -> None:
        User.objects.filter(pk=self.pk).update(
            used_storage_bytes=models.F("used_storage_bytes") - file_size_bytes
        )
