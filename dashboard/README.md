# Watcher Dashboard

A free, self-hosted replacement for a DAKboard-style wall display, built for a
Raspberry Pi 5 (or Pi 4) plugged into a TV or monitor. It shows:

- **Clock and date**, with **countdowns** to dates you care about
- **Current weather, an hourly strip and a 5-day outlook**, plus UV, air quality, sunrise/sunset and moon phase (Open-Meteo, no account needed)
- **Severe weather banner** for active National Weather Service watches and warnings (US)
- **Live animated radar** for the last two hours (RainViewer, no account needed)
- **Stocks** (Finnhub, free API key) and a **favorite team tile** with record, next game and last result (ESPN)
- **Your calendars**, as many as you like, each in its own color (published ICS links, no Microsoft or Google developer setup)
- **Photo slideshow** from photos you add from your phone
- **Shared to-do list and a note** everyone in the house can see and edit from a phone
- **Now playing** card for Spotify, and a **screen schedule** that turns the TV off at night and on in the morning
- **Scrolling news ticker** from RSS feeds (NPR, BBC, CBS by default)

![Dashboard](docs/dashboard.png)

Everything runs on one small Linux computer plugged into the TV: a Raspberry Pi,
an Intel mini PC, or a desktop you already own (this project was set up on a
2013 Mac Pro running Omarchy). A small Python web server fetches the data on a
timer and serves one web page; Chromium shows that page full-screen at login.
After the one-time install, **everything is managed from a settings page on your
phone** (or on the TV itself with a mouse or touchscreen), and the computer stays
a normal Linux desktop you can switch to at any time. No subscriptions, no cloud
account, and your calendar links and keys never leave your home network.

## Which computer?

| | Raspberry Pi 4 / 5 | Intel N150 mini PC | A Linux desktop you own (e.g. Mac Pro + Omarchy) |
|---|---|---|---|
| Cost | $100–230 with supply, cooler, card | $130–160 complete | $0 |
| Speed as a desktop | OK (Pi 5) | Good | Best |
| Power all day | 5–8 W | 8–15 W | 50 W or more |
| Turns the TV itself off/on | Yes (HDMI-CEC) | No, picture only | No, picture only |
| Setup section | Part 1 | Part 1b | Part 1c |

The dashboard looks and works the same on all of them.

---

## Part 1: Set up a Raspberry Pi (one time)

You need: a Raspberry Pi 5 (4 GB or more is comfortable; a Pi 4 with 2 GB also
works), the official 27 W USB-C power supply, the Active Cooler (the Pi 5 runs
warm with a browser full-screen all day), a microSD card (16 GB+), a micro-HDMI
to HDMI cable, a screen, and Wi-Fi or Ethernet.

1. On your computer, install **Raspberry Pi Imager** from
   <https://www.raspberrypi.com/software/>.
2. In Imager choose your Pi model, then the OS **Raspberry Pi OS (64-bit)**
   (the normal one *with desktop*), then your SD card.
3. When Imager asks to customize settings, click **Edit settings** and set:
   - Hostname: `dashboard`
   - Username `pi` and a password you will remember
   - Your Wi-Fi name and password
   - Under **Services**, turn on **SSH** with password login
4. Write the card, put it in the Pi, connect the screen to the HDMI port
   **next to the power connector** (HDMI 0), and power it on. The first boot
   takes a couple of minutes. Either port works; HDMI 0 is simply the one the
   Pi uses first at boot.

## Part 1b: Set up an Intel mini PC (one time)

Install **Linux Mint Cinnamon** (download from linuxmint.com, write it to a USB
stick with balenaEtcher, boot the mini PC from the stick, choose "Install").
Afterwards open **Power Management** in Mint's settings and set the screen to
never blank. Then go to Part 2.

## Part 1c: Use a Linux desktop you already have (Omarchy / Mac Pro)

