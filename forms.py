from django import forms
from django.contrib.auth import get_user_model

from .models import Forfait, Membre

User = get_user_model()


class MembreForm(forms.ModelForm):
    forfait = forms.ModelChoiceField(Forfait.objects.filter(actif=True), label="Forfait d'heures")

    class Meta:
        model = Membre
        fields = ["nom", "telephone", "metier", "adresse", "photo"]
        widgets = {"photo": forms.FileInput(attrs={"accept": "image/*"})}


class ResponsableForm(forms.Form):
    identifiant = forms.CharField(max_length=150)
    nom_complet = forms.CharField(max_length=150)
    telephone = forms.CharField(max_length=30, required=False)
    mot_de_passe = forms.CharField(min_length=6, widget=forms.PasswordInput)

    def clean_identifiant(self):
        v = self.cleaned_data["identifiant"].strip()
        if User.objects.filter(username__iexact=v).exists():
            raise forms.ValidationError("Cet identifiant existe déjà.")
        return v
