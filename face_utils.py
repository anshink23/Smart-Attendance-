"""Analyse an uploaded student photo: must contain exactly one clear face."""

import numpy as np
from PIL import Image, ImageOps


def _load(path, max_side=1000):
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")   # fixes rotated phone photos
    img.thumbnail((max_side, max_side))
    return np.array(img)


def get_single_face_encoding(path):
    """Returns (encoding, None) on success or (None, error_message)."""
    import face_recognition          # imported here so the web pages load even before it is installed
    try:
        image = _load(path)
    except Exception:
        return None, "could not be read as an image (use JPG or PNG)."

    boxes = face_recognition.face_locations(image, model="hog")
    if len(boxes) == 0:
        return None, "no face found. Use a clear, front-facing photo with good light."
    if len(boxes) > 1:
        return None, "more than one face found. Upload a photo of only this student."

    top, right, bottom, left = boxes[0]
    if right - left < 60:
        return None, "face is too small. Move closer or crop the photo."

    return face_recognition.face_encodings(image, boxes)[0], None
