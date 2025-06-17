# Family Calendar

This is a small webapp for running a house-hold calendar.

It's not fancy, and tries to have a minimal list of top-level dependencies.

How is it used?

  - create a venv or have a python3 environment
  - `pip install -r requirements.txt`
  - figure out your configuration
  - run the `familycal` script in your python env's bin dir, maybe like `./env/bin/familycal /path/to/your/config.toml`
  - open the service where you've configured it, maybe `http://localhost:8000`

The service will connect to the configured caldav server, and fetch the
configured calendars you included. It caches these in memory for the duration
of the services life.

There are buttons in the web interface to sync the cached calendars,
and to refresh the cached calendars. The web interface also attempts to
sync and refresh the calendar every 10 minutes.


# What a config looks like

```toml
# vi: ft=toml
[app]
debug = true

familyname = "The"
baseurl = "http://localhost:8000"

[calendars]
url = "https://your.caldav.service/url"
username = "your_username"
password = "your_password"

include = [
    "a",
    "list of",
    "calendar names",
    "found on the caldav",
    "server"
]

[calendars.colors]
[calendars.colors."calendar names"]
background = "#c4ffb3"
text = "#000"


[server]
host = "127.0.0.1"
port = 8000


[logging]
version = 1

[logging.loggers]
[logging.loggers.""]
level = "INFO"
handlers = ["console"]
[logging.loggers.familycal]
level="INFO"
qualname="familycal"
handlers=["console"]
propagate=0

[logging.handlers]
[logging.handlers.console]
class="logging.StreamHandler"
level="INFO"
formatter="simple"

[logging.formatters]
[logging.formatters.simple]
format="%(asctime)s (%(name)s) [%(levelname)s] %(message)s"
```
