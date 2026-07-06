<p align="center">
  <img src="cycling/static/img/badge.png" alt="MTBTrails badge" width="140">
</p>

<h1 align="center">MTBTrails</h1>

<p align="center">
  <a href="https://mtb-trails-production.up.railway.app"><strong>mtb-trails-production.up.railway.app</strong></a>
</p>

MTBTrails is a community platform for mountain bikers to map, share, and discover trails.
Riders can pin or draw routes (or upload a GPX file), see elevation profiles and live trail
weather, tag difficulty grades, browse an explore map of every posted trail, buy and sell
gear in the built-in marketplace, and follow other riders through profiles that track their
stats.

## Features

- **Trail posts** — pin a point, draw a route, or upload a GPX track to log a ride
- **Elevation profiles** — auto-generated from route/GPX geometry
- **Trail weather** — live conditions at the trail's location, plus a home feed weather widget
- **Difficulty grades** — color-coded green/blue/red/black ratings on every trail
- **Explore map** — Leaflet + CyclOSM map of all trails with a location
- **Marketplace** — list, browse, and message sellers about gear
- **Inbox** — direct conversations between riders
- **Rider profiles** — stats, posted trails, followers/following
- **Comments & likes** on trail posts, with media attachments

## Tech stack

- [Django 6](https://www.djangoproject.com/) + PostgreSQL
- [Leaflet](https://leafletjs.com/) with [CyclOSM](https://www.cyclosm.org/) tiles for mapping
- [Cloudinary](https://cloudinary.com/) for media storage
- [WhiteNoise](http://whitenoise.evans.io/) for static file serving
- [gunicorn](https://gunicorn.org/) on [Railway](https://railway.app/)
- 67-test suite (`python manage.py test`)

## Local setup

```bash
git clone <repo-url>
cd Cycling
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

No API keys are required to run the app locally — maps use the free CyclOSM tile layer.
A few optional environment variables enable extra features:

| Variable | Purpose |
| --- | --- |
| `WEATHER_API_KEY` | Enables trail/feed weather (OpenWeatherMap) |
| `CLOUDINARY_URL` | Stores uploaded media on Cloudinary instead of locally |
| `DATABASE_URL` | Points at Postgres instead of the local default |

Run the test suite with:

```bash
python manage.py test
```
