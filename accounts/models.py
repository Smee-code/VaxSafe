from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrator'
        STAFF = 'STAFF', 'Health Staff'
        PERSONNEL = 'PERSONNEL', 'Authorized Personnel'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STAFF)
    position = models.CharField(max_length=100, blank=True, help_text='Job title, e.g. Nurse, Municipal Health Officer.')
    contact_number = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ['last_name', 'first_name', 'username']

    def __str__(self):
        return self.get_full_name() or self.username

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    @property
    def is_admin(self):
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def is_health_staff(self):
        return self.role == self.Role.STAFF

    @property
    def is_personnel(self):
        return self.role == self.Role.PERSONNEL and not self.is_superuser

    @property
    def can_manage_clinical(self):
        """Admins and health staff can create and edit patient, vaccination and inventory records."""
        return self.is_admin or self.is_health_staff
