"""Forms for the scanner app."""
from django import forms
from django.conf import settings

MAX_RANGE = getattr(settings, "SCANNER_MAX_PORT_RANGE", 1000)

# Well-known port presets shown in the UI
PRESET_CHOICES = [
    ("", "— Custom range —"),
    ("1-1024", "Common ports (1–1024)"),
    ("1-100", "Top 100 (1–100)"),
    ("80-80", "HTTP (80)"),
    ("443-443", "HTTPS (443)"),
    ("20-25", "FTP/SSH/SMTP (20–25)"),
    ("3000-3100", "Dev servers (3000–3100)"),
    ("8000-8100", "Alt HTTP (8000–8100)"),
]


class ScanRequestForm(forms.Form):
    target = forms.CharField(
        label="Target (IP or hostname)",
        max_length=253,
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. scanme.nmap.org or 93.184.216.34",
                "class": "form-input",
                "autocomplete": "off",
                "spellcheck": "false",
            }
        ),
        help_text="Public IP address or resolvable hostname only.",
    )
    preset = forms.ChoiceField(
        label="Port preset",
        choices=PRESET_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_preset"}),
    )
    port_start = forms.IntegerField(
        label="Start port",
        min_value=1,
        max_value=65535,
        initial=1,
        widget=forms.NumberInput(attrs={"class": "form-input", "min": "1", "max": "65535"}),
    )
    port_end = forms.IntegerField(
        label="End port",
        min_value=1,
        max_value=65535,
        initial=1024,
        widget=forms.NumberInput(attrs={"class": "form-input", "min": "1", "max": "65535"}),
    )

    def clean(self):
        cleaned = super().clean()
        port_start = cleaned.get("port_start")
        port_end = cleaned.get("port_end")

        if port_start is not None and port_end is not None:
            if port_start > port_end:
                raise forms.ValidationError(
                    "Start port must be less than or equal to end port."
                )
            port_count = port_end - port_start + 1
            if port_count > MAX_RANGE:
                raise forms.ValidationError(
                    f"Range too large: {port_count} ports requested "
                    f"(maximum is {MAX_RANGE})."
                )
        return cleaned
