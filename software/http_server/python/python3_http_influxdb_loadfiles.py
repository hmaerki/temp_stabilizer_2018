# -*- coding: utf-8 -*-
import os
import shutil
import traceback
import threading

import influxdb

import config_app
import config_http_server
import time
import python3_http_server_lib
import python3_grafana_log_reader_lib
import python3_grafana_log_reader
import portable_grafana_datatypes

def http_write_data(strMac, strFilename, strLogData):
  '''
    Will be called from apache-wsgi
  '''
  import python3_http_server_lib

  def write_data(strMac, strFilenameBase, strLogData):
    fSecondsSince1970_UnixEpochStart_EndOfFile = time.time()
    strTime = time.strftime('%Y-%m-%d_%H-%M-%S', time.localtime(fSecondsSince1970_UnixEpochStart_EndOfFile))

    strFilenameFull = python3_http_server_lib.getToProcessFilenameFull(strFilenameBase, strMac)

    print('strFilenameFull:' + strFilenameFull)

    with open(strFilenameFull, 'w') as fOut:
      fOut.write(strLogData)

      # Add a timestamp to the file
      fOut.write('1000 ntptime %d\n' % fSecondsSince1970_UnixEpochStart_EndOfFile)

    return strFilenameFull

  # def makedirs(strDir):
  #   if not os.path.exists(strDir):
  #     os.makedirs(strDir)

  # makedirs(python3_http_server_lib.strHttpServerToProcessDirectory)
  # makedirs(python3_http_server_lib.strHttpServerProcessedDirectory)
  # makedirs(python3_http_server_lib.strHttpServerFailedDirectory)

  strFilenameFull = write_data(strMac, strFilename, strLogData)

  thread = threading.Thread(target=__processFiles, args=())
  thread.start()

  return strFilenameFull

def __processFiles():
  processFiles(python3_http_server_lib.strHttpServerToProcessDirectory,
                          python3_http_server_lib.strHttpServerProcessedDirectory,
                          python3_http_server_lib.strHttpServerFailedDirectory,
                          bWritePng=False)

def openInfluxDb():
  print('InfluxDB open %s:%d %s' % (config_http_server.strInfluxDbHost, config_http_server.strInfluxDbPort, config_http_server.strInfluxDbDatabase))
  return influxdb.InfluxDBClient(config_http_server.strInfluxDbHost, config_http_server.strInfluxDbPort, '', '', config_http_server.strInfluxDbDatabase)

class GrafanaInfluxGetNtpTime(python3_grafana_log_reader_lib.GrafanaDumper):
  def __init__(self):
    python3_grafana_log_reader_lib.GrafanaDumper.__init__(self)
    self.iMillisecondsSince1970_UnixEpochStart_StartOfFile = None
    self.strMac = None

  def handleMac(self, iTime_ms, strMac):
    self.strMac = strMac

  def handleNtpTime(self, iTime_ms, fSecondsSince1970_UnixEpoch):
    self.iMillisecondsSince1970_UnixEpochStart_StartOfFile = int(fSecondsSince1970_UnixEpoch*1000.0) - iTime_ms

