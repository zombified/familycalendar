import asyncio
from collections import namedtuple
import contextlib
import datetime
import json
import mimetypes
import pathlib
import re
import sys
from urllib.parse import unquote, parse_qs

# https://github.com/audivir/caldav2ics/blob/main/caldav2ics.py
#   -- this was helpful to see an example
#      of usage for caldav, even if its ideas
#      aren't really used here (maybe a little,
#      but not really specifically)
import caldav
import icalendar
import recurring_ical_events
import uvicorn

from familycal.settings import config, logger, package_dir
from familycal.asgi import (
    html_response,
    json_response,
    plaintext_response,
    Response,
    run_at_startup,
    sys_route,
)


CALENDAR_SYNC = {}
CALENDAR_CACHE = {}

STATIC_PATH = r"^/static/(.+)$"


def gen_calendar_cache():
    logger.info("generating calendar cache...")
    st = datetime.datetime.now()

    for calname in CALENDAR_SYNC.keys():
        timezones_cache = []
        calendar = icalendar.Calendar()
        events = []
        for obj in CALENDAR_SYNC[calname]:
            cal_ = icalendar.Calendar.from_ical(obj._data)
            for timezone in cal_.walk("VTIMEZONE"):
                if timezone["tzid"] not in timezones_cache:
                    timezones_cache.append(timezone["tzid"])
                    calendar.add_component(timezone)
            for event in cal_.walk("VEVENT"):
                event_copy = icalendar.Event(event)
                events.append(event_copy)

        for event in events:
            calendar.add_component(event)

        CALENDAR_CACHE[calname] = calendar

    en = datetime.datetime.now()
    td = en - st
    logger.info(f"... took {td.seconds}s")


@sys_route("static", STATIC_PATH)
async def static(scope):
    matches = re.match(STATIC_PATH, unquote(scope["path"]))
    if matches is None:
        return html_response(404, [], "Not Found")
    staticpath = package_dir() / pathlib.Path("static/")
    if not staticpath.exists():
        return html_response(404, [], "Not Found")
    respath = staticpath / pathlib.Path(matches.group(1))
    if not respath.exists():
        return html_response(404, [], "Not Found")

    mimetype, encoding = mimetypes.guess_type(respath.name)
    fin = open(respath, "rb", buffering=0)
    # TODO: do I want to send file size back too?
    return Response(200, [
        ["Content-Type", mimetype]
    ], fin)


@sys_route("sync", r"^/sync$")
async def sync(scope):
    for calendar in CALENDAR_SYNC.keys():
        CALENDAR_SYNC[calendar].sync()

    gen_calendar_cache()

    return plaintext_response(200, [], b"")


@sys_route("events", r"^/events$")
async def events(scope):
    global CALENDAR_SYNC
    global CALENDAR_CACHE

    qs = parse_qs(scope.get("query_string", ""))
    startstr = qs.get(b'start', None)
    endstr = qs.get(b'end', None)

    if startstr is None:
        now = datetime.datetime.now()
        weekday = now.weekday()
        start_of_week = now - datetime.timedelta(days=weekday)
        startstr = start_of_week.isoformat()
    else:
        startstr = startstr[0].decode("utf-8")

    if endstr is None:
        now = datetime.datetime.now()
        weekday = now.weekday()
        end_of_week = now + datetime.timedelta(days=(6 - weekday))
        endstr = end_of_week.isoformat()
    else:
        endstr = endstr[0].decode("utf-8")

    start = datetime.datetime.fromisoformat(startstr)
    end = datetime.datetime.fromisoformat(endstr)

    calendar_names = CALENDAR_CACHE.keys()

    events = []
    for calendar_name in calendar_names:
        ical_events = recurring_ical_events \
            .of(CALENDAR_CACHE[calendar_name]) \
            .between(
                (start.year, start.month, start.day),
                (end.year, end.month, end.day))

        colors = config.get("calendars", {}).get("colors", {})
        bgcolor = colors.get(calendar_name, {}).get("background", "#00F")
        textcolor = colors.get(calendar_name, {}).get("text", "#000")

        for event in ical_events:
            jsevent = {
                "id": str(event.uid),
                "resourceIds": [],
                #"allDay": True,  # defaults should be sane
                "start": str(event.start.isoformat()),
                "end": str(event.end.isoformat()),
                "title": str(event["SUMMARY"]),
                "editable": False,
                "startEditable": False,
                "durationEditable": False,
                "display": "auto",
                "backgroundColor": bgcolor,
                "textColor": textcolor,
                "classNames": [],
                "extendedProps": {},
            }
            events.append(jsevent)

    return json_response(200, [], events)