Plug the TV into the computer's HDMI port, open a terminal (on Omarchy:
`Super + Return`), and go to Part 2. The installer recognises Omarchy, uses its
package manager, adds the dashboard to Omarchy's login autostart
(`~/.config/hypr/autostart.lua`) and to the app launcher, and stops Omarchy's
idle screen lock while the dashboard is open so the TV never shows a lock
screen. Omarchy's own stay-awake toggle (`Super + Ctrl + I`) works too.

## Part 2: Install the dashboard (the only terminal step)

In a terminal on the dashboard computer (on a Pi you can also use
`ssh pi@dashboard.local` from another machine), paste these lines one at a time:

```bash
git clone https://github.com/schwadb/WatcherV1.git ~/WatcherV1
cd ~/WatcherV1/dashboard
bash deploy/install.sh
```

(On a Pi, run `sudo apt update && sudo apt full-upgrade -y` first.)

The install script takes a few minutes. It detects which kind of computer it is
on, installs Chromium and the Python packages, creates your settings and secrets
files, sets the time zone, turns off screen blanking where it can, sets the
dashboard to open at login, and adds a launcher to the app menu. When it
finishes it prints the address of the settings page.

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

In the **System** tab press **Reboot** (or type `sudo reboot`). The computer
starts up, the dashboard server starts, and Chromium opens the page full-screen
at login. The dashboard is also at <http://dashboard.local:8080> (or the
computer's name or IP address) from any device on your Wi-Fi.

---

## The settings page

<http://dashboard.local:8080/manage> has six tabs:

| Tab | What you can do |
|---|---|
| **Photos** | Add photos from your phone, see what's on the dashboard, delete |
| **To-do** | A shared household list. Add, check off, delete. Checked items disappear the next day. |
| **Notes** | A short message shown on the dashboard; saves as you type |
| **Settings** | Every setting: location by ZIP code, units, 24-hour clock, which panels to show, weather options, radar zoom, calendars with colors, stock symbols, your sports team (search by name), countdowns, news feeds, photo speed, screen schedule, and your keys and links |
| **Music** | Connect Spotify so the dashboard shows what's playing |
| **System** | Dashboard address, version, free disk, Pi temperature, which keys are set, and buttons to restart, update to the latest version, turn the screen off or on, and reboot |

Changes apply right away; the dashboard page reloads itself when settings change.

**On the TV itself:** plug a mouse, keyboard or touchscreen into the Pi, move the
mouse or touch the screen, and tap the gear in the top-right corner (or press
`S`). The same settings page opens on the TV with larger buttons, a
**Back to dashboard** link, and an on-screen keyboard for touchscreens.

**Hiding panels:** turn off anything you don't use under Settings → Panels. The
neighbors expand to fill the space. Turn off the radar and the weather panel gets
taller; turn off stocks and the photo gets the whole middle column.

## Using the computer as a computer too

The dashboard is just a full-screen browser window on top of the normal Linux
desktop, so the same machine can be your computer. Plug in a mouse and keyboard
(USB or Bluetooth), or use a touchscreen. On Omarchy, `Super + F` or `F11` also
drops the dashboard into a normal tiled window.

- **Drop to the desktop:** move the mouse or touch the screen and tap
  **Desktop** in the top-right corner (or press `D`). The dashboard window
  closes and the normal desktop with its menu and taskbar is there. From a
  phone, System tab → **Switch Pi to desktop** does the same.
- **Keep both:** press `F11` instead. The dashboard shrinks to a normal window
  you can move aside; `F11` again makes it full-screen.
- **Bring the dashboard back:** double-click **Watcher Dashboard** on the
  desktop, pick it from the app menu (Accessories), or on a phone use System tab
  → **Show dashboard on the Pi**.
- **Choose what happens at boot:** Settings → Screen & desktop → "Open the
  dashboard when the Pi starts". Turn it off and the Pi boots to the desktop;
  phones can still open the dashboard page at any time because the server keeps
  running in the background.
