# -*- coding: utf-8 -*-
import os

import portable_grafana_datatypes
import portable_ticks
import config_app
import config_node

'''
Optimierungspotential:
 - Ein Wert wird geschrieben, wenn er sich verändert. Aber frühstens wieder in iMODULO_xxx
 - Statt einem Zeichen ohne Wert wird nichts geschrieben.
   - a) Ein leeres Zeichen wird aber mindestens alle iMODULO geschrieben
   - b) Dafür wird wird vor dem nächsten Wert die ms hineingeschrieben bei welcher der letzte Wert gemessen wurde.
   - c) Am Anfang des Files wird dem reader ein Hint gegeben, alle wieviele Millisekunden ein Wert gemessen wird. So kann der Empfänger fehlende Werte einsetzen.
'''
def nextFilename(strFilenameTemplate='test_hw_pidh_pido_day_log_%02d.txt'):
  listFiles = os.listdir()
  for i in range(100):
    strFilename = strFilenameTemplate % i
    if strFilename in listFiles:
      continue
    print('strFilename: %s' % strFilename)
    return strFilename
  raise Exception('nextFilename()')

class CachedLog:
  def __init__(self, strFilename):
    self.strFilename = strFilename
    self.listBuf = []

  def write(self, strMessage):
    self.listBuf.append(strMessage)
    if len(self.listBuf) < 20:
      return
    self.__flush()

  def __flush(self):
    print('flush()')
    with open(self.strFilename, 'a') as fLog:
      for strLine in self.listBuf:
        fLog.write(strLine)
    self.listBuf = []

  def close(self):
    self.__flush()

