# Watcher Dashboard

A free, self-hosted replacement for a DAKboard-style wall display, built for a
Raspberry Pi 4B plugged into a TV or monitor. It shows:

- **Clock and date**, with **countdowns** to dates you care about
- **Current weather, an hourly strip and a 5-day outlook**, plus UV, air quality, sunrise/sunset and moon phase (Open-Meteo, no account needed)
- **Severe weather banner** for active National Weather Service watches and warnings (US)
- **Live animated radar** for the last two hours (RainViewer, no account needed)
- **Stocks** (Finnhub, free API key) and a **favorite team tile** with record, next game and last result (ESPN)
- **Your calendars**, as many as you like, each in its own color (published ICS links, no Microsoft or Google developer setup)
- **Photo slideshow** from photos you add from your phone
- **Shared to-do list and a note** everyone in the house can see and edit from a phone
- **Scrolling news ticker** from RSS feeds (NPR, BBC, CBS by default)

![Dashboard](docs/dashboard.png)

Everything runs on the Pi. A small Python web server fetches the data on a timer
and serves one web page; Chromium shows that page full-screen at boot. After the
one-time install, **everything is managed from a settings page on your phone**
(or on the TV itself with a mouse or touchscreen). No subscriptions, no cloud
account, and your calendar links and keys never leave your home network.

---

## Part 1: Set up the Raspberry Pi (one time)

You need: a Raspberry Pi 4B (2 GB or more), a microSD card (16 GB+), a screen
with HDMI, and Wi-Fi or Ethernet.

1. On your computer, install **Raspberry Pi Imager** from
   <https://www.raspberrypi.com/software/>.
2. In Imager choose your Pi 4, then the OS **Raspberry Pi OS (64-bit)** (the
   normal one *with desktop*), then your SD card.
3. When Imager asks to customize settings, click **Edit settings** and set:
   - Hostname: `dashboard`
   - Username `pi` and a password you will remember
   - Your Wi-Fi name and password
   - Under **Services**, turn on **SSH** with password login
4. Write the card, put it in the Pi, connect the screen, and power it on. The
   first boot takes a couple of minutes.

## Part 2: Install the dashboard (the only terminal step)

On the Pi's desktop open **Terminal** from the top menu, or from your computer
run `ssh pi@dashboard.local`. Paste these lines one at a time:

```bash
sudo apt update && sudo apt full-upgrade -y
git clone https://github.com/schwadb/WatcherV1.git ~/WatcherV1
cd ~/WatcherV1/dashboard
bash deploy/install.sh
```

The install script takes about five minutes. It installs Chromium and the
Python packages, creates your settings and secrets files, sets the Pi's time
zone, turns off screen blanking, and sets the dashboard to start on boot. When
it finishes it prints the address of the settings page.

## Part 3: Finish setup from your phone

On any phone or laptop on the same Wi-Fi, open
**<http://dashboard.local:8080/manage>** (the script also prints the numeric
address, which works if `.local` names do not on your network).

**Settings tab → Keys & links.** Two panels need something from you:

- **Stocks: a free Finnhub API key.** Go to <https://finnhub.io/register>,
  create a free account, and copy the API key shown on your Finnhub dashboard.