@sys_route("index", r"^/$")
async def index(scope):
    appconfig = config.get("app", {})

    baseurl = appconfig.get("baseurl", None)
    if baseurl is None:
        logger.error("baseurl not configured")
        return plaintext_response(500, [], b"")

    familyname = appconfig.get("familyname", "").strip()
    familynamesp = ""
    if len(familyname) > 0:
        familynamesp = f"{familyname} "

    auto_daynight = appconfig.get("auto_daynight", False)
    daystart = appconfig.get("daystart", 6)
    dayend = appconfig.get("dayend", 18)

    html = f"""<html>
<head>
  <title>{familynamesp}Family Calendar</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@event-calendar/build@4.4.0/dist/event-calendar.min.css">
  <script src="https://cdn.jsdelivr.net/npm/@event-calendar/build@4.4.0/dist/event-calendar.min.js"></script>
  <link rel="stylesheet" href="{baseurl}/static/style.css" />
  <!--
    Schedule_or_Calendar_Flat_Icon.svg from Wikimedia Commons by Videoplasty.com, CC-BY-SA 4.0
  //-->
  <link rel="icon" href="{baseurl}/static/Schedule_or_Calendar_Flat_Icon.svg" type="image/svg+xml">
  <script src="{baseurl}/static/script.js"></script>
</head>
<body>
  <nav class='ec-toolbar extramenu'>
    <div class='ec-start row'>
        <img class='col' src="{baseurl}/static/Schedule_or_Calendar_Flat_Icon.svg" height="32" width="32" />
        <div class='col title'>{familynamesp}Family Calendar</div>
    </div>
    <div class='ec-center'></div>
    <div class='ec-end'>
      <div class='ec-button-group'>
        <button class='ec-button' onclick='calendar_update("{baseurl}")'>&#8635;</button>
        <button class='ec-button' onclick='document.body.classList.toggle("ec-dark")'>&#9788;</button>
      </div>
    </div>
  </nav>
  <div id='ecdiv'></div>
  <script>
  var auto_daynight = {'true' if auto_daynight else 'false'};
  var daystart = {daystart};
  var dayend = {dayend};
  var ec = EventCalendar.create(document.getElementById("ecdiv"), {{
      view: "timeGridWeek",
      scrollTime: "05:00:00",
      nowIndicator: true,
      selectable: false,
      locale: "en-US",
      dayHeaderFormat: {{
          weekday: "short",
          month: "numeric",
          day: "numeric",
      }},
      eventTimeFormat: {{
          hour12: true,
          hour: "numeric",
          minute: "numeric"
      }},
      headerToolbar: {{
          start: "prev,next today",
          center: "title",
          end: "dayGridMonth,timeGridWeek,timeGridDay,listWeek",
      }},
      eventSources: [
          {{url: "{baseurl}/events",}},
      ],
      views: {{
        timeGridWeek: {{pointer: true}},
      }},
  }});

  window.onload = function() {{
    // update calendar every 10 minutes
    setInterval(() => {{
      calendar_sync("{baseurl}");
      calendar_refresh();
    }} , 600000);

    // we want to start checking day/night on the next hour
    let dt = new Date();
    const m = dt.getMinutes();
    const s = dt.getSeconds();
    const ms = dt.getMilliseconds();
    const ms_until = ((60 - m) * 60 * 1000) - (s * 1000) - ms;
    setTimeout(() => {{
        calendar_auto_daynight(auto_daynight, daystart, dayend);
        setInterval(calendar_auto_daynight, 60 * 60 * 1000, [
            auto_daynight,
            daystart,
            dayend,
        ]);
    }}, ms_until)
  }};
  </script>
</body>
</html>"""
    return html_response(200, [], html)


@run_at_startup()
def startup():
    global CALENDAR_SYNC
    global CALENDAR_CACHE

    if len(CALENDAR_SYNC.keys()) > 0:
        # if there are already things cached, then we don't need
        # to re-cache. Let another operation perform a sync
        return

    logger.info("syncing calendars...")
    st = datetime.datetime.now()

    calendars_to_include = config.get("calendars", {}).get("include", [])

    caldav_url = config.get("calendars", {}).get("url", None)
    username = config.get("calendars", {}).get("username", None)
    password = config.get("calendars", {}).get("password", None)
    with caldav.DAVClient(url=caldav_url, username=username, password=password) as client:
        principal = client.principal()
        # all calendars the caldav connection has access to
        for davcal in principal.calendars():
            # skipping the ones not configured to be fetched
            if davcal.name not in calendars_to_include:
                logger.warning(f"calendar '{davcal.name}' not found in inclusion list")
                continue

            logger.info(f"-> syncing: {davcal.name}")
            st2 = datetime.datetime.now()
            CALENDAR_SYNC[davcal.name] = davcal.objects(load_objects=True)
            en2 = datetime.datetime.now()
            td2 = en2 - st2
            logger.info(f"-->--> took {td2.seconds}s for {davcal.name}")

    en = datetime.datetime.now()
    td = en - st
    logger.info(f"took {td.seconds}s total")

    gen_calendar_cache()


def run():
    try:
        uvicorn.run(
            "familycal.asgi:app",
            host=config.get("server", {}).get("host", "127.0.0.1"),
            port=config.get("server", {}).get("port", 8000),
            log_level="info"
        )
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("👋bye")
