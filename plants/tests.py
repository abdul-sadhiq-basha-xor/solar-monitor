from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from .models import SolarPlant, SolarReading
from django.utils import timezone


class BasicAuthTests(TestCase):
    def test_signup_and_redirection(self):
        resp = self.client.post(reverse('signup'), {
            'username': 'newuser',
            'email': 'n@e.com',
            'password': 'secretpw',
        })
        # after successful signup should redirect to dashboard
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_login_required_for_dashboard(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertRedirects(resp, f"{reverse('login')}?next={reverse('dashboard')}")


class PlantViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'o@example.com', 'pw')
        self.staff = User.objects.create_user('admin', 'a@example.com', 'pw', is_staff=True)
        # create plant owned by owner
        self.plant = SolarPlant.objects.create(name='P1', location='loc', capacity_kw=5, owner=self.owner)

    def test_owner_dashboard(self):
        self.client.login(username='owner', password='pw')
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'P1')

    def test_staff_dashboard_shows_all(self):
        self.client.login(username='admin', password='pw')
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'P1')

    def test_owner_cannot_view_other_detail(self):
        other = User.objects.create_user('other', 'other@example.com', 'pw')
        self.client.login(username='other', password='pw')
        resp = self.client.get(reverse('plant_detail', args=[self.plant.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_staff_can_view_detail(self):
        self.client.login(username='admin', password='pw')
        resp = self.client.get(reverse('plant_detail', args=[self.plant.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_create_plant_form(self):
        self.client.login(username='owner', password='pw')
        resp = self.client.post(reverse('plant_create'), {
            'name': 'P2',
            'location': 'x',
            'capacity_kw': 3,
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(SolarPlant.objects.filter(name='P2', owner=self.owner).exists())


class TaskTests(TestCase):
    def test_simulate_task_creates_reading(self):
        plant = SolarPlant.objects.create(name='X', location='L', capacity_kw=1, owner=self.owner)
        from .tasks import simulate_solar_readings
        simulate_solar_readings()
        self.assertTrue(SolarReading.objects.filter(plant=plant).exists())

