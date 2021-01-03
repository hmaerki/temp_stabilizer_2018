# -*- coding: utf-8 -*-

import io
import os
import sys
import time
import socket
import urllib
import logging

# https://docs.python.org/3/library/tarfile.html
import tarfile

# pip3 install PyGithub
# https://pygithub.readthedocs.io/en/latest/introduction.html
import github

# Rate Limit
# https://api.github.com/rate_limit
# https://developer.github.com/v3/rate_limit/
# https://developer.github.com/v3/#rate-limiting

# https://raw.githubusercontent.com/hmaerki/temp_stabilizer_2018/master/software/http_server/python/config_http_server.py

import python3_config_nodes_lib
import python3_http_server_lib
import portable_firmware_constants
import portable_constants
import config_http_server

strGithubRepoConfig = 'tempstabilizer2018group/tempstabilizer2018'
strGithubUser = 'tempstabilizer2018group'
strGithubPw = 'xxx'
strGithubToken = None

strFILENAME_CONFIG_NODES = '/software/http_server/python/config_nodes.py'
strDIRECTORY_NODE = 'software/node'
assert strFILENAME_CONFIG_NODES.startswith('/')
assert '\\' not in strFILENAME_CONFIG_NODES
assert not strDIRECTORY_NODE.startswith('/')
assert '\\' not in strDIRECTORY_NODE

listGitPrefixes = ('heads', 'tags')

URL_TAG_REPO = ';strRepo='

def escape(s):
  for strChar, strEscape in portable_constants.listReplacements:
    s = s.replace(strChar, strEscape)
  return s

def unescapeSwVersion(strVersionFull):
  # heads-SLA-master;2;strRepo=-APR-local-SP-on-SP-raspberrypi-APR-
  # ->
  # heads/master;2
  l = strVersionFull.split(URL_TAG_REPO, 2)
  if len(l) != 2:
    return strVersionFull
  strVersion, strDummy = strVersionFull.split(URL_TAG_REPO, 2)
  for strChar, strEscape in portable_constants.listReplacements:
    strVersion = strVersion.replace(strEscape, strChar)
  # heads/master;2
  return strVersion

def writeToApacheErrorLog(msg):
  sys.stderr.write(msg + '\n')

