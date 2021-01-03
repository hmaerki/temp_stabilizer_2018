import os
import sys
import pathlib
from urllib.parse import urlparse

import flask
import jinja2
from werkzeug.exceptions import HTTPException

app = flask.Flask(__name__)
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True
# This will force exceptions when a variable is missing in a template
app.jinja_env.undefined = jinja2.StrictUndefined

strFileDirectory = pathlib.Path(__file__).absolute().parent
strHttpDirectory = strFileDirectory.parent.parent
sys.path.append(str(strFileDirectory))
sys.path.append(str(strHttpDirectory / 'node' / 'config'))
sys.path.append(str(strHttpDirectory / 'node' / 'program'))

import config_app
import config_http_server
import portable_firmware_constants
import python3_http_influxdb_loadfiles


@app.errorhandler(Exception)
def handle_exception(e):
    # pass through HTTP errors
    if isinstance(e, HTTPException):
        return e

    # now you're handling non-HTTP exceptions only
    return flask.render_template("500_generic.html", e=e), 500

@app.route('/')
def index():
  return flask.render_template('index.html', host=flask.request.host)

@app.route('/favicon.ico')
def favicon_ico():
  return '-'

@app.route('/index.html')
def index_html():
  return flask.redirect(flask.url_for('index'))

@app.route('/intro.html')
def intro():
  listLinks = []

  def addLink(strText, strLink):
    listLinks.append((strText, strLink))

  addLink('github', 'https://github.com/tempstabilizer2018group/tempstabilizer2018')
  # addLink('grafana', 'http://%(HTTP_HOST)s:3000' % environ)

  url_parsed = urlparse(flask.request.base_url)

  addLink('grafana', f'http://{url_parsed.hostname}:3000')
  addLink('summary (summary of configured against live nodes)', 'summary.html')
  addLink('summary_old (summary of configured against live nodes)', 'summary_old.html')
  addLink(portable_firmware_constants.strHTTP_PATH_VERSIONCHECK, '%(strHTTP_PATH_VERSIONCHECK)s?%(strHTTP_ARG_MAC)s=3C71BF0F97A4&%(strHTTP_ARG_VERSION)s=heads-SLASH-master;1' % portable_firmware_constants.__dict__)
  addLink(portable_firmware_constants.strHTTP_PATH_SOFTWAREUPDATE, '%(strHTTP_PATH_SOFTWAREUPDATE)s?%(strHTTP_ARG_MAC)s=3C71BF0F97A4&%(strHTTP_ARG_VERSION)s=heads-SLASH-master;1' % portable_firmware_constants.__dict__)

  addLink('influx db: delete (Dangerous! Will delete the whole database!)', flask.url_for('influxdb_delete'))
  addLink('influx db: reload all datafiles (Dangerous! Will delete the whole database!)', flask.url_for('influxdb_reload_all'))

  return flask.render_template('intro.html', listLinks=listLinks)

# TODO: OSOLETE REMOVED
@app.route('/summary_old.html')
def summary_old():
  import python3_wsgi_app_summary
  strHtml = python3_wsgi_app_summary.getSummary()
  return strHtml


@app.route('/summary.html')
def summary():
  import python3_http_summary
  table = python3_http_summary.Table()
  return flask.render_template('summary.html', table=table)


@app.route('/influxdb_delete')
def influxdb_delete():
    python3_http_influxdb_loadfiles.delete()
    return intro()


@app.route('/influxdb_reload_all')
def influxdb_reload_all():
    python3_http_influxdb_loadfiles.delete()
    python3_http_influxdb_loadfiles.reload_all()
    return intro()

def mandatory_arg(request, arg):
  value = request.args.get(arg, None)
  if value is None:
    raise Exception(f'Argument "{arg}" was not provided in "{request.full_path}"!')
  return value

class Git:
  def __init__(self, request):
    self.strMac = mandatory_arg(request, portable_firmware_constants.strHTTP_ARG_MAC)
    self.strVersion = mandatory_arg(request, portable_firmware_constants.strHTTP_ARG_VERSION)

    self.p = config_http_server.factoryGitHubPull()
    self.strVersionGit = self.p.setMac(self.strMac)

# GET /softwareupdate?mac=3C71BF0F97A4&version=heads-SLASH-master;1
@app.route(portable_firmware_constants.strHTTP_PATH_SOFTWAREUPDATE)
def softwareupdate():
  git = Git(flask.request)

  strTarFilename = git.p.strTarFilename
  strTarFilenameFull = git.p.getTar()
  if strTarFilenameFull is None:
    # Unknown Mac
    # Return "204 No content"
    return f'Unkown MAC address { git.strMac }', 204

  return flask.send_file(strTarFilenameFull, mimetype='application/octet-stream', as_attachment=True, attachment_filename=strTarFilename)


# GET /versioncheck?mac=3C71BF0F97A4&version=heads-SLASH-master;1
@app.route(portable_firmware_constants.strHTTP_PATH_VERSIONCHECK)
def versioncheck():
  git = Git(flask.request)

  return git.strVersionGit

@app.route(config_app.strHttpPostPath, methods=['POST'])
def upload():
  strMac = mandatory_arg(flask.request, portable_firmware_constants.strHTTP_ARG_MAC)
  strFilename = mandatory_arg(flask.request, portable_firmware_constants.strHTTP_ARG_FILENAME)

  strLogData = flask.request.data
  strLogData = strLogData.decode('utf-8')

  if len(strLogData) == 0:
    return 'No data received!', 400

  import python3_http_influxdb_loadfiles

  strFilenameFull = python3_http_influxdb_loadfiles.http_write_data(strMac, strFilename, strLogData)
  strResponse = f'strLogData: "{strLogData[0:10]}"\n'
  strResponse += f'strFilenameFull: "{strFilenameFull}"\n'

  return strResponse
