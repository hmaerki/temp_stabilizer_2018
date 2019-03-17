# -*- coding: utf-8 -*-
'''
  Ableitung der Methoden für Simulation und Hardware.
'''
import sys

import config_app

import portable_ticks
import portable_constants
import portable_persist
import portable_controller
import portable_tempstabilizer
import portable_grafana_log_writer

PERSIST_SW_REBOOT = 'Sw_Reboot'

class Controller:
  def __init__(self):
    self.ticks_init()
    self.__objPersist = portable_persist.Persist(self.directoryData())
    self.__iLedModulo = 0
    self.__iTicksButtonPressed_ms = None
    self.__fTempO_SensorLast = -1000.0
    self.__fTempH_SensorLast = -1000.0
    self.openLogs()
    self.objHw = self.factoryHw()
    self.objHw.fDac_V = 0.0

    self.__objPollForWlanInterval = portable_ticks.Interval(iInterval_ms=config_app.iPollForWlanInterval_ms, bForceFirstTime=False)
    self.__forceWlanFirstTime()

    self.objGrafanaProtocol = self.factoryGrafanaProtocol()
    self.attachFileToGrafanaProtocol()

    self.objTs = self.factoryTempStabilizer()
    if self.fLog != None:
      self.objTs.logHeader(self.fLog)

  def __forceWlanFirstTime(self):
    # On PowerOn: start with Wlan
    bForceWlanFirstTime = self.objHw.isPowerOnReset()
    if self.__fileExists(config_app.FILENAME_REPLICATE_ONCE):
      bForceWlanFirstTime = True

    if not bForceWlanFirstTime:
      return

    self.__objPollForWlanInterval.doForce(iNextIriggerIn_ms=config_app.iPollForWlanOnce_ms)
    print('bForceWlanFirstTime=True: Will replicate in %ds' % (config_app.iPollForWlanOnce_ms // 1000))

  def ticks_init(self):
    # May be derived and overridden
    portable_ticks.init(config_app.iSimulationMaxTicks_ms)

  def exit(self):
    # May be derived and overridden
    if config_app.iExperimentDuration_ms == None:
      return False
    bExit = config_app.iExperimentDuration_ms < portable_ticks.objTicks.time_ms()
    return bExit

  def done(self):
    # May be derived and overridden
    self.objHw.fDac_V = 0.0
    self.__objPersist.persist()
    self.closeLogs()
    return False

  def openLogs(self):
    self.fLog = self.factoryLog()

  def closeLogs(self):
    if self.fLog != None:
      self.fLog.close()
    if self.objGrafanaProtocol != None:
      self.objGrafanaProtocol.close()

  def getStartTime_ms(self):
    # May be derived and overridden
    return portable_ticks.objTicks.ticks_add(portable_ticks.objTicks.ticks_ms(), -config_app.iTimeProcess_O_H_ms)

  def __fileExists(self, strFilename):
    try:
      with open(strFilename, 'r') as fIn:
        return True
    except:
       return False

  def directoryData(self):
    raise Exception('Needs to be derived...')

  def filenameLog(self):
    raise Exception('Needs to be derived...')

  def filenameGrafanaLog(self):
    raise Exception('Needs to be derived...')

  def factoryCachedFile(self, strFilename):
    # May be derived and overridden
    fOut = portable_grafana_log_writer.CachedLog(strFilename)
    return fOut

  def factoryGrafanaProtocol(self):
    return portable_grafana_log_writer.GrafanaProtocol(self.objHw.listEnvironsAddressI2C)

  def attachFileToGrafanaProtocol(self):
    strFilename = self.filenameGrafanaLog()
    bFileExists = self.__fileExists(strFilename)
    objCachedFile = self.factoryCachedFile(strFilename)
    self.objGrafanaProtocol.attachFile(objCachedFile)
    if not bFileExists:
      self.objGrafanaProtocol.writeHeader(self.objHw.iI2cFrequencySelected)

  def factoryLog(self):
    # May be derived and overridden
    if config_app.iLogInterval_ms == None:
      return None

    self.__objLogInterval = portable_ticks.Interval(iInterval_ms=config_app.iLogInterval_ms)
    strFilename = self.filenameLog()
    return self.factoryCachedFile(strFilename)

  def factoryHw(self):
    raise Exception('Needs to be derived...')

  def factoryTempStabilizer(self):
    # May be derived and overridden
    return portable_tempstabilizer.TempStabilizer()

  def reboot(self):
    raise Exception('Needs to be derived...')
  
  def remove(self, strFilenameFull):
    raise Exception('Needs to be derived...')

  def create(self, strFilenameFull):
    raise Exception('Needs to be derived...')

  def prepare(self):
    if config_app.bRunStopwatch:
      portable_ticks.enableStopwatch()

    # In case we restarted and the hardware ist still active
    self.networkFreeResources()

    self.objHw.startTempMeasurement()

    print('portable_tempstabilizer.prepare(): Supply Voltage fSupplyHV_V is %0.2f V' % self.objHw.messe_fSupplyHV_V)

    self.objTs.find_fDACzeroHeat(self.objHw)

    self.__fTempO_SensorLast = self.objHw.messe_fTempH_C
    self.__fTempH_SensorLast = self.objHw.messe_fTempO_C
    fTempH_Start = self.__fTempO_SensorLast
    fTempO_Start = self.__fTempH_SensorLast + config_app.fStart_Increment_fTempO_C
    iStartTicks_ms = self.getStartTime_ms()
    self.objTs.start(iTimeOH_ms=iStartTicks_ms, iTimeDayMaxEstimator=iStartTicks_ms, fTempH_Start=fTempH_Start, fTempO_Sensor=fTempO_Start, objPersist=self.__objPersist)

  def isNetworkConnected(self):
    raise Exception('Needs to be derived...')

  def networkFreeResources(self):
    raise Exception('Needs to be derived...')

  def ledBlink(self):
    '''
      Turns the LED on after some time. The LED will be switched off after the PID-calculation.
    '''
    self.__iLedModulo += 1
    bOn = self.__iLedModulo % config_app.iHwLedModulo == 0
    if bOn:
      if self.objHw.bButtonPressed:
        return
      self.objHw.setLed(True)

  def runOnce(self):
    '''
      return False: I2C-Readerror. Tray again next time
    '''
    iStopwatch_us = portable_ticks.stopwatch()
    fTempO_Sensor = self.objHw.messe_fTempO_C
    portable_ticks.stopwatch_end(iStopwatch_us, 'self.objHw.messe_fTempO_C')
    fTempDiff_C = abs(fTempO_Sensor - self.__fTempO_SensorLast)
    self.__fTempO_SensorLast = fTempO_Sensor
    if fTempDiff_C > 10.0:
      print('WARNING: self.objHw.messe_fTempO_C() diff = %f C' % fTempDiff_C)
      return False

    iStopwatch_us = portable_ticks.stopwatch()
    fTempH_Sensor = self.objHw.messe_fTempH_C  
    portable_ticks.stopwatch_end(iStopwatch_us, 'self.objHw.messe_fTempH_C')
    fTempDiff_C = abs(fTempH_Sensor - self.__fTempH_SensorLast)
    self.__fTempH_SensorLast = fTempH_Sensor
    if fTempDiff_C > 10.0:
      print('WARNING: self.objHw.messe_fTempH_C() diff = %f C' % fTempDiff_C)
      return False

    iNowTicks_ms = portable_ticks.objTicks.ticks_ms()

    iStopwatch_us = portable_ticks.stopwatch()
    self.objTs.processDayMaxEstimator(iNowTicks_ms, fTempO_Sensor)
    portable_ticks.stopwatch_end(iStopwatch_us, 'self.objTs.processDayMaxEstimator(...)')

    iStopwatch_us = portable_ticks.stopwatch()
    self.objTs.processO(iNowTicks_ms, fTempO_Sensor)
    portable_ticks.stopwatch_end(iStopwatch_us, 'self.objTs.processO(...)')

    iStopwatch_us = portable_ticks.stopwatch()
    self.objTs.processH(iNowTicks_ms, fTempH_Sensor, fTempO_Sensor)
    portable_ticks.stopwatch_end(iStopwatch_us, 'self.objTs.processH(...)')

    iStopwatch_us = portable_ticks.stopwatch()
    self.objHw.fDac_V = self.objTs.fDac_V(self.objHw, self.objHw.messe_fSupplyHV_V)
    portable_ticks.stopwatch_end(iStopwatch_us, 'self.objTs.fDac_V')
    return True

  def logOnce(self):
    self.objGrafanaProtocol.logTempstablilizer(self.objTs, self.objHw, self.__objPersist)
    self.logConsole()

    if self.fLog != None:
      self.log()

  def log(self):
    # May be derived and overridden
    if self.fLog == None:
      return

    bIntervalOver, iDummy = self.__objLogInterval.isIntervalOver()
    if bIntervalOver:
      self.objTs.log(self.fLog, self.objHw)
      portable_ticks.count('HwController.log()')

  def logConsole(self):
    raise Exception('Needs to be derived...')

  def sleepOnce(self, iStartTicks_ms):
    iDelay_ms = config_app.iTimeProcess_O_H_ms - portable_ticks.objTicks.ticks_diff(portable_ticks.objTicks.ticks_ms(), iStartTicks_ms)
    # print('iDelay_ms: %d' % iDelay_ms)
    if iDelay_ms > 0:
      self.delay_ms(iDelay_ms)

  def delay_ms(self, iDelay_ms):
    raise Exception('Needs to be derived...')

  def flush(self):
    if self.__objPersist != None:
      self.__objPersist.persist(bForce=True)
    self.objGrafanaProtocol.flush()

    fDiskFree_MBytes = self.objHw.messe_fDiskFree_MBytes
    if fDiskFree_MBytes < config_app.fDiskGrafanaTrash_MBytes:
      print('***** Out of disk space')
      # We remove the grafana file and brutally reboot
      self.remove(self.filenameGrafanaLog())
      self.reboot()

  def logException(self, objException, strFunction):
    self.formatIfFilesystemError(objException)
    iErrorId = self.objHw.randint(1000, 10000)
    strError = 'iErrorId=%d. %s returned %s' % (iErrorId, strFunction, str(objException))
    self.objGrafanaProtocol.logError(strError)
    self.flush()
    self.logExceptionHw(objException, strError, iErrorId)

  def formatIfFilesystemError(self, objException):
    # May be derived and overridden
    pass

  def logExceptionHw(self, objException, strError, iErrorId=None):
    # May be derived and overridden
    print(strError)
    sys.print_exception(objException)
  
  def runForever(self):
    self.prepare()
    while True:
      if self.exit():
        break
      try:
        self.runForeverInner()
      except portable_ticks.I2cException as e:
        self.objGrafanaProtocol.logError('I2C-Error: %s' % str(e))
        raise
       
    self.done()

  def runForeverInner(self):
    iStartTicks_ms = portable_ticks.objTicks.ticks_ms()

    iStopwatch_us = portable_ticks.stopwatch()
    self.networkOnce()
    portable_ticks.stopwatch_end(iStopwatch_us, 'self.networkOnce()')

    self.handleButton()

    portable_ticks.count('portable_controller.runForever().runOnce()')
    self.ledBlink()
    iStopwatch_us = portable_ticks.stopwatch()
    bSuccess = self.runOnce()
    if not self.objHw.bButtonPressed:
      self.objHw.setLed(False)
    portable_ticks.stopwatch_end(iStopwatch_us, 'self.runOnce()')
    if bSuccess:
      portable_ticks.count('portable_controller.runForever().logOnce()')
      iStopwatch_us = portable_ticks.stopwatch()
      self.logOnce()
      portable_ticks.stopwatch_end(iStopwatch_us, 'self.logOnce()')
      self.__objPersist.persist()

    portable_ticks.count('portable_controller.runForever().sleepOnce()')
    self.sleepOnce(iStartTicks_ms)
    self.objHw.startTempMeasurement()

  def handleButton(self):
    if self.__iTicksButtonPressed_ms == None:
      if self.objHw.bButtonPressed:
        # Button was released and now is pressed
        self.__iTicksButtonPressed_ms = portable_ticks.objTicks.ticks_ms()
        self.objHw.setLed(False)
      return
    iButtonPressed_ms = portable_ticks.objTicks.ticks_diff(portable_ticks.objTicks.ticks_ms(), self.__iTicksButtonPressed_ms)

    if iButtonPressed_ms < 5*portable_constants.SECOND_MS:
      # 0-5s: LED on
      self.objHw.setLed(True)
      if not self.objHw.bButtonPressed:
        self.objGrafanaProtocol.logWarning('Button pressed < 5s: Force WLAN replication')
        self.__objPollForWlanInterval.doForce()
        self.__iTicksButtonPressed_ms = None
      return

    # 5-99s: LED off
    self.objHw.setLed(False)
    if not self.objHw.bButtonPressed:
      strMsg = 'Button pressed > 5s: Delete "%s" and Reboot' % config_app.LOGFILENAME_PERSIST
      self.objGrafanaProtocol.logWarning(strMsg)
      print(strMsg)

      # Write Logs
      self.done()

      # Delete the file after self.done(): self.done() writes it!
      # Delete setpoint of previous session in 'persist.txt'
      self.__objPersist.trash()

      self.reboot()

    
  def networkOnce(self):
    '''Return ms spent'''
    if not config_app.bUseNetwork:
      return

    bIntervalOver, iEffectiveIntervalDuration_ms = self.__objPollForWlanInterval.isIntervalOver()
    if not bIntervalOver:
      return 0

    # Flush the filebuffer to make sure there is sufficient memory available for network communication
    # Write persist.txt in case we will be restarted by the watchdog
    self.flush()

    portable_ticks.count('portable_controller.networkOnce() find wlan')
    self.objGrafanaProtocol.logInfo('networkFindWlans()')
    if self.networkFindWlans():
      portable_ticks.count('portable_controller.networkOnce() found wlan')
      if self.__fileExists(config_app.FILENAME_REPLICATE_ONCE):
        # The file is presnet after SW-Installation or after a Watchdog-Reboot.
        # We do exactly on retry
        self.remove(config_app.FILENAME_REPLICATE_ONCE)
        print('removed:', config_app.FILENAME_REPLICATE_ONCE)
      else:
        # If it is not a retry, we create a file to do a retry in case of a watchdog reboot
        self.create(config_app.FILENAME_REPLICATE_ONCE)
        print('created:', config_app.FILENAME_REPLICATE_ONCE)

      portable_ticks.funcMemUsage()

      self.objGrafanaProtocol.logInfo('networkConnect()')
      self.networkConnect()
      if self.isNetworkConnected():
        portable_ticks.count('portable_controller.networkOnce() replication started')
        self.writeStatisticsFile()
        self.networkReplicate()
      else:
        print('Not connected!')
      self.networkFreeResources()

    if self.__fileExists(config_app.FILENAME_REPLICATE_ONCE):
      self.remove(config_app.FILENAME_REPLICATE_ONCE)
      print('removed:', config_app.FILENAME_REPLICATE_ONCE)

    iTimeDelta_ms = self.__objPollForWlanInterval.iTimeElapsed_ms(portable_ticks.objTicks.ticks_ms())
    if iTimeDelta_ms > 100:
      self.objGrafanaProtocol.logInfo('networkOnce() took %s ms' % iTimeDelta_ms)

  def writeStatisticsFile(self):
    if not config_app.bWriteLogStatistics:
      return
    strFilename = '%s/%s' % (self.directoryData(), config_app.LOGFILENAME_STATISTICS)
    with open(strFilename, 'w') as fOut:
      portable_ticks.objTicks.print_statistics(fOut)

  def networkConnect(self):
    raise Exception('Needs to be derived...')

  def networkReplicate(self):
    raise Exception('Needs to be derived...')

  def networkFindWlans(self):
    '''Return true if required Wlan found'''
    # TODO: Uncomment the following line
    raise Exception('Needs to be derived...')

  def networkDisconnect(self):
    raise Exception('Needs to be derived...')


