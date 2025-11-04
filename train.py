from datetime import datetime
from textual.widgets import DataTable, Static, Rule
from common_widgets import *
from libs.traffic_api import *
from libs.utils import *
import pytz

class TrainStationMessage(Static):
    last_refresh = datetime.min
    def load_message(self):
        if is_freq_throttled(self.last_refresh):
            return
        lag_message = []
        normal_message = []
        error, messages_json = api_train_message()
        if error != None:
            logger.error("Can't access API to get train messages.")
            return
        else:
            for json in messages_json["RESPONSE"]["RESULT"][0]["TrainStationMessage"]:
                if json["Status"] == "Lag":
                    lag_message.append(json)
                else:
                    normal_message.append(json)
        self.remove_children()
        # TODO: The active days should be considered.
        for msg in lag_message:
            normalized_message = msg["FreeText"].replace("\n", "")
            self.mount(ScrollingLabel(normalized_message, classes="lag"))
            self.mount(Rule())
        for msg in normal_message:
            normalized_message = msg["FreeText"].replace("\n", "")
            self.mount(ScrollingLabel(normalized_message, classes="normal"))
            self.mount(Rule())
        self.set_loading(False)
        self.last_refresh = datetime.now()

    def get_visible_size(self):
        return self.content_size
    def on_mount(self):
        self.border_title = "Notices"
        self.set_loading(True)
        self.set_timer(1, self.load_message)
        self.set_interval(config["apiFreqCheck"], self.load_message)
    def refresh_message(self):
        self.load_message()

class TrainScheduleTable(DataTable):
    schedule_cache = []
    stations = []
    def __init__(self, schedule, stations):
        super().__init__()
        self.schedule_cache = schedule
        self.stations = stations

    def refresh_data(self):
        self.clear()
        for row in self.schedule_cache:
            time = datetime.fromisoformat(row["AdvertisedTimeAtLocation"])
            now = datetime.now(tz=pytz.UTC)
            track = row["TrackAtLocation"]
            from_station = "/".join([self.stations[loc] for loc in row["FromLocation"]])
            if now > time:
                # Train left
                delta = (now - time).total_seconds()
                to_station = "/".join(self.stations[loc] for loc in row["ToLocation"])
                line = "{f} :arrow_right: {t}".format(f=from_station, t=to_station)
                # Make the left train gray
                line = "[#808080]{line}[/#808080]".format(line=line)
                track = "[#808080]{track}[/#808080]".format(track=track)
                departure_time = "[#808080]{min}m ago[/#808080]".format(min=int(delta / 60))
            else:
                # Train arriving
                delta = (time - now).total_seconds()
                to_station = "/".join(["[bold][green]{loc}[/green][/bold]".format(loc=self.stations[loc]) for loc in row["ToLocation"]])
                line = "{f} :arrow_right: {t}".format(f=from_station, t=to_station)
                departure_time = "{min} min".format(min=int(delta / 60))
            self.add_row(line, track, departure_time)

    def on_mount(self):
        self.cursor_type = "none"
        self.refresh_data()
        self.set_interval(config["apiFreqCheck"], self.refresh_data)

class TrainSchedule(Static):
    stations = {}
    last_refresh = datetime.min
    def load_stations(self):
        error, stations_json = api_train_stations()
        if error != None:
            logger.error("Can't access API to get train stations.")
            return
        else:
            for json in stations_json["RESPONSE"]["RESULT"][0]["TrainStation"]:
                self.stations[json["LocationSignature"]] = json["AdvertisedLocationName"]
            logger.debug("Stations loaded: {stations}".format(stations=self.stations))
            self.border_subtitle = self.stations[config["myStationCode"]]
    def load_schedule(self):
        if is_freq_throttled(self.last_refresh):
            return
        error, schedule_json = api_train_announcement()
        if error != None:
            logger.error("Can't access API to get train stations.")
            return
        else:
            schedules = schedule_json["RESPONSE"]["RESULT"][0]["TrainAnnouncement"]
            table = TrainScheduleTable(schedules, self.stations)
            table.add_columns(*("Line", "Track", "Time"))
            if self.last_refresh != datetime.min:
                self.query_one(TrainScheduleTable).remove()
            self.mount(table)
            self.set_loading(False)
            self.last_refresh = datetime.now()
    def on_mount(self):
        self.border_title = "Schedules"
        self.set_loading(True)
        self.set_timer(1, self.load_stations)
        self.set_timer(1, self.load_schedule)
        # Refresh stations on a daily basis.
        self.set_interval(config["stationUpdateInterval"], self.load_stations)
        self.set_interval(config["apiFreqCheck"], self.load_schedule)

class Train(Static):
    def compose(self):
        yield TrainSchedule(id="schedule")
        yield TrainStationMessage(id="message")
        self.border_title = "Train Information"