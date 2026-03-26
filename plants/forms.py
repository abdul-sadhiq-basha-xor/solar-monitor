# plants/forms.py
from django import forms
from django.contrib.auth.models import User

from .models import SolarPlant, CSVUpload


class SignUpForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['username', 'email', 'password']


class PlantForm(forms.ModelForm):
    class Meta:
        model = SolarPlant
        fields = ['name', 'location', 'capacity_kw']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'capacity_kw': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class CSVImportForm(forms.Form):
    """Form to upload CSV file for bulk import of solar readings."""
    file = forms.FileField(
        label='Select CSV File',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv',
            'id': 'csv-file-input',
        })
    )
    
    def clean_file(self):
        """Validate that the uploaded file is a CSV."""
        file = self.cleaned_data.get('file')
        if file:
            if not file.name.endswith('.csv'):
                raise forms.ValidationError('Please upload a CSV file.')
            if file.size > 10 * 1024 * 1024:  # 10 MB limit
                raise forms.ValidationError('File size must be under 10 MB.')
        return file
