# Home
Built this project for my home control panel. Suitable for Swidish people.
Application is built on a text based UI to save memory.

## Dependencies
```bash
pip install textual textual-dev pytz requests
```

## Config
Config settings can be found in `/config.json`.
- `trainApiUrl`: The train information API URL.
- `myStationCode`: The closest station code. Station codes are updated from API daily. But it doesn't change most of the time. Find the current codes in `/example_response/TrainStations.json`. `LocationSignature` is the code I'm referring to.
- `message`: Settings for the train messages.
  - `updateIntervalMin`: How often are the messages updated.
  - `scrollSpeed`: When the message is too long to fit in the screen, this parameter controls how fast it scrolls. The value is a time in seconds that the messages moves. Every time the whole message will move 1 character left.
  - `margin`: We don't want the message to move all the time. So it will stop at the beginning and the end. The way how this is implemented is that we put some virtual characters at the beginning and the end. They are not visible, but occupies 1 position. While moving the virtual characters the message stays.
- `apiFreqCheck`: Every `apiFreqCheck` seconds we check if we should call the API to refresh data.
- `apiFreqControl`: Because the API is free but have limited quota (10000 times per month). Access frequency needs to be regulated. The script follows the following table to access API.
    |    Time     | Interval(min) | Total |
    | :---------: | :-----------: | :---: |
    | 00:00~07:00 |      30       |  14   |
    | 07:00~09:00 |       2       |  60   |
    | 09:00~17:00 |      10       |  48   |
    | 17:00~19:00 |       2       |  60   |
    | 19:00~24:00 |      10       |  30   |
    |Total: 212/day|||
- `stationUpdateInterval`: Because the stations doesn't change easily. We only update the station list once a day.
- `title`: The title showing on top of the screen.

For security reasons, keys are not saved in the `config.json`. I suggest you can fill them in  `my_keys.sh`. Remember, never push the key to Github.

## Run
```bash
source ./my_keys.sh
./home.py
```