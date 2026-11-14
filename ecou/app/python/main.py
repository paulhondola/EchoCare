"""Ecou on the UNO Q (08-ecou.md). ECOU_RUN picks what runs:

    robot   (default) Ecou itself: tracking, gestures, floor search, the phone link
    test    the bring-up test, every part once (08 §8, step 1)
    record  gesture samples for the model (spike S15)

Set it in the app's environment, or change DEFAULT_RUN below.
"""

import os
import time

from arduino.app_utils import App
from body import Body

DEFAULT_RUN = "robot"

run = os.environ.get("ECOU_RUN", DEFAULT_RUN)
body = Body()
started = False
robot = None


def loop() -> None:
    global started, robot
    if not started:
        started = True
        time.sleep(2.0)  # let the sketch finish starting
        if run == "test":
            import bringup

            bringup.run(body)
        elif run == "record":
            import record

            record.run(body)
        else:
            from robot import Ecou

            robot = Ecou(body)
            robot.calibrate()
        return
    if robot is not None:
        robot.tick()
    else:
        if body.temp_c is not None:
            body.show_temp(body.temp_c)
        time.sleep(2.0)


App.run(user_loop=loop)