class GrafanaInfluxDbDumper(python3_grafana_log_reader_lib.GrafanaDumper):
  def __init__(self, strMac, iMillisecondsSince1970_UnixEpochStart_StartOfFile):
    assert strMac != None
    assert iMillisecondsSince1970_UnixEpochStart_StartOfFile != None
    python3_grafana_log_reader_lib.GrafanaDumper.__init__(self)
    self.__strMac = strMac
    self.__iMillisecondsSince1970_UnixEpochStart = iMillisecondsSince1970_UnixEpochStart_StartOfFile
    self.__listMeasurements = []
    self.__dictSummaryFields = {}

    p = config_http_server.factoryGitHubPull()
    p.setMac(strMac)
    self.__strNodeName = p.objNode.strName
    self.__strLabLabel = p.objNode.strLabLabel

  def handleMac(self, iTime_ms, strMac):
    assert self.__strMac == strMac

  def getTimeGrafana_ms(self, iTime_ms):
    # https://github.com/influxdata/influxdb-python/blob/master/examples/tutorial_server_data.py
    assert self.__iMillisecondsSince1970_UnixEpochStart != None
    return iTime_ms + self.__iMillisecondsSince1970_UnixEpochStart

  def handleLine(self, iTime_ms, strVerb, strPayload):
    python3_grafana_log_reader_lib.GrafanaDumper.handleLine(self, iTime_ms, strVerb, strPayload)

    if strVerb in (
            portable_grafana_datatypes.TAG_GRAFANA_NTP,
            portable_grafana_datatypes.TAG_GRAFANA_I2C_FREQUENCY_SELECTED_HZ,
            portable_grafana_datatypes.TAG_GRAFANA_MAC,
            portable_grafana_datatypes.TAG_GRAFANA_VERSION_FIRMWARE,
            portable_grafana_datatypes.TAG_GRAFANA_VERSION_SW,
            portable_grafana_datatypes.TAG_GRAFANA_ERROR,
          ):
      if strVerb == portable_grafana_datatypes.TAG_GRAFANA_NTP:
        iSecondsSince1970_UnixEpoch = int(strPayload)
        strPayload = 1000*iSecondsSince1970_UnixEpoch

      if strVerb == portable_grafana_datatypes.TAG_GRAFANA_I2C_FREQUENCY_SELECTED_HZ:
        strPayload = int(strPayload)

      self.__addSummaryField(strVerb, strPayload)

  def __addSummaryField(self, strVerb, value):
      self.__dictSummaryFields[config_http_server.strInfluxDbSummaryPrefix+strVerb] = value

  def addMeasurement(self, objGrafanaValue, iTime_ms, strValue):
    iTime_ms = self.getTimeGrafana_ms(iTime_ms)
    fValue = objGrafanaValue.convert2float(strValue)

    # fDiskFree_MBytes
    strFieldName = objGrafanaValue.strName
    # 17
    strTagName = self.__strNodeName
    # print(objGrafanaValue.strInfluxDbTag)
    if objGrafanaValue.strInfluxDbTag == portable_grafana_datatypes.INFLUXDB_TAG_ENVIRONS:
      strFieldName = 'fTempEnvirons_C'
      # 58
      strTagName += '-' + objGrafanaValue.strName

    dictMeasurement = {
      'time': iTime_ms,
      'measurement': self.__strLabLabel,
      'tags': {
        objGrafanaValue.strInfluxDbTag: strTagName,
        config_http_server.strInfluxDbNameOrigin: config_http_server.strInfluxDbTagOrigin,
      },
      'fields': {
        strFieldName: fValue,
      },
    }

    self.__listMeasurements.append(dictMeasurement)

  def handleAnnotation(self, iTime_ms, strVerb, strPayload):
    iTime_ms = self.getTimeGrafana_ms(iTime_ms)
    # 17
    strNodeName = self.__strNodeName
    # LabHombi
    strLabLabel = self.__strLabLabel
    dictAnnotation = {
                'time': iTime_ms,
                'measurement': strLabLabel,
                'fields': {
                  'title': '%s %s %s' % (strVerb.upper(), strLabLabel, strNodeName),
                  'text': strPayload,
                  'tags': strVerb,  # Comma separated string
                },
                'tags': {
                  'node': strNodeName,
                  'type': portable_grafana_datatypes.INFLUXDB_TYPE_EVENT,
                  'severity': strVerb,
                  config_http_server.strInfluxDbNameOrigin: config_http_server.strInfluxDbTagOrigin,
                },
    }

    self.__listMeasurements.append(dictAnnotation)

  def __addSummary(self):
    # 17
    strNodeName = self.__strNodeName
    # LabHombi
    strLabLabel = self.__strLabLabel
    self.__addSummaryField(portable_grafana_datatypes.INFLUXDB_TAG_NODE, strNodeName)
    self.__addSummaryField(portable_grafana_datatypes.INFLUXDB_TAG_SITE, strLabLabel)
    dictSummary = {
                'time': self.__iMillisecondsSince1970_UnixEpochStart,
                'measurement': strLabLabel,
                'fields': self.__dictSummaryFields,
                'tags': {
                  'node': strNodeName,
                  'type': portable_grafana_datatypes.INFLUXDB_TYPE_SUMMARY,
                  config_http_server.strInfluxDbNameOrigin: config_http_server.strInfluxDbTagOrigin,
                },
              }
    print('*** Summary {}'.format(dictSummary))
    self.__listMeasurements.append(dictSummary)

  def __writeToInfluxDB(self, strFilenameFull):
    # Set up influxDB connection
    # url, port, user, pw, db
    objInfluxDBClient = openInfluxDb()

    self.__addSummary()

    # Write data to influxDB
    # https://influxdb-python.readthedocs.io/en/latest/api-documentation.html?highlight=time_precision
    # print('InfluxDB write %s:%d %s' % (config_http_server.strInfluxDbHost, config_http_server.strInfluxDbPort, config_http_server.strInfluxDbDatabase))
    print('%s: Writing %d measurements to InfluxDB...' % (os.path.basename(strFilenameFull), len(self.__listMeasurements)))
    bSuccess = objInfluxDBClient.write_points(self.__listMeasurements, time_precision='ms', protocol='json')

    objInfluxDBClient.close()
    assert bSuccess, 'Failed to write to influxdb.'

  def readFileAndWriteToDB(self, strFilenameFull):
    self.readFile(strFilenameFull)
    self.__writeToInfluxDB(strFilenameFull)

