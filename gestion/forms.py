from django import forms
from django.contrib.auth import get_user_model

from .models import Forfait, Membre
from .photos import reduire_photo

User = get_user_model()


class MembreForm(forms.ModelForm):
    forfait = forms.ModelChoiceField(Forfait.objects.filter(actif=True), label="Forfait d'heures")

    photo = forms.ImageField(required=False, widget=forms.FileInput(attrs={"accept": "image/*"}))

    class Meta:
        model = Membre
        fields = ["nom", "telephone", "metier", "adresse"]

    field_order = ["nom", "telephone", "metier", "adresse", "photo", "forfait"]

    def save(self, commit=True):
        m = super().save(commit=False)
        f = self.cleaned_data.get("photo")
        if f:
            m.photo_data = reduire_photo(f)
        if commit:
            m.save()
        return m


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