class GithubPullBase:
  def __init__(self, strDirectory=None):
    if strDirectory == None:
      strDirectory = python3_http_server_lib.strHttpServerSwDownloadDirectory
      # strDirectory = '/tmp'
    self.__strDirectory = os.path.abspath(strDirectory)
    self._strGitRepo = None
    self._strGitTags = None

  def setMac(self, strMac):
    # Get the most actual config file from github
    objConfigNodes = self._getConfigNodesFromGithub()

    # Find the mac we are looking for
    self.objNode = objConfigNodes.findNodeByMac(strMac)

    # remember it
    self.setTags(self.objNode.strGitRepo, self.objNode.strGitTags)

    # return the version string
    return self._strGitTagsEscaped

  def setTags(self,  strGitRepo, strGitTags):
    assert self._strGitRepo == None, 'This methode must only be called once!'
    assert self._strGitTags == None, 'This methode must only be called once!'
    self._strGitRepo = strGitRepo
    self._strGitTags = strGitTags

    strGitTags += "%s'%s'" % (URL_TAG_REPO, self._getRepo())
    # Escape characters in the tags, but not the ';' between the git-tags
    self._strGitTagsEscaped = ';'.join(map(escape, strGitTags.split(';')))

    self.__strTarFilename = 'node_%s.tar' % self._strGitTagsEscaped
    self.__strTarFilenameFull = os.path.join(self.__strDirectory, self.__strTarFilename)


  def skipDirectory(self, strDirectory):
    if strDirectory.find('.git') >= 0:
      return True
    return False
    
  def skipFile(self, strFilename):
    if strFilename.find('.git') >= 0:
      return True
    if strFilename.find('_SKIP') >= 0:
      return True
    return False

  @property
  def strTarFilename(self):
    return self.__strTarFilename

  def getTar(self):
    if config_http_server.bCacheTarFiles:
      if os.path.exists(self.__strTarFilenameFull):
        logging.info('Tarfile already in cache. skip download....')
        return self.__strTarFilenameFull

    dictFiles = self._fetchFromGithub()
    if config_http_server.bDoMpyCrossCompile:
      dictFiles = self.crossCompilePythonFiles(dictFiles)
    self.__writeTar(dictFiles)
    return self.__strTarFilenameFull

  # TODO: OBSOLETE REMOVE
  def getTarContent(self):
    strFilenameFull = self.getTar()
    if strFilenameFull == None:
      # Unknown Mac
      # https://modwsgi.readthedocs.io/en/develop/user-guides/debugging-techniques.html
      writeToApacheErrorLog('Unknown Mac')
      return None
    with open(strFilenameFull, 'rb') as f:
      strTarContent = f.read()
    return strTarContent

  def crossCompilePythonFiles(self, dictFiles):
    dictFiles2 = {}

    for strFilename, byteData in sorted(dictFiles.items()):
      if (not strFilename.endswith('.py')) or (strFilename == 'main.py'):
        # Non python file: skip
        dictFiles2[strFilename] = byteData
        continue

      # Python file: compile
      strFilename2, byteData2 = self.crossCompilePythonFile(strFilename, byteData)
      dictFiles2[strFilename2] = byteData2

    return dictFiles2

  def crossCompilePythonFile(self, strFilename, byteData):
    strFilenameMpy = strFilename.replace('.py', '.mpy')
    assert strFilenameMpy != strFilename
    if os.path.exists(strFilename):
      os.remove(strFilename)
    if os.path.exists(strFilenameMpy):
      os.remove(strFilenameMpy)

    TMPDIR = '/tmp/mpy-cross-tmp'
    strFilenameFull = os.path.join(TMPDIR, strFilename)
    strBaseDir = os.path.dirname(strFilenameFull)
    if not os.path.exists(strBaseDir):
      os.makedirs(strBaseDir)
    with open(strFilenameFull, 'wb') as f:
      f.write(byteData)
    import subprocess
    # subprocess.check_call([config_http_server.strMpyCrossFilenameFull, '-v', '-mno-unicode', '-X', 'emit=bytecode', strFilenameFull])
    subprocess.check_call([config_http_server.strMpyCrossFilenameFull, strFilenameFull])
    strFilenameMpyFull = os.path.join(TMPDIR, strFilenameMpy)
    with open(strFilenameMpyFull, 'rb') as f:
      byteDataMpy = f.read()
    return strFilenameMpy, byteDataMpy
  
  '''
    'heads/master' is a Git-Tag: It may be retrieved from git
    '5' is a User-Tag: Just to distinguish one version from another.
  '''
  def _isUserTag(self, strGitTag):
    l = strGitTag.split('/', 1)
    if len(l) > 1:
      if l[0] in listGitPrefixes:
        # 'heads/master'
        # l[0]: 'heads'
        return False
    return True

  '''
    'heads/master' => 'master'
  '''
  def _getGitTagWithoutPrefix(self, strGitTag):
    l = strGitTag.split('/', 1)
    if len(l) > 1:
      return l[1]
    return l[0]

  def _getDictNodesFromString(self, strConfigNodes):
    dictGlobals = {}
    dictLocals = {}
    exec(strConfigNodes, dictGlobals, dictLocals)
    return dictLocals['dictConfigNodes']

  def _getConfigNodesFromGithub(self):
    '''
      We read 'config_nodes.py' from github.
      Then we call findTagsByMac(strMac) to get strGitTags
    '''
    logging.info('Get "config_nodes.py" from github....')
    dictConfigNodes = self._getConfigNodesFromGithub2()
    objConfigNodes = python3_config_nodes_lib.ConfigNodes(dictConfigNodes)
    return objConfigNodes

  def _selectFile(self, strFilenameRelative):
    '''
      strFilenameRelative is absolute within the Git-repostitory and in the local filesystem relativ to the Git-root.
      The filename returned is relative to the node-folder which will be deployed to the target.
    '''
    if not strFilenameRelative.startswith(strDIRECTORY_NODE):
      # We are only interested in files of the node-directory
      return None
    assert not strFilenameRelative[0] in r'.\/', ('Backslash in "%s"' % strFilenameRelative)
    strFilenameRelative2 = strFilenameRelative[len(strDIRECTORY_NODE)+1:]
    if strFilenameRelative2.endswith('.py'):
      # We are only interested in python-files
      return strFilenameRelative2
    if strFilenameRelative2.endswith('.TXT'):
      # REPLICATE_ONCE.TXT
      return strFilenameRelative2
    return None

  def createDirectoryIfNeeded(self):
    strDirectory = os.path.dirname(self.__strTarFilenameFull)
    if not os.path.exists(strDirectory):
      os.makedirs(strDirectory)

  def __writeTar(self, dictFiles):
    self.createDirectoryIfNeeded()

    with tarfile.open(self.__strTarFilenameFull, 'w') as tar:

      def addFile(strFilename, byteData):
        info = tarfile.TarInfo(name=strFilename)
        info.size = len(byteData)
        tar.addfile(info, io.BytesIO(byteData))

      for strFilename, byteData in sorted(dictFiles.items()):
        addFile(strFilename, byteData)

      # The update iscomplete if the version file is written.
      # Therefore this file goes last!
      addFile(portable_firmware_constants.strFILENAME_VERSION, bytes(self._strGitTagsEscaped.encode('utf8')))