def loadFileIntoInfluxDb(strFilenameFull):
  objNtpTimeDumper = GrafanaInfluxGetNtpTime()
  objNtpTimeDumper.readFile(strFilenameFull)
  strMac = objNtpTimeDumper.strMac
  if strMac == None:
    raise Exception('This file has no strMac: ' + strMac)
  iMillisecondsSince1970_UnixEpochStart_StartOfFile = objNtpTimeDumper.iMillisecondsSince1970_UnixEpochStart_StartOfFile
  if iMillisecondsSince1970_UnixEpochStart_StartOfFile == None:
    raise Exception('This file has no StartOfFile-Time: ' + strFilenameFull)

  objInfluxDbDumper = GrafanaInfluxDbDumper(strMac, iMillisecondsSince1970_UnixEpochStart_StartOfFile)
  objInfluxDbDumper.readFileAndWriteToDB(strFilenameFull)

def writePng(strFilenameFull):
  strFilenamePngFull = strFilenameFull.replace('.txt', '.png')
  assert strFilenamePngFull != strFilenameFull

  print('%s: Writing PNG' % os.path.basename(strFilenamePngFull))

  import python3_grafana_log_config

  objDumper = python3_grafana_log_reader.GrafanaPlotDumper(python3_grafana_log_config.getPlotConfig())
  objDumper.readFile(strFilenameFull)
  objDumper.plot(strFilenamePngFull)

def processFiles(strDirectoryToBeProcessed, strDirectoryProcessed=None, strDirectoryFailed=None, bWritePng=False):
  for strFilename in sorted(os.listdir(strDirectoryToBeProcessed), reverse=True):
    if not strFilename.endswith('.txt'):
      continue
    strFromFilenameFull = os.path.join(strDirectoryToBeProcessed, strFilename)

    if strFilename.endswith('_' + config_app.LOGFILENAME_GRAFANA):
      try:
        loadFileIntoInfluxDb(strFromFilenameFull)
      except Exception as e:
        print('loadFileIntoInfluxDb() failed: %s' % str(e))
        traceback.print_exc()
        if strDirectoryFailed != None:
          strToFilenameFull = os.path.join(strDirectoryFailed, strFilename)
          shutil.move(strFromFilenameFull, strToFilenameFull)
          continue

      if bWritePng:
        writePng(strFromFilenameFull)

    if strDirectoryProcessed != None:
      strToFilenameFull = os.path.join(strDirectoryProcessed, strFilename)
      shutil.move(strFromFilenameFull, strToFilenameFull)

def delete():
  '''
    Dangerous! Will delete the whole database!
  '''
  objInfluxDBClient = openInfluxDb()
  # objInfluxDBClient.delete_series()
  objInfluxDBClient.delete_series(tags={config_http_server.strInfluxDbNameOrigin: config_http_server.strInfluxDbTagOrigin})
  objInfluxDBClient.close()

def reload_all():
  for strFilename in os.listdir(python3_http_server_lib.strHttpServerProcessedDirectory):
    if not strFilename.endswith('.txt'):
      continue
    strFromFilenameFull = os.path.join(python3_http_server_lib.strHttpServerProcessedDirectory, strFilename)

    if strFilename.endswith('_' + config_app.LOGFILENAME_GRAFANA):
      strToFilenameFull = os.path.join(python3_http_server_lib.strHttpServerToProcessDirectory, strFilename)
      shutil.move(strFromFilenameFull, strToFilenameFull)

  __processFiles()

if __name__ == '__main__':
  # loadFileIntoInfluxDb(r'C:\Projekte\temp_stabilizer_2018\temp_stabilizer_2018\software_regler\http_server\node_data\to_process\2018-11-04_16-52-47_httptest_4712_grafana.txt')
  # processFiles(http_server_lib.strHttpServerToProcessDirectory)
  
  processFiles(python3_http_server_lib.strHttpServerToProcessDirectory,
                                         python3_http_server_lib.strHttpServerProcessedDirectory,
                                         python3_http_server_lib.strHttpServerFailedDirectory,
                                         bWritePng=False)
