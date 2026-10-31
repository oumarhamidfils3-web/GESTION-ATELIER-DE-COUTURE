import io

from PIL import Image, ImageOps


def reduire_photo(fichier):
    """Redresse, réduit (400 x 500 max) et convertit la photo en JPEG léger pour la stocker en base."""
    img = ImageOps.exif_transpose(Image.open(fichier)).convert("RGB")
    img.thumbnail((400, 500))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82)
    return buf.getvalue()