- **Calendar: your Outlook calendar's link.** In Outlook on the web
  (<https://outlook.office.com>) click the gear icon → **Calendar** →
  **Shared calendars**. Under **Publish a calendar**, pick the calendar, choose
  **Can view all details**, click **Publish**, and copy the **ICS** link (the one
  ending in `.ics`). Paste it under **Calendars** (where you can also give it a
  color and add more calendars) or into the Outlook link field.

Press **Save**. The dashboard picks the change up by itself within a minute. The
**System** tab shows what is still missing.

If the Publish option is missing on a work account, your IT admin has turned
calendar publishing off. Ask them to allow it, or use a personal Outlook.com
calendar instead.

**Set a PIN** (same section) if other people use your Wi-Fi, so only you can
change settings.

## Part 4: Add photos

**Photos tab** → tap the box and pick photos from your phone. Big phone photos
are resized for the screen, and iPhone HEIC photos are converted. They appear in
the slideshow within seconds. The same tab lets you delete photos.

Other ways in: plug a USB stick into the Pi and copy files into
`~/WatcherV1/dashboard/photos/`, or from a computer run
`scp *.jpg pi@dashboard.local:~/WatcherV1/dashboard/photos/`.

## Part 5: Reboot

In the **System** tab press **Reboot the Pi** (or type `sudo reboot`). The Pi
starts up, the dashboard server starts, and Chromium opens the page full-screen.
The dashboard is also at <http://dashboard.local:8080> from any device on your
Wi-Fi.

---

## The settings page

<http://dashboard.local:8080/manage> has six tabs:

| Tab | What you can do |
|---|---|
| **Photos** | Add photos from your phone, see what's on the dashboard, delete |
| **To-do** | A shared household list. Add, check off, delete. Checked items disappear the next day. |
| **Notes** | A short message shown on the dashboard; saves as you type |
| **Settings** | Every setting: location by ZIP code, units, 24-hour clock, which panels to show, weather options, radar zoom, calendars with colors, stock symbols, your sports team (search by name), countdowns, news feeds, photo speed, screen schedule, and your keys and links |
| **Music** | Now-playing setup (Spotify) |
| **System** | Dashboard address, version, free disk, Pi temperature, which keys are set, and buttons to restart, update to the latest version, turn the screen off or on, and reboot |

Changes apply right away; the dashboard page reloads itself when settings change.

**On the TV itself:** plug a mouse, keyboard or touchscreen into the Pi, move the
mouse or touch the screen, and tap the gear in the top-right corner (or press
`S`). The same settings page opens on the TV with larger buttons, a
**Back to dashboard** link, and an on-screen keyboard for touchscreens.

**Hiding panels:** turn off anything you don't use under Settings → Panels. The
neighbors expand to fill the space. Turn off the radar and the weather panel gets
taller; turn off stocks and the photo gets the whole middle column.

## Where your settings live

- `~/WatcherV1/dashboard/config.yaml` holds every setting. The settings page edits
  it for you (keeping the comments), and the file is yours: updates never touch it.
  If you like, you can edit it by hand and restart with `sudo systemctl restart dashboard`.
- `~/WatcherV1/dashboard/.env` holds your keys, links and PIN.
- `~/WatcherV1/dashboard/photos/` is the photo folder and `data/` holds the to-do list and notes.

### Several calendars, each with a color

Any calendar that can give you a public ICS link works: Outlook (Publish a
calendar), Google Calendar (Settings → your calendar → "Secret address in iCal
format"), iCloud (share the calendar as public). Add each under Settings →
Calendars with a name and a color. Every event on the dashboard gets a stripe in
its calendar's color and a small legend appears in the panel header. One calendar
failing never hides the others. (In `config.yaml` a link can also be written as
`"${NAME}"` to read it from `.env`.)

### Severe weather banner

When the National Weather Service has an active watch, warning or advisory for
your location, a red (warning), orange (watch) or yellow (advisory) banner
appears across the top of the photo panel with the alert name and when it ends.
Nothing shows when there are no alerts. Outside the US it does nothing; turn it
off under Settings → Weather.

### Countdowns

Settings → Countdowns: a title, a date and an optional emoji. The clock panel
shows up to three upcoming countdowns. Past dates disappear by themselves.

### Favorite team

Settings → Sports team: search by name (college and pro football, basketball,
baseball, hockey, MLS) and pick your team. The tile shows the record and
standing, the next game with TV channel, the last result, and the live score
while a game is on. The data comes from ESPN's public site.

### Screen schedule

Settings → Screen schedule: a time to turn the screen off at night and on in the
morning, and a time from which the page dims. See the "Turning the TV off at
night" section once that update is installed.

## If something goes wrong

- **System tab** shows what is still missing and lets you restart.
- **See what the server is doing:** `journalctl -u dashboard -f`
- **Check every data source:** `curl http://localhost:8080/api/health`
- **Black screen after boot on the Pi:** run
  `OZONE_PLATFORM=x11 ~/WatcherV1/dashboard/deploy/kiosk.sh` in a terminal.
  If that works, edit `~/.config/labwc/autostart` and add `OZONE_PLATFORM=x11`
  in front of the kiosk line.
- **Calendar shows "Busy" instead of event names:** re-publish the calendar
  with **Can view all details**.
- **Calendar changes take a while to appear:** Microsoft refreshes published
  calendar links on its own schedule, sometimes a few hours behind.
- **Forgot the PIN:** on the Pi, edit `~/WatcherV1/dashboard/.env`, clear the
  `DASHBOARD_PIN=` line, and restart the service.
- **Test the page without internet or keys:** set `DASHBOARD_MOCK=1` in
  `.env`; every panel then shows sample data.

## Updating later

System tab → **Update to latest version**. It downloads the newest code,
installs any new packages and restarts. (By hand: `cd ~/WatcherV1 && git pull`,
then `cd dashboard && bash deploy/install.sh`.)

## For developers

Plain Python 3.11 + FastAPI on the back end, vanilla HTML/CSS/JS on the front
end, no build step. Leaflet is vendored under `static/vendor/`. `config.yaml`
is git-ignored; `config.example.yaml` is the template.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python tools/make_sample_photos.py        # three sample photos
DASHBOARD_MOCK=1 .venv/bin/uvicorn app.main:app --port 8080   # sample data, no network needed
bash tools/smoke.sh                                 # checks every /api/* endpoint
.venv/bin/python tools/check_calendar.py            # recurring-event parsing checks
.venv/bin/python tools/check_parsers.py             # alerts, moon, hourly, sports, multi-calendar checks
node tools/check_manage.mjs http://127.0.0.1:8080 photo.jpg   # settings page end-to-end (needs Playwright for Node)
node tools/screenshot.mjs http://127.0.0.1:8080 out.png
```

Data sources and their terms: [Open-Meteo](https://open-meteo.com/) (free for
non-commercial use, weather and air quality), the [National Weather Service API](https://www.weather.gov/documentation/services-web-api)
(free, US), [RainViewer](https://www.rainviewer.com/api.html) (free for personal use,
attribution shown on the map), [Finnhub](https://finnhub.io/) (free tier), ESPN's public
site API (unofficial; the sports tile fails softly if it changes), Esri World Dark Gray
basemap tiles, [zippopotam.us](https://www.zippopotam.us/) for ZIP lookups, and each
news site's public RSS feed.
