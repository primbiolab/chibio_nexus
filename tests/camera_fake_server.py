"""
Arranca camera/webrtc_server.py en 127.0.0.1:<puerto> con una cámara SIMULADA (nunca abre la webcam real).

    python tests/camera_fake_server.py <modo> <puerto>
    modo = frames  → 30 fps de frames grises
           none    → sin cámara (isOpened() False, read() → (False, None))
"""
import os
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class FakeCap:
    def __init__(self, mode):
        self.mode = mode
        self._frame = np.full((720, 1280, 3), 127, dtype=np.uint8)

    def isOpened(self):
        return self.mode == 'frames'

    def set(self, *a):
        return True

    def get(self, prop):
        return 30.0

    def read(self):
        if self.mode == 'frames':
            time.sleep(1 / 30)
            return True, self._frame
        time.sleep(0.05)
        return False, None

    def release(self):
        pass


if __name__ == '__main__':
    mode, port = sys.argv[1], int(sys.argv[2])
    cv2.VideoCapture = lambda *a, **k: FakeCap(mode)
    import uvicorn
    from camera import webrtc_server
    uvicorn.run(webrtc_server.app, host='127.0.0.1', port=port, log_level='warning')
