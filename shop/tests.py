import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client
from django.test import TestCase
from django.urls import reverse

from .models import Category, CustomerProfile, Order, PageView, Product, StaffProfile


class CartApiTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Аксессуары", slug="accessories", is_active=True)
        self.product = Product.objects.create(
            category=category,
            name="Тестовый кабель",
            slug="test-cable",
            brand="Test",
            description="Тестовый товар",
            price=Decimal("990"),
            image="img/biggeek-products/product-01.png",
            stock=5,
            is_active=True,
        )

    def request_cart(self, method, payload):
        return self.client.generic(
            method,
            reverse("api_cart"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_patch_quantity_zero_removes_item(self):
        response = self.request_cart("POST", {"product_id": self.product.id, "quantity": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

        response = self.request_cart("PATCH", {"product_id": self.product.id, "quantity": 0})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)
        self.assertEqual(response.json()["items"], [])

    def test_out_of_stock_product_is_not_added_to_cart(self):
        self.product.stock = 0
        self.product.save(update_fields=["stock"])

        response = self.request_cart("POST", {"product_id": self.product.id, "quantity": 1})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Товар скоро в продаже")
        self.assertEqual(self.client.get(reverse("api_cart")).json()["count"], 0)


class CsrfCookieTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Аксессуары", slug="accessories", is_active=True)
        self.product = Product.objects.create(
            category=category,
            name="Тестовый кабель",
            slug="test-cable",
            brand="Test",
            description="Тестовый товар",
            price=Decimal("990"),
            image="img/biggeek-products/product-01.png",
            stock=5,
            is_active=True,
        )

    def assert_sets_csrf_cookie(self, url_name, *args):
        response = self.client.get(reverse(url_name, args=args))
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)

    def test_cart_mutation_pages_set_csrf_cookie(self):
        self.assert_sets_csrf_cookie("home")
        self.assert_sets_csrf_cookie("catalog")
        self.assert_sets_csrf_cookie("product_detail", self.product.slug)
        self.assert_sets_csrf_cookie("cart")


class CheckoutTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Аксессуары", slug="accessories", is_active=True)
        self.product = Product.objects.create(
            category=category,
            name="Тестовый кабель",
            slug="test-cable",
            brand="Test",
            description="Тестовый товар",
            price=Decimal("990"),
            image="img/biggeek-products/product-01.png",
            stock=5,
            is_active=True,
        )
        self.checkout_payload = {
            "customer_name": "Иван Иванов",
            "phone": "+7 700 000 00 00",
            "email": "ivan@example.com",
        }

    def add_to_cart(self):
        response = self.client.generic(
            "POST",
            reverse("api_cart"),
            data=json.dumps({"product_id": self.product.id, "quantity": 1}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)

    @patch("shop.views.process_order_payment.delay", side_effect=Exception("celery unavailable"))
    def test_guest_can_checkout_without_login(self, _delay):
        self.add_to_cart()

        response = self.client.get(reverse("checkout"))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse("checkout"), self.checkout_payload)
        order = Order.objects.get()

        self.assertIsNone(order.user)
        self.assertEqual(order.payment_status, Order.PaymentStatus.WAITING)
        self.assertRedirects(response, reverse("order_payment", args=[order.order_number]))
        self.assertIn(order.id, self.client.session["guest_order_ids"])
        self.assertEqual(self.client.get(reverse("api_cart")).json()["count"], 0)
        self.assertEqual(self.client.get(reverse("order_payment", args=[order.order_number])).status_code, 200)

        response = self.client.post(reverse("order_payment", args=[order.order_number]))
        self.assertRedirects(response, reverse("order_detail", args=[order.order_number]))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertTrue(order.qr_svg)
        self.assertContains(self.client.get(reverse("order_detail", args=[order.order_number])), "Электронный чек")

        other_client = Client()
        blocked_response = other_client.get(reverse("order_detail", args=[order.order_number]))
        self.assertEqual(blocked_response.status_code, 404)
        blocked_response = other_client.get(reverse("order_payment", args=[order.order_number]))
        self.assertEqual(blocked_response.status_code, 404)

    @patch("shop.views.process_order_payment.delay", side_effect=Exception("celery unavailable"))
    def test_authenticated_checkout_stays_in_account_flow(self, _delay):
        user = User.objects.create_user(username="buyer", password="secret", email="buyer@example.com")
        self.client.force_login(user)
        self.add_to_cart()

        response = self.client.post(reverse("checkout"), self.checkout_payload)
        order = Order.objects.get()

        self.assertEqual(order.user, user)
        self.assertRedirects(response, reverse("order_payment", args=[order.order_number]))
        self.assertNotIn("guest_order_ids", self.client.session)
        user.refresh_from_db()
        self.assertEqual(user.customer_profile.phone, self.checkout_payload["phone"])
        self.assertEqual(self.client.get(reverse("api_account")).json()["orders"][0]["url"], reverse("order_detail", args=[order.order_number]))


class AccountProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="profile-buyer",
            password="ProfilePass123",
            email="old@example.com",
            first_name="Старое",
        )
        CustomerProfile.objects.create(user=self.user, phone="+7 700 000 00 00")
        self.client.force_login(self.user)

    def test_account_api_updates_profile_settings(self):
        response = self.client.generic(
            "PATCH",
            reverse("api_account"),
            data=json.dumps(
                {
                    "first_name": "Никита",
                    "last_name": "Покупатель",
                    "email": "new@example.com",
                    "phone": "+7 701 111 22 33",
                    "city": "Алматы",
                    "address": "Пункт выдачи eShop",
                    "marketing_consent": True,
                }
            ),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user"]["name"], "Никита Покупатель")
        self.assertEqual(payload["user"]["phone"], "+7 701 111 22 33")
        self.user.refresh_from_db()
        self.user.customer_profile.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")
        self.assertEqual(self.user.customer_profile.city, "Алматы")
        self.assertTrue(self.user.customer_profile.marketing_consent)

    def test_account_api_rejects_duplicate_email(self):
        User.objects.create_user(username="other-buyer", email="taken@example.com", password="ProfilePass123")

        response = self.client.generic(
            "PATCH",
            reverse("api_account"),
            data=json.dumps(
                {
                    "first_name": "Никита",
                    "email": "taken@example.com",
                    "phone": "+7 701 111 22 33",
                }
            ),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["errors"])


class RegistrationOrderLinkTests(TestCase):
    def create_guest_order(self, email):
        return Order.objects.create(
            user=None,
            status=Order.Status.READY,
            payment_status=Order.PaymentStatus.PAID,
            total=Decimal("1990"),
            customer_name="Гость Покупатель",
            phone="+7 700 111 22 33",
            email=email,
        )

    def test_registration_links_current_session_guest_orders_by_email(self):
        order = self.create_guest_order("guest@example.com")
        unrelated_order = self.create_guest_order("guest@example.com")
        different_email_order = self.create_guest_order("other@example.com")
        session = self.client.session
        session["guest_order_ids"] = [order.id, different_email_order.id]
        session.save()

        response = self.client.post(
            reverse("register"),
            {
                "username": "guest-buyer",
                "first_name": "Гость",
                "email": "guest@example.com",
                "password1": "ComplexPass123",
                "password2": "ComplexPass123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Подтвердите регистрацию")
        self.assertContains(response, self.client.session["pending_registration"]["code"])
        self.assertFalse(User.objects.filter(username="guest-buyer").exists())

        response = self.client.post(
            reverse("register"),
            {
                "registration_step": "verify",
                "verification_code": self.client.session["pending_registration"]["code"],
            },
        )

        user = User.objects.get(username="guest-buyer")
        order.refresh_from_db()
        unrelated_order.refresh_from_db()
        different_email_order.refresh_from_db()

        self.assertRedirects(response, reverse("account"))
        self.assertEqual(order.user, user)
        self.assertIsNone(unrelated_order.user)
        self.assertIsNone(different_email_order.user)
        self.assertEqual(self.client.session["guest_order_ids"], [different_email_order.id])
        account_orders = self.client.get(reverse("api_account")).json()["orders"]
        self.assertEqual([item["number"] for item in account_orders], [order.order_number])

    def test_wrong_registration_code_does_not_create_account(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "guest-buyer",
                "first_name": "Гость",
                "email": "guest@example.com",
                "password1": "ComplexPass123",
                "password2": "ComplexPass123",
            },
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse("register"),
            {
                "registration_step": "verify",
                "verification_code": "000000",
            },
        )

        self.assertContains(response, "Неверный код подтверждения.")
        self.assertFalse(User.objects.filter(username="guest-buyer").exists())


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reset-buyer",
            email="reset@example.com",
            password="OldComplexPass123",
        )

    def test_login_page_has_password_reset_link(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, reverse("password_reset"))
        self.assertContains(response, "Забыли пароль?")

    def test_password_reset_requires_code_and_changes_password(self):
        response = self.client.post(reverse("password_reset"), {"email": "reset@example.com"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Сброс пароля")
        self.assertContains(response, self.client.session["pending_password_reset"]["code"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldComplexPass123"))

        response = self.client.post(
            reverse("password_reset"),
            {
                "password_reset_step": "verify",
                "verification_code": "000000",
                "password1": "NewComplexPass123",
                "password2": "NewComplexPass123",
            },
        )
        self.assertContains(response, "Неверный код подтверждения.")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldComplexPass123"))

        response = self.client.post(
            reverse("password_reset"),
            {
                "password_reset_step": "verify",
                "verification_code": self.client.session["pending_password_reset"]["code"],
                "password1": "NewComplexPass123",
                "password2": "NewComplexPass123",
            },
        )
        self.assertRedirects(response, reverse("login"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewComplexPass123"))
        self.assertNotIn("pending_password_reset", self.client.session)


class ControlAdminTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Аксессуары", slug="accessories", is_active=True)
        self.product = Product.objects.create(
            category=self.category,
            name="Тестовый товар",
            slug="control-product",
            brand="Test",
            description="Товар для админки",
            price=Decimal("1990"),
            image="img/biggeek-products/product-01.png",
            stock=2,
            is_active=True,
        )

    def create_staff_user(self, username="admin", role=StaffProfile.Role.ADMIN):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="ControlPass123",
            is_staff=True,
        )
        StaffProfile.objects.create(user=user, role=role, is_active=True)
        return user

    def test_service_mode_creates_first_admin_and_logs_in(self):
        response = self.client.get(reverse("control_service"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Сервисный режим открыт")

        response = self.client.post(
            reverse("control_service"),
            {
                "username": "owner",
                "first_name": "Owner",
                "email": "owner@example.com",
                "role": StaffProfile.Role.OWNER,
                "password1": "ControlPass123",
                "password2": "ControlPass123",
            },
        )

        user = User.objects.get(username="owner")
        self.assertTrue(user.is_staff)
        self.assertEqual(user.staff_profile.role, StaffProfile.Role.OWNER)
        self.assertRedirects(response, reverse("control_dashboard"))

    def test_unified_login_sends_staff_to_control(self):
        self.create_staff_user(username="manager")

        response = self.client.post(
            reverse("login"),
            {"username": "manager", "password": "ControlPass123"},
        )

        self.assertRedirects(response, reverse("control_dashboard"))

    def test_staff_user_cannot_open_customer_account(self):
        user = self.create_staff_user(username="staff-only", role=StaffProfile.Role.ADMIN)
        self.client.force_login(user)

        response = self.client.get(reverse("account"))
        self.assertRedirects(response, reverse("control_dashboard"))

        response = self.client.get(reverse("api_account"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["control_url"], reverse("control_dashboard"))

    def test_owner_can_create_staff_user_from_control_staff(self):
        owner = self.create_staff_user(username="owner", role=StaffProfile.Role.OWNER)
        self.client.force_login(owner)

        response = self.client.get(reverse("control_staff_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Новый пользователь админки")

        response = self.client.post(
            reverse("control_staff_create"),
            {
                "username": "new-admin",
                "first_name": "Новый",
                "email": "new-admin@example.com",
                "role": StaffProfile.Role.CONTENT,
                "password1": "ControlPass123",
                "password2": "ControlPass123",
            },
        )

        user = User.objects.get(username="new-admin")
        self.assertRedirects(response, reverse("control_staff"))
        self.assertTrue(user.is_staff)
        self.assertEqual(user.staff_profile.role, StaffProfile.Role.CONTENT)

    def test_role_permissions_are_enforced(self):
        user = self.create_staff_user(username="content", role=StaffProfile.Role.CONTENT)
        self.client.force_login(user)

        self.assertEqual(self.client.get(reverse("control_products")).status_code, 200)
        self.assertEqual(self.client.get(reverse("control_users")).status_code, 403)

    def test_page_view_middleware_records_public_visit(self):
        response = self.client.get(reverse("catalog"), HTTP_USER_AGENT="Mozilla/5.0 iPhone Mobile")

        self.assertEqual(response.status_code, 200)
        view = PageView.objects.filter(path="/catalog/").latest("created_at")
        self.assertEqual(view.device, "mobile")
        self.assertFalse(view.is_staff_area)
