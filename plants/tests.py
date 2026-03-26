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
    def setUp(self):
        # create an owner user for plant relationships
        self.owner = User.objects.create_user('owner2', 'o2@example.com', 'pw')

    def test_simulate_task_creates_reading(self):
        plant = SolarPlant.objects.create(name='X', location='L', capacity_kw=1, owner=self.owner)
        from .tasks import simulate_solar_readings
        simulate_solar_readings()
        self.assertTrue(SolarReading.objects.filter(plant=plant).exists())


from django.test import override_settings

class CeleryDemoTests(TestCase):
    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        CELERY_TASK_EAGER_PROPAGATES=True,
        CELERY_RESULT_BACKEND='rpc://',
        CELERY_BROKER_URL='memory://',
    )
    def setUp(self):
        self.user = User.objects.create_user('u', 'u@example.com', 'pw')
        self.client.login(username='u', password='pw')

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        CELERY_TASK_EAGER_PROPAGATES=True,
        CELERY_RESULT_BACKEND='rpc://',
        CELERY_BROKER_URL='memory://',
    )
    def test_start_long_task_and_status(self):
        # start the task via view
        resp = self.client.post(reverse('start_long_task'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('task_id', data)
        task_id = data['task_id']

        # check status - should be PENDING or SUCCESS depending on eager timing
        resp2 = self.client.get(reverse('task_status'), {'task_id': task_id})
        self.assertEqual(resp2.status_code, 200)
        status_data = resp2.json()
        self.assertIn('status', status_data)
        # with eager execution, task runs immediately but status could be PENDING or SUCCESS
        self.assertIn(status_data['status'], ('PENDING', 'SUCCESS', 'PROGRESS'))

    def test_status_no_backend(self):
        # simulate a configuration with no result backend; view should return 500
        with override_settings(CELERY_RESULT_BACKEND=None, CELERY_TASK_ALWAYS_EAGER=False):
            task_id = 'fake'
            resp = self.client.get(reverse('task_status'), {'task_id': task_id})
            self.assertEqual(resp.status_code, 500)
            self.assertIn('error', resp.json())

