# -*- coding: utf-8 -*-
import micropython
import portable_constants
import config_app
import hw_controller

config_app.iLogInterval_ms = 10 * portable_constants.SECOND_MS
config_app.iLogInterval_ms = None
config_app.iPollForWlanInterval_ms = 2 * portable_constants.MINUTE_MS
config_app.iPollForWlanInterval_ms = 30 * portable_constants.MINUTE_MS
config_app.iPollForWlanInterval_ms = 120 * portable_constants.MINUTE_MS
config_app.bUseNetwork = True
config_app.bHwDoLightSleep = True
config_app.bWriteLogStatistics = False

def f(*args):
  print('******* KeyboardInterrupt')
  if controller:
    controller.flush()

controller = None
try:
  hw_controller.updateConfigAppByVERSION()

  controller = hw_controller.HwController('hw_test_pidh_pido_day.py')
  controller.runForever()

except KeyboardInterrupt:
  micropython.schedule(f, None)

except Exception as e:
  if controller is None:
    raise
  controller.logException(e, 'Mainloop')

