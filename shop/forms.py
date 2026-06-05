from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from .models import Category, Product, SiteContent, StaffProfile


class RegisterForm(UserCreationForm):
    email = forms.EmailField(label="Email")
    first_name = forms.CharField(label="Имя", max_length=80)

    class Meta:
        model = User
        fields = ["username", "first_name", "email", "password1", "password2"]


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(label="Email аккаунта")


class PasswordResetConfirmForm(forms.Form):
    verification_code = forms.CharField(label="Код из письма", max_length=6)
    password1 = forms.CharField(label="Новый пароль", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Повторите пароль", widget=forms.PasswordInput)

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data["password2"]
        if password1 and password1 != password2:
            raise forms.ValidationError("Пароли не совпадают.")
        validate_password(password2, self.user)
        return password2


class CheckoutForm(forms.Form):
    customer_name = forms.CharField(label="Имя получателя", max_length=160)
    phone = forms.CharField(label="Телефон", max_length=40)
    email = forms.EmailField(label="Email для чека")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and user.is_authenticated:
            self.fields["customer_name"].initial = user.get_full_name() or user.username
            self.fields["email"].initial = user.email
            profile = getattr(user, "customer_profile", None)
            if profile:
                self.fields["phone"].initial = profile.phone


class AdminProductForm(forms.ModelForm):
    attributes = forms.JSONField(
        label="Характеристики JSON",
        required=False,
        widget=forms.Textarea(attrs={"rows": 8}),
    )

    class Meta:
        model = Product
        fields = [
            "category",
            "name",
            "slug",
            "brand",
            "description",
            "price",
            "old_price",
            "image",
            "stock",
            "color",
            "memory",
            "screen_size",
            "attributes",
            "is_featured",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
        }

    def clean_attributes(self):
        return self.cleaned_data.get("attributes") or {}


class AdminCategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "slug", "description", "sort_order", "is_active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }


class SiteContentForm(forms.ModelForm):
    class Meta:
        model = SiteContent
        fields = ["key", "title", "block_type", "body", "is_active"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 8}),
        }


class AdminUserCreateForm(UserCreationForm):
    first_name = forms.CharField(label="Имя", max_length=80, required=False)
    email = forms.EmailField(label="Email")
    role = forms.ChoiceField(label="Роль", choices=StaffProfile.Role.choices)

    class Meta:
        model = User
        fields = ["username", "first_name", "email", "role", "password1", "password2"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Пользователь с такой почтой уже существует.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get("first_name", "")
        user.email = self.cleaned_data["email"]
        user.is_staff = True
        if commit:
            user.save()
            StaffProfile.objects.create(user=user, role=self.cleaned_data["role"], is_active=True)
        return user


class AdminStaffProfileForm(forms.ModelForm):
    first_name = forms.CharField(label="Имя", max_length=80, required=False)
    email = forms.EmailField(label="Email")
    is_user_active = forms.BooleanField(label="Аккаунт активен", required=False)

    class Meta:
        model = StaffProfile
        fields = ["role", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["first_name"].initial = self.instance.user.first_name
            self.fields["email"].initial = self.instance.user.email
            self.fields["is_user_active"].initial = self.instance.user.is_active

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        current_user_id = self.instance.user_id if self.instance and self.instance.pk else None
        exists = User.objects.filter(email__iexact=email).exclude(id=current_user_id).exists()
        if exists:
            raise forms.ValidationError("Пользователь с такой почтой уже существует.")
        return email

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user
        user.first_name = self.cleaned_data.get("first_name", "")
        user.email = self.cleaned_data["email"]
        user.is_active = self.cleaned_data.get("is_user_active", False)
        if commit:
            user.save(update_fields=["first_name", "email", "is_active"])
            profile.save()
        return profile
