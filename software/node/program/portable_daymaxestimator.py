# -*- coding: utf-8 -*-
import math

import config_app
import portable_ticks
import portable_constants

# DayMaxEstimator
# 6 Minutes
_TIME_PROCESS_DAYMAXESTIMATOR_MS = 6*portable_constants.MINUTE_MS
# 6 Minutes
_TIME_CALC_FTEMPO_SETPOINT_MS = portable_constants.TIME_CALC_FTEMPO_SETPOINT_MS
# 3 Hours
_TIME_INTERVAL_FTEMPO_SETPOINT_MS = portable_constants.TIME_INTERVAL_FTEMPO_SETPOINT_MS

# SetpointReduction
_SETPOINT_CONSTANT_MS = 3 * 24 * portable_constants.HOUR_MS
# Parabel: Nach __SETPOINT_ABNAHME_MS nimmt die Temperatur um __SETPOINT_ABNAHME_C ab.
__SETPOINT_ABNAHME_MS = 24 * portable_constants.HOUR_MS
__SETPOINT_ABNAHME_C = 0.01
_SETPOINT_K_MS = __SETPOINT_ABNAHME_MS/math.sqrt(__SETPOINT_ABNAHME_C)
# Anstieg bei Leistund zu klein pro Tag
_SETPOINT_INCREASE_C = 0.02 * _TIME_CALC_FTEMPO_SETPOINT_MS / ( 24 * portable_constants.HOUR_MS)

_PERSIST_SETPOINT_TEMPO_C = 'SetpointWhenSet.fTempO_C'
PERSIST_SETPOINT_TIMESINCE_MS = 'SetpointWhenSet.iTimeSince_ms'

_PERSIST_SETPOINT_LIST_LAST = 'SetpointList.iLast'
_PERSIST_SETPOINT_LIST_TEMP_C = 'SetpointList.fTemp_C'
_PERSIST_SETPOINT_LIST_HEAT_W = 'SetpointList.fHeat_W'

_iTimePeakDelay_ms = 20*portable_constants.MINUTE_MS
bDebug = False
if bDebug:
  debug_print = print
else:
  # A dummy function
  debug_print = lambda *x: None


class TempO_SetpointWhenSet:
  '''
    Persistenz:
    Gespeichert werden muss:
      - fTempO_C
      - Die Zeit, seit der fTempO_C gesetzt wurde.
        iTimeSince_ms = ticks_diff(iTicks_now_ms, iTicks_ms)
    Das File soll jede Stunde geschrieben werden.
  '''
  def __init__(self, iTicks_ms, fTempO_C, objPersist=None):
    self.iTicks_ms = iTicks_ms
    self.fTempO_C = fTempO_C
    self.__objPersist = objPersist
    if objPersist.loaded:
      print('Initialize from persist: Setpoint fTemp_C, iTimeSince_ms')
      # Restore the value from the previous run
      fTempO_C = objPersist.getValue(_PERSIST_SETPOINT_TEMPO_C, None)
      if fTempO_C != None:
        self.fTempO_C = fTempO_C
        # print('persist start: fTempO_C=%0.6f' % self.fTempO_C)
      iTimeSince_ms = objPersist.getValue(PERSIST_SETPOINT_TIMESINCE_MS, None)
      if iTimeSince_ms != None:
        # TODO(Hans): add/diff?
        self.iTicks_ms = portable_ticks.objTicks.ticks_diff(iTicks_ms, iTimeSince_ms)
        # print('persist start: iTimeSince_ms=%d' % iTimeSince_ms)

  def __calculateSetpointReduction(self, iTicks_now_ms):
    iAgeParabel_ms = iTicks_now_ms - self.iTicks_ms - _SETPOINT_CONSTANT_MS
    if iAgeParabel_ms < 0:
      return 0.0
    fTmp = float(iAgeParabel_ms)/_SETPOINT_K_MS
    return -fTmp*fTmp

  def calculateSetpoint(self, iTicks_now_ms):
    if self.__objPersist != None:
      # Save actual value in Persist-Object
      iTimeSince_ms = portable_ticks.objTicks.ticks_diff(iTicks_now_ms, self.iTicks_ms)
      self.__objPersist.setValue(_PERSIST_SETPOINT_TEMPO_C, self.fTempO_C)
      self.__objPersist.setValue(PERSIST_SETPOINT_TIMESINCE_MS, iTimeSince_ms)

    return self.fTempO_C + self.__calculateSetpointReduction(iTicks_now_ms)

  def restart(self, iTicks_ms, fTempO_C):
    self.fTempO_C = fTempO_C
    self.iTicks_ms = iTicks_ms

  def adjust(self, iTicks_ms, fTempIncrease_C):
    debug_print('old fTempO_C=%0.6f' % self.fTempO_C)
    self.fTempO_C = self.calculateSetpoint(iTicks_ms) + fTempIncrease_C
    debug_print('new fTempO_C=%0.6f' % self.fTempO_C)
    # Subtrakt PeakDelay to avoid that a peak increases the setpoint again
    iTimeSince_ms = portable_ticks.objTicks.ticks_diff(iTicks_ms, self.iTicks_ms)
    if iTimeSince_ms > _iTimePeakDelay_ms:
      # Make sure, we only set the time forward and never backward
      self.iTicks_ms = portable_ticks.objTicks.ticks_add(iTicks_ms, -_iTimePeakDelay_ms)