- The night-time screen schedule never turns the screen off while the dashboard
  window is closed, so it won't interrupt you at the desktop.
- "Locked kiosk" (same settings card) is for a display nobody should be able to
  leave: no `F11`, no Desktop button, only the phone can switch it.
- "Stop the desktop's idle screen lock" (Omarchy / Hyprland) keeps the TV from
  showing a lock screen after a few quiet minutes. The lock comes back at your
  next login; turn the option off if you'd rather keep locking and use
  `Super + Ctrl + I` (stay awake) yourself.

A Pi 5 makes a good everyday desktop alongside the dashboard; 4 GB or more is
comfortable, 8 GB if you keep many browser tabs open. A Pi 4 with 2 GB handles
the dashboard plus light desktop use. Two screens (dashboard on the TV, desktop
on a monitor) is possible with the second HDMI port but not set up by this
project yet.

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

### Storm mode (a warning takes over the screen)

When the alert is a **Warning** (Tornado, Severe Thunderstorm, Flash Flood, …)
or a **Tornado Watch**, the dashboard does more than a banner: the whole screen
turns into the alert. The left half shows the alert name, when it ends, the
Weather Service text and what to do; the right half is the radar, zoomed in one
step. A three-note chime plays when it appears. It stays for ten minutes (or
until someone presses **Esc** or the **Dismiss** button), then the normal
dashboard comes back. The red banner keeps showing until the alert expires.

Settings → Weather: turn storm mode off, change how many minutes it stays, or
turn the chime off. Which alerts trigger it is the `takeover_events` list in
`config.yaml` (`*Warning` matches every kind of warning).

### ChronAlert radar inside the dashboard

