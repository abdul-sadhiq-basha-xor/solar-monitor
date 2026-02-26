# plants/forms.py
from django import forms
from django.contrib.auth.models import User

from .models import SolarPlant


class SignUpForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['username', 'email', 'password']


class PlantForm(forms.ModelForm):
    class Meta:
        model = SolarPlant
        fields = ['name', 'location', 'capacity_kw']