'''
  Instead of connecting to Github, this class reads from the local filesystem.
  This is useful when developing software on the raspberry pi: When the node
  does an update, the local code will be deployed.
'''
class GitHubPullLocal(GithubPullBase):
  def __init__(self, strDirectory=None):
    import config_nodes
    self.__strSourceDirectory = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

    # We may directly access config_nodes. However in apache, we must read the actual file!
    # with io.open(config_nodes.__file__, 'r', encoding='utf8') as f:
    with open(config_nodes.__file__, 'r') as f:
      strConfigNodes = f.read()

    self.__dictConfigNodes = self._getDictNodesFromString(strConfigNodes)
    GithubPullBase.__init__(self, strDirectory)

  def _getRepo(self):
    return 'local on ' + socket.gethostname()

  def _getConfigNodesFromGithub2(self):
    return self.__dictConfigNodes
 
  def _fetchFromGithub(self):
    dictFiles = {}
    for strRootDirectory, listDirsDummy, listFilenames in os.walk(self.__strSourceDirectory):
      if self.skipDirectory(strRootDirectory):
        # For example the '.git'-directory
        continue

      assert strRootDirectory.startswith(self.__strSourceDirectory)
      strRootDirectoryRelative = strRootDirectory[len(self.__strSourceDirectory)+1:]
      strRootDirectoryRelative = strRootDirectoryRelative.replace('\\', '/')
      for strFilename in listFilenames:
        if self.skipFile(strFilename):
          # For example '.gitignore'
          continue
        strFilenameRelative = strRootDirectoryRelative + '/' + strFilename
        strFilenameRelative2 = self._selectFile(strFilenameRelative)
        if strFilenameRelative2 == None:
          continue
        # print(strFilenameRelative2)
        strFilenameFull = os.path.join(strRootDirectory, strFilename)
        with io.open(strFilenameFull, 'r', encoding='utf8') as fIn:
          strContents = fIn.read()
          strContents = strContents.encode('utf8')
          dictFiles[strFilenameRelative2] = strContents
    return dictFiles

'''
  This will use the Github API - but is limited by 60 requests...
'''
class GitHubApiPull(GithubPullBase):
  def __init__(self, strDirectory=None):
    GithubPullBase.__init__(self, strDirectory)

  def __openRepo(self, strGithubRepo):
    # objGithub = github.Github(strGithubUser, strGithubPw)
    if strGithubToken == None:
      objGithub = github.Github()
    else:
      objGithub = github.Github(login_or_token=strGithubToken)
    return objGithub.get_repo(strGithubRepo)

  def _getRepo(self):
    return 'www.github.com via %s' % socket.gethostname()

  def _getConfigNodesFromGithub2(self):
    objGitRepo = self.__openRepo(strGithubRepoConfig)
    objGitFile = objGitRepo.get_file_contents(path=strFILENAME_CONFIG_NODES, ref='heads/master')
    strConfigNodes = objGitFile.decoded_content
    return self._getDictNodesFromString(strConfigNodes)

  def _fetchFromGithub(self):
    objGitRepo = self.__openRepo(self._strGitRepo)

    dictFiles = {}

    for strGitTag in self._strGitTags.split(';'):
      logging.debug('  Tag: %s' % strGitTag)
      if self._isUserTag(strGitTag):
        # User Tags don't pull from github
        continue
      try:
        objGitTag = objGitRepo.get_git_ref(strGitTag)
      except github.UnknownObjectException:
        raise Exception('Tag "%s" does not exist in git-repository "%s"' % (strGitTag, self._strGitRepo))

      objGitTree = objGitRepo.get_git_tree(objGitTag.object.sha, recursive=True)
      for objGitFile in objGitTree.tree:
        logging.debug('    File: %s' % objGitFile.path)
        strFilenameRelative2 = self._selectFile(objGitFile.path)
        if strFilenameRelative2 == None:
          continue
        if self.skipFile(strFilenameRelative2):
          continue
        if objGitFile.path in dictFiles:
          logging.debug('      Alreadey added, would be overwritten - skipped....')
          continue
        if objGitFile.type != 'blob':
          logging.debug('      Not a blob, skipped....')
          continue
        objGitContents = objGitRepo.get_file_contents(path=objGitFile.path, ref=strGitTag)
        dictFiles[strFilenameRelative2] = objGitContents.decoded_content
    return dictFiles