[ChronAlert](https://chronalert.com) is a free weather-tracking program for
radio and storm enthusiasts (the Pro version adds more layers). It runs on your
computer and shows its map in a web page on port 8420, so the dashboard can show
that page too. Two ways to use it:

- **Rotate with the photos:** every few minutes the photo panel swaps to the
  ChronAlert map for a while, then goes back to photos. If ChronAlert is not
  running, the photos just keep going.
- **Button only:** a **Map** button appears in the corner (move the mouse or
  touch the screen to see it). Press it, or the **C** key, for the map full
  screen; **Esc** or **Close map** goes back. Storm mode never shows the
  ChronAlert map on its own, so the radar you see in a warning is always the
  dashboard's.

To set it up on the Mac Pro / any Linux desktop:

1. Download the Linux AppImage from <https://chronalert.com/download> into
   `~/Applications` (make the folder if it is missing), then make it runnable:
   `chmod +x ~/Applications/ChronAlert*.AppImage` and double-click it (or run
   it from a terminal). Sign in and pick your location inside ChronAlert.
2. On the phone, Settings → **ChronAlert**: choose *Rotate with the photos* or
   *Button only* and save. Leave the address blank when ChronAlert runs on the
   dashboard computer; otherwise enter `http://<that-computer>:8420/`.
3. To open ChronAlert on your phone too, open its port in the firewall once:
   `sudo ufw allow 8420/tcp`.
4. Optional: in ChronAlert's own settings turn on "start with the computer" so
   it is always running when the dashboard needs it.

If the map stays blank inside the dashboard (some apps refuse to be shown
inside another page), set *Open full screen as* to **A separate window**. The
Map button then opens ChronAlert in its own Chromium window on the TV;
Alt+Tab or closing it brings the dashboard back.

### Countdowns

Settings → Countdowns: a title, a date and an optional emoji. The clock panel
shows up to three upcoming countdowns. Past dates disappear by themselves.

### Favorite teams

Settings → Sports teams: search by name (college and pro football, basketball,
baseball, hockey, MLS) and pick a team; search again to add more. The tile
shows the record and standing, the next game with TV channel, the last result,
and the live score while a game is on. With several teams the tile rotates
through them every 12 seconds (small dots show which one is up), and a team
that is playing right now stays on screen. The data comes from ESPN's public
site.

### Turning the TV off at night

Settings → Screen schedule: a time to turn the screen off and a time to turn it
back on (for example 23:00 and 06:00), plus an optional time from which the page
dims. The Pi switches its HDMI output off at bedtime and on in the morning. If
your TV has HDMI-CEC switched on (Samsung "Anynet+", LG "SimpLink", Sony "Bravia
Sync", usually on by default), the TV itself goes to standby and wakes up too.
The page also goes black during off hours, so even a TV without CEC shows
nothing bright.

Try it from the System tab with **Screen off now** and **Screen on now**. If
the TV does not come back on by itself, turn CEC on in the TV's menu or just
switch the TV on with its remote; the dashboard is already running.
"HDMI control: only dim the page" turns the output switching off and keeps the
black overlay.

On a mini PC or the Mac Pro there is no CEC: the picture is switched off and on
(on Omarchy through Hyprland's own display power control) but the TV stays
powered. Most TVs go to sleep by themselves a few minutes after the signal
stops and wake when it returns; if yours doesn't, use the TV's sleep timer, or
add a Pulse-Eight USB-CEC adapter later and the scripts will use it.

### Now playing (Spotify)

The Music tab shows what's playing on your Spotify account as a small card over
the photo, with album art and a progress bar. Spotify's rules make the one-time
connection a bit fiddly, so the tab walks you through it:

1. On a computer, go to <https://developer.spotify.com/dashboard>, log in
   (the account must be **Spotify Premium**, a Spotify rule since 2026) and
   create an app with any name.
2. Under **Redirect URIs** paste exactly `http://127.0.0.1:8080/api/spotify/callback`
   (the Music tab shows the exact value for your port).
3. Copy the app's **Client ID** into Settings → Keys & links.
4. On the Music tab press **Connect Spotify** and approve. Your browser then
   lands on a page that cannot load (Spotify only allows that local address).
   Copy that page's address from the address bar and paste it into the box on
   the Music tab, then press **Finish connecting**.

Done on the Pi's own browser (Alt+F4 out of the kiosk, open the address in
Chromium) the last step finishes by itself. The card hides when nothing is
playing, and **Disconnect** on the Music tab removes the connection.

## If something goes wrong

- **System tab** shows what is still missing and lets you restart.
- **See what the server is doing:** `journalctl -u dashboard -f`
- **Check every data source:** `curl http://localhost:8080/api/health`
- **Dashboard closed and you want it back:** desktop icon, app menu, or the
  phone's System tab.
- **TV does not switch off or on with the schedule:** the Pi 5 has a CEC
  adapter per HDMI port and the scripts try both; make sure CEC is on in the
  TV's menu. The HDMI output itself is switched regardless.
- **Black screen after boot on the Pi:** run
  `OZONE_PLATFORM=x11 ~/WatcherV1/dashboard/deploy/kiosk.sh` in a terminal.
  If that works, edit `~/.config/labwc/autostart` and add `OZONE_PLATFORM=x11`
  in front of the kiosk line.
- **Calendar shows "Busy" instead of event names:** re-publish the calendar
  with **Can view all details**.
- **Calendar changes take a while to appear:** Microsoft refreshes published
  calendar links on its own schedule, sometimes a few hours behind.
- **Omarchy shows the lock screen over the dashboard:** check "Stop the
  desktop's idle screen lock" under Settings → Screen & desktop, or press
  `Super + Ctrl + I`.
- **Phone says the page took too long to respond, but it works on the
  computer itself:** the computer's firewall is blocking it. Omarchy turns on
  `ufw`; run `sudo ufw allow 8080/tcp` (the installer now does this for you)
  and try again.
- **Forgot the PIN:** on the computer, edit `~/WatcherV1/dashboard/.env`, clear the
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