TEMP_LOW_C = -100.00
HEAT_HIGH_W = config_app.fPowerOffsetMin_W+config_app.fPowerOffsetRangeOk_W

class TemperatureList:
  def __init__(self, objPersist):
    self.__objPersist = objPersist
    self.iDatapoints = int(_TIME_INTERVAL_FTEMPO_SETPOINT_MS/_TIME_CALC_FTEMPO_SETPOINT_MS)
    self.iIndexMiddle = int(self.iDatapoints/2)
    self.fFetMin_W = (config_app.fPowerOffsetMin_W + config_app.fPowerOffsetRangeOk_W) / 2.0

    if objPersist.loaded:
      print('Initialize from persist: listTempC, listHeat_W')
      # Restore the value from the previous run
      self.iLastDatapoint = objPersist.getValue(_PERSIST_SETPOINT_LIST_LAST, None)
      self.listTemp_C = objPersist.getValue(_PERSIST_SETPOINT_LIST_TEMP_C, None)
      self.listHeat_W = objPersist.getValue(_PERSIST_SETPOINT_LIST_HEAT_W, None)
      if (self.iLastDatapoint != None) and (self.listTemp_C != None) and (self.listHeat_W != None):
        self.fFetMin_W = config_app.fFetMin_W
        return

    self.iLastDatapoint = 0
    self.listTemp_C = [TEMP_LOW_C,]*self.iDatapoints
    self.listHeat_W = [HEAT_HIGH_W,]*self.iDatapoints

  def appendLastDatapoint(self, fHeat_W, fTemp_C=TEMP_LOW_C):
    self.iLastDatapoint += 1
    if self.iLastDatapoint >= self.iDatapoints:
      self.iLastDatapoint = 0
      self.fFetMin_W = config_app.fFetMin_W
    self.listTemp_C[self.iLastDatapoint] = fTemp_C
    self.listHeat_W[self.iLastDatapoint] = fHeat_W
    if self.__objPersist != None:
      self.__objPersist.setValue(_PERSIST_SETPOINT_LIST_LAST, self.iLastDatapoint)
      self.__objPersist.setValue(_PERSIST_SETPOINT_LIST_TEMP_C, self.listTemp_C)
      self.__objPersist.setValue(_PERSIST_SETPOINT_LIST_HEAT_W, self.listHeat_W)

  def getTempMedian_C(self):
    listTempSorted_C = sorted(self.listTemp_C)
    return listTempSorted_C[self.iIndexMiddle]

  def getTempMax_C(self):
    return max(self.listTemp_C)

  def getHeatMedian_W(self):
    listHeatSorted_W = sorted(self.listHeat_W)
    return listHeatSorted_W[self.iIndexMiddle]

  def getListAsString(self):
    return ','.join(map(lambda v: '%0.1f' % v, (self.listTemp_C[self.iLastDatapoint+1:] + self.listTemp_C[:self.iLastDatapoint])))