'''
  This will use the Github public urls
'''
class GitHubPublicPull(GithubPullBase):
  strUrlFileTemplate = 'https://raw.githubusercontent.com/%s/%s/%s'
  strUrlZipTemplage = 'https://github.com/%s/archive/%s.zip'

  def getFileUrl(self, strGithubRepoConfig, strTag, strFile):
    strTagWithoutPrefix = self._getGitTagWithoutPrefix(strTag)
    if strFile.startswith('/'):
      strFile = strFile[1:]
    return self.strUrlFileTemplate % (strGithubRepoConfig, strTagWithoutPrefix, strFile)

  def getZipUrl(self, strGithubRepoConfig, strTag):
    strTagWithoutPrefix = self._getGitTagWithoutPrefix(strTag)
    return self.strUrlZipTemplage % (strGithubRepoConfig, strGithubRepoConfig)

  def getFromHttp(self, strUrl):
    logging.info('get %s' % strUrl)
    try:
      with urllib.request.urlopen(strUrl) as f:
        bData = f.read()
        return bData
    except Exception as e:
      raise Exception(f'Failed to get "{strUrl}": {e}')

  def __init__(self, strDirectory=None):
    GithubPullBase.__init__(self, strDirectory)

  def _getRepo(self):
    return f'www.github.com via {socket.gethostname()}'

  def _getConfigNodesFromGithub2(self):
    # https://raw.githubusercontent.com/tempstabilizer2018group/tempstabilizer2018/master/software/http_server/python/config_nodes.py
    strFileUrl = self.getFileUrl(strGithubRepoConfig, 'heads/master', strFILENAME_CONFIG_NODES)
    bConfigNodes = self.getFromHttp(strFileUrl)
    strConfigNodes = bConfigNodes.decode('utf8')
    return self._getDictNodesFromString(strConfigNodes)

  def __openRepo(self, strGithubRepo):
    # objGithub = github.Github(strGithubUser, strGithubPw)
    if strGithubToken == None:
      objGithub = github.Github()
    else:
      objGithub = github.Github(login_or_token=strGithubToken)
    self.throwRateLimitException(objGithub)
    return objGithub.get_repo(strGithubRepo)

  def throwRateLimitException(self, objGithub):
    # Empirical measurments given that the counter decrements by 3 for one software update.
    LOW_LIMIT = 5
    rate_remaining, rate_limit = objGithub.rate_limiting
    rate_resettime = objGithub.rate_limiting_resettime
    reset_time_min = (rate_resettime - time.time())/60.0
    msg = f'Github Ratelimit: Remaining {rate_remaining} of {rate_limit}. Limit set to {LOW_LIMIT}. Will reset in {reset_time_min:0.0f} min.'
    if rate_remaining < LOW_LIMIT:
      writeToApacheErrorLog('Exception: %s' % msg)
      raise Exception(msg)

    # Write to apache-log file
    writeToApacheErrorLog(msg)

  def _fetchFromGithub(self):
    objGitRepo = self.__openRepo(self._strGitRepo)

    dictFiles = {}

    for strGitTag in self._strGitTags.split(';'):
      logging.debug('  Tag: %s' % strGitTag)
      if self._isUserTag(strGitTag):
        # User Tags don't pull from github
        continue
      try:
        objGitTag = objGitRepo.get_git_ref(strGitTag)
      except github.UnknownObjectException:
        raise Exception('Tag "%s" does not exist in git-repository "%s"' % (strGitTag, self._strGitRepo))

      objGitTree = objGitRepo.get_git_tree(objGitTag.object.sha, recursive=True)
      for objGitFile in objGitTree.tree:
        logging.debug('    File: %s' % objGitFile.path)
        strFilenameRelative2 = self._selectFile(objGitFile.path)
        if strFilenameRelative2 == None:
          continue
        if self.skipFile(strFilenameRelative2):
          continue
        if objGitFile.path in dictFiles:
          logging.debug('      Alreadey added, would be overwritten - skipped....')
          continue
        if objGitFile.type != 'blob':
          logging.debug('      Not a blob, skipped....')
          continue
        strPath = objGitFile.path
        # https://raw.githubusercontent.com/hmaerki/temp_stabilizer_2018/master/software/node/config/config_app.py
        strFileUrl = self.getFileUrl(self._strGitRepo, strGitTag, strPath)
        bFileContent = self.getFromHttp(strFileUrl)
        dictFiles[strFilenameRelative2] = bFileContent
    return dictFiles

if __name__ == '__main__':
  pass
  # p = GithubPull('x1.0;y1.1')
  # strTarFilenameFull = p.getTar()
