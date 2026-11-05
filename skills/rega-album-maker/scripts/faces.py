"""Faces in a photo, found with OpenCV's small YuNet detector (assets/models, MIT license).

It is optional. With it, the layout may crop a photo of people without cutting a face, put a title on a photo
without covering anyone, and keep faces out of the spine of a two-page spread. Without it, photos with people
stay whole and titles sit beside the photos, never on them.
"""
import os

from common import ASSETS

os.environ.setdefault('OPENCV_LOG_LEVEL', 'ERROR')  # keep OpenCV's notes out of the output

MODEL = os.path.join(ASSETS, 'models', 'face_detection_yunet_2023mar.onnx')
_DET = {}


def available():
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        return False
    return hasattr(cv2, 'FaceDetectorYN_create') and os.path.isfile(MODEL)


def detect(path, min_h=0.03):
    """[x, y, w, h] of each face, as fractions of the image's width and height, biggest first."""
    import cv2
    import numpy as np
    from PIL import Image
    im = Image.open(path).convert('RGB')
    im.thumbnail((640, 640))
    a = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    det = _DET.get('d')
    if det is None:
        det = _DET['d'] = cv2.FaceDetectorYN_create(MODEL, '', (a.shape[1], a.shape[0]), 0.75)
    det.setInputSize((a.shape[1], a.shape[0]))
    _, found = det.detect(a)
    W, H = im.size
    out = [[round(x / W, 4), round(y / H, 4), round(w / W, 4), round(h / H, 4)]
           for x, y, w, h in (found[:, :4].tolist() if found is not None else []) if h / H >= min_h]
    return sorted(out, key=lambda f: -f[3])