class GrafanaProtocol:
  def __init__(self, objLog, bFileExists=False):
    self.__objLog = objLog
    self.__iLastTicks_ms = portable_ticks.objTicks.ticks_ms()
    self.__iCounter = -1
    self.__objInterval = portable_ticks.Interval(iInterval_ms=config_app.iGrafanaLogInterval_ms)

    self.__objGrafanaValue_TempO = portable_grafana_datatypes.GrafanaValueFloatAvg('O', 'fTempO_C', 100.0)
    self.__objGrafanaValue_TempO_Setpoint = portable_grafana_datatypes.GrafanaValueFloat('S', 'fTempO_Setpoint_C', 100.0)
    self.__objGrafanaValue_Heat = portable_grafana_datatypes.GrafanaValueFloatAvg('H', 'fHeat_W', 100.0)
    self.__objGrafanaValue_TempEnvirons = portable_grafana_datatypes.GrafanaValueFloatAvg('U', 'fTempEnvirons_C', 100.0)
    self.__objGrafanaValue_PidH_bLimitHigh = portable_grafana_datatypes.GrafanaValueBoolTrue('L', 'PidH_bLimitHigh')
    self.__objGrafanaValue_DACzeroHeat = portable_grafana_datatypes.GrafanaValueFloatAvg('z', 'fDACzeroHeat_V', 1000.0)
    self.__objGrafanaValue_DiskFree = portable_grafana_datatypes.GrafanaValueFloat('F', 'fDiskFree_MBytes', 100.0)

    if bFileExists:
      return

    self.logLine(portable_grafana_datatypes.TAG_GRAFANA_VERSION, '0.1')
    self.logLine(portable_grafana_datatypes.TAG_GRAFANA_SITE_NODE, '%s %s' % (config_node.strSite, config_node.strNode))
    self.logLine(portable_grafana_datatypes.TAG_GRAFANA_MAXTICK_MS, portable_ticks.objTicks.iMaxTicks_ms)

    def logAuxiliary(objGrafanaValue, iModuloPull):
      self.logLine(portable_grafana_datatypes.TAG_GRAFANA_DATATYPE, objGrafanaValue.getConstructor())
      if config_app.bGrafanaSkipEqualValues:
        self.logLine(portable_grafana_datatypes.TAG_GRAFANA_MESSINTERVAL_MS, '%s %d' % (objGrafanaValue.strTag, iModuloPull*config_app.iGrafanaLogInterval_ms))

    logAuxiliary(self.__objGrafanaValue_TempO, config_app.iMODULO_GRAFANALOG_MEDIUM_PULL)
    logAuxiliary(self.__objGrafanaValue_TempO_Setpoint, config_app.iMODULO_GRAFANALOG_MEDIUM_PULL)
    logAuxiliary(self.__objGrafanaValue_Heat, config_app.iMODULO_GRAFANALOG_MEDIUM_PULL)
    logAuxiliary(self.__objGrafanaValue_TempEnvirons, config_app.iMODULO_GRAFANALOG_SLOW_PULL)
    logAuxiliary(self.__objGrafanaValue_PidH_bLimitHigh, config_app.iMODULO_GRAFANALOG_MEDIUM_PULL)
    logAuxiliary(self.__objGrafanaValue_DACzeroHeat, config_app.iMODULO_GRAFANALOG_MEDIUM_PULL)
    logAuxiliary(self.__objGrafanaValue_DiskFree, config_app.iMODULO_GRAFANALOG_SLOW_PULL)

  def close(self):
    self.__objLog.close()

  def logInfo(self, strWarning):
    self.logLine(portable_grafana_datatypes.TAG_GRAFANA_INFO, strWarning)

  def logWarning(self, strWarning):
    self.logLine(portable_grafana_datatypes.TAG_GRAFANA_WARNING, strWarning)

  def logError(self, strWarning):
    self.logLine(portable_grafana_datatypes.TAG_GRAFANA_ERROR, strWarning)

  def logNtpTime(self, iSecondsSince1970_UnixEpoch):
    self.logLine(portable_grafana_datatypes.TAG_GRAFANA_NTP, str(int(iSecondsSince1970_UnixEpoch)))

  def logLine(self, strTag, strPayload):
    iTicksNow_ms = portable_ticks.objTicks.ticks_ms()
    iTicksDiff_ms = portable_ticks.objTicks.ticks_diff(iTicksNow_ms, self.__iLastTicks_ms)
    self.__objLog.write('%d %s %s\n' % (iTicksDiff_ms, strTag, strPayload))
    self.__iLastTicks_ms = iTicksNow_ms

  def __logLine(self, iEffectiveIntervalDuration_ms, strTag, strPayload):
    self.__objLog.write('%d %s %s\n' % (iEffectiveIntervalDuration_ms, strTag, strPayload))

  def logTempstablilizer(self, objTs, objHw):
    bIntervalOver, iEffectiveIntervalDuration_ms = self.__objInterval.isIntervalOver()
    if not bIntervalOver:
      return

    self.__iCounter += 1

    if (self.__iCounter % config_app.iMODULO_GRAFANALOG_MEDIUM_PUSH) == 0:
      self.__objGrafanaValue_TempO.pushValue(objTs.fTempO_C)
      self.__objGrafanaValue_Heat.pushValue(objTs.fHeat_W)
      self.__objGrafanaValue_PidH_bLimitHigh.pushValue(objTs.bFetMax_W_Limit_High)
      self.__objGrafanaValue_DACzeroHeat.pushValue(objTs.fDACzeroHeat_V)

    if (self.__iCounter % config_app.iMODULO_GRAFANALOG_SLOW_PUSH) == 0:
      fTempEnvirons_C = objHw.messe_fTempEnvirons_C
      if fTempEnvirons_C != None:
        self.__objGrafanaValue_TempEnvirons.pushValue(fTempEnvirons_C)
      iDiskFree_MBytes = objHw.messe_iDiskFree_MBytes

    listValues = []

    def pullValue(objGrafanaValue):
      strValue = objGrafanaValue.pullValue()
      if strValue != None:
        listValues.append(objGrafanaValue.strTag + strValue)
      else:
        if not config_app.bGrafanaSkipEqualValues:
          # Einfluss von 'Leer'zeichen: 2'092 Bytes mit. 1'457 Bytes ohne.
          # Stellen für die Temperatur: Drei Stellen: 1'457 Bytes, Zwei Stellen: 997 Bytes
          listValues.append(objGrafanaValue.strTag)

    if (self.__iCounter % config_app.iMODULO_GRAFANALOG_MEDIUM_PULL) == 0:
      pullValue(self.__objGrafanaValue_TempO)
      pullValue(self.__objGrafanaValue_Heat)
      pullValue(self.__objGrafanaValue_PidH_bLimitHigh)
      pullValue(self.__objGrafanaValue_DACzeroHeat)

      # self.__objGrafanaValue_TempO_Setpoint is not AVG. So we only need to pushValue() once per pullValue()
      self.__objGrafanaValue_TempO_Setpoint.pushValue(objTs.fTempO_Setpoint_C)
      pullValue(self.__objGrafanaValue_TempO_Setpoint)

    if (self.__iCounter % config_app.iMODULO_GRAFANALOG_SLOW_PULL) == 0:
      pullValue(self.__objGrafanaValue_TempEnvirons)
      # self.__objGrafanaValue_DiskFree is not AVG. So we only need to pushValue() once per pullValue()
      self.__objGrafanaValue_DiskFree.pushValue(iDiskFree_MBytes)
      pullValue(self.__objGrafanaValue_DiskFree)

    if len(listValues) > 0:
      self.logLine(portable_grafana_datatypes.TAG_GRAFANA_VALUE, ''.join(listValues))

if __name__ == '__main__':
  objFloat = GrafanaValueFloat('S', 'fTempO_Setpoint_C', 1000.0)
  listFloatInput = (1.0, 1.0, 1.1, 1.1, 1.1, 20.0)
