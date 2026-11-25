"""
Liveness helper: counts real eye blinks (Eye Aspect Ratio on dlib's 68 landmarks).

Needs: shape_predictor_68_face_landmarks.dat in this folder
Download: http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2
"""

import os

import dlib
from scipy.spatial import distance as dist

PREDICTOR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "shape_predictor_68_face_landmarks.dat")
if not os.path.exists(PREDICTOR_PATH):
    raise SystemExit("[ERROR] shape_predictor_68_face_landmarks.dat not found.\n"
                     "Download http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2, "
                     "extract it and put the .dat file in the same folder as these scripts.")
predictor = dlib.shape_predictor(PREDICTOR_PATH)

RIGHT_EYE = list(range(36, 42))
LEFT_EYE = list(range(42, 48))

EAR_THRESHOLD = 0.21   # below this the eye is considered closed
CONSEC_FRAMES = 2      # closed frames needed to count as a blink


def eye_aspect_ratio(eye):
    a = dist.euclidean(eye[1], eye[5])
    b = dist.euclidean(eye[2], eye[4])
    c = dist.euclidean(eye[0], eye[3])
    return (a + b) / (2.0 * c)


class BlinkCounter:
    """Tracks blinks for ONE specific face (pass that face's box every frame)."""

    def __init__(self):
        self.closed_frames = 0
        self.blinks = 0

    def update(self, gray_frame, box):
        """box = (top, right, bottom, left) in gray_frame pixel coordinates."""
        top, right, bottom, left = box
        rect = dlib.rectangle(int(left), int(top), int(right), int(bottom))
        shape = predictor(gray_frame, rect)
        pts = [(shape.part(i).x, shape.part(i).y) for i in range(68)]

        ear = (eye_aspect_ratio([pts[i] for i in LEFT_EYE]) +
               eye_aspect_ratio([pts[i] for i in RIGHT_EYE])) / 2.0

        if ear < EAR_THRESHOLD:
            self.closed_frames += 1
        else:
            if self.closed_frames >= CONSEC_FRAMES:
                self.blinks += 1
            self.closed_frames = 0
        return self.blinks
