# -*- coding: utf-8 -*-
"""Screen capture wrapper (mss, multi-monitor aware)."""
import mss
import numpy as np


class ScreenCapture:
    """Captures a fixed screen region as an RGB numpy array."""

    def __init__(self, region=None, monitor=1):
        self.region = dict(region) if region else None
        self.monitor = monitor
        self._sct = mss.mss()

    def set_region(self, region):
        """region = {'left','top','width','height'} in virtual-screen pixels."""
        self.region = dict(region)

    def set_monitor(self, index):
        self.monitor = index

    @staticmethod
    def list_monitors():
        with mss.mss() as sct:
            return list(sct.monitors)  # [0] = virtual span, [1..] = real

    def grab(self):
        """Return an RGB uint8 array of the region, or None."""
        if not self.region:
            return None
        try:
            shot = self._sct.grab(self.region)
        except Exception:
            return None
        img = np.asarray(shot, dtype=np.uint8)
        if img.size == 0:
            return None
        return img[:, :, [2, 1, 0]].copy()

    def close(self):
        try:
            self._sct.close()
        except Exception:
            pass