class DayMaxEstimator:
  """
    Grundsätzlich werden nur die Zeitpunkte berücksichtigt, bei welchen nicht geheizt wird.
    Die Berechnung des neuen fTempO_Setpoint_C findet alle 6 Minuten (_TIME_CALC_FTEMPO_SETPOINT_MS) statt.
    Es wird immer die tiefste Temperatur der letzten 3 Stunden (_TIME_INTERVAL_FTEMPO_SETPOINT_MS) berücksichtigt.
    Falls diese Temperatur höher ist als der aktuelle fTempO_Setpoint_C, so wird dieser erhöht.
    Der aktuelle fTempO_Setpoint_C wird gemäss der Funktion 'calculateSetpointReduction()' reduziert.
    Falsch: Median
  """
  def __init__(self, iTicks_ms):
    self.fOutputValue = None
    self.iNextDayEstimatorTicks_ms = iTicks_ms

    if portable_ticks.objTicks.iMaxTicks_ms < _TIME_PROCESS_DAYMAXESTIMATOR_MS:
      print('WARNING: DayMaxEstimator will NEVER be called: iMaxTicks_ms<_TIME_PROCESS_DAYMAXESTIMATOR_MS  (%d<%d)' % (portable_ticks.objTicks.iMaxTicks_ms, _TIME_PROCESS_DAYMAXESTIMATOR_MS))

  @property
  def fFetMin_W(self):
    return self.objTemperatureList.fFetMin_W

  def start(self, iTicks_ms, fTempO_Sensor, objPersist=None):
    # Initial values
    self.objTempO_SetpointWhenSet = TempO_SetpointWhenSet(iTicks_ms=iTicks_ms, fTempO_C=fTempO_Sensor, objPersist=objPersist)
    self.objTemperatureList = TemperatureList(objPersist)
    self.iStartTime_ms = iTicks_ms

  def process(self, iTicks_ms, objAvgTempO_C, objAvgHeat_W, bFetMin_W_Limit_Low):
    iDiffTicks_ms = portable_ticks.objTicks.ticks_diff(iTicks_ms, self.iNextDayEstimatorTicks_ms)
    if iDiffTicks_ms > 0:
      if self.fOutputValue != None:
        # Still no need to process
        return

    self.iNextDayEstimatorTicks_ms = portable_ticks.objTicks.ticks_add(iTicks_ms, _TIME_PROCESS_DAYMAXESTIMATOR_MS)

    self.fOutputValue = self.__process(iTicks_ms, objAvgTempO_C, objAvgHeat_W, bFetMin_W_Limit_Low)

  def __process(self, iTicks_ms, objAvgTempO_C, objAvgHeat_W, bFetMin_W_Limit_Low):
    portable_ticks.count('DayMaxEstimator.__process()')

    iTimeDelta_ms = portable_ticks.objTicks.ticks_diff(iTicks_ms, self.iStartTime_ms)
    if iTimeDelta_ms > _TIME_CALC_FTEMPO_SETPOINT_MS:
      fAvgHeat_W = objAvgHeat_W.getValueAndReset()
      fAvgTempO_C = objAvgTempO_C.getValueAndReset()
      # Alle 6 Minuten wird die Temperatur in objTemperatureList gespeichert und der Setpoint neu berechnet.
      self.iStartTime_ms = portable_ticks.objTicks.ticks_add(self.iStartTime_ms, _TIME_CALC_FTEMPO_SETPOINT_MS)
      debug_print(10*'****')
      debug_print('*** DayMaxEstimator')
      debug_print('**** self.iStartTime_ms:', self.iStartTime_ms, ', bFetMin_W_Limit_Low:', bFetMin_W_Limit_Low)

      if config_app.bPowerOffset:
        self.__adjustPowerOffset(iTicks_ms)

      if bFetMin_W_Limit_Low:
        # No heating
        self.objTemperatureList.appendLastDatapoint(fHeat_W=fAvgHeat_W, fTemp_C=fAvgTempO_C)
        return self.__updateSetpoint(iTicks_ms)
      # Heating
      self.objTemperatureList.appendLastDatapoint(fHeat_W=fAvgHeat_W)
    # debug_print('**** self.objTempO_SetpointWhenSet.calculateSetpoint:%0.6f' % self.objTempO_SetpointWhenSet.calculateSetpoint(iTicks_ms))

    return self.objTempO_SetpointWhenSet.calculateSetpoint(iTicks_ms)

  def __updateSetpoint(self, iTicks_ms):
    fTempPast_C = self.__getTempPast_C(iTicks_ms)
    debug_print('**** fTempPast_C:', fTempPast_C)
    fSetpoint_C = self.objTempO_SetpointWhenSet.calculateSetpoint(iTicks_ms)
    debug_print('**** fTempPast_C, fSetpoint_C:', fTempPast_C, fSetpoint_C)
    if fTempPast_C < fSetpoint_C:
      return fSetpoint_C
    debug_print('**** self.objTempO_SetpointWhenSet.restart:', fTempPast_C)
    self.objTempO_SetpointWhenSet.restart(iTicks_ms, fTempPast_C)
    return fTempPast_C

  def __getTempPast_C(self, iTicks_ms):
    iTimeSinceLastSetpointSet_ms = portable_ticks.objTicks.ticks_diff(iTicks_ms, self.objTempO_SetpointWhenSet.iTicks_ms)
    debug_print('**** iTimeSinceLastSetpointSet_s:', iTimeSinceLastSetpointSet_ms//1000)
    # assert iTimeSinceLastSetpointSet_ms >= 0
    if iTimeSinceLastSetpointSet_ms < 0:
      raise Exception('iTimeSinceLastSetpointSet_ms should be >= 0, but is %d' % iTimeSinceLastSetpointSet_ms)
    debug_print('**** self.objTemperatureList.listTemp_C:', self.objTemperatureList.getListAsString())

    if iTimeSinceLastSetpointSet_ms < _iTimePeakDelay_ms:
      # Setpoint was set within the last 20min
      debug_print('**** max')
      return self.objTemperatureList.getTempMax_C()

    # Setpoint has not been set during last 20min
    debug_print('**** median')
    return self.objTemperatureList.getTempMedian_C()

  def __adjustPowerOffset(self, iTicks_ms):
    fHeat_W = self.objTemperatureList.getHeatMedian_W()
    if fHeat_W < config_app.fPowerOffsetMin_W:
      # Power too low: Increase setpoint slowly
      debug_print('__adjustPowerOffset: Power too low: Increase setpoint slowly')
      self.objTempO_SetpointWhenSet.adjust(iTicks_ms, fTempIncrease_C=_SETPOINT_INCREASE_C)
      return

    if fHeat_W < config_app.fPowerOffsetMin_W+config_app.fPowerOffsetRangeOk_W:
      # Power ok (in good-range): Do not decrease setpoint in the long run
      debug_print('__adjustPowerOffset: Power ok (in good-range): Do not decrease setpoint in the long run')
      self.objTempO_SetpointWhenSet.adjust(iTicks_ms, fTempIncrease_C=0.0)
      return

