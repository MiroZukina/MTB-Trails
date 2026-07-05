# Deploying MTBTrails to Railway

## 0. Before you do anything else

Two real secrets were found committed in this repo's git history (see the
chat for full detail):

1. `social/.env` — a real Gmail address + App Password. **Revoke this App
   Password now** (Google Account → Security → 2-Step Verification → App
   Passwords) and generate a new one if you still need outgoing email.
2. `social/settings.py` — a commented-out Render.com Postgres connection
   string with a real password. If that Render database still exists,
   rotate/delete it too.

Both have been removed from the working tree and untracked from git, but
**they still exist in git history** (this repo has a single "first commit").
Removing them from history entirely (e.g. `git filter-repo`) is a separate,
more invasive step — ask if you want help with that. Either way, treat both
credentials as burned.

## 1. Environment variables to set in Railway

Go to your Railway service → **Variables** and add:

| Variable | Value | Notes |
|---|---|---|
| `SECRET_KEY` | *(generate one)* | Run `python -c "import secrets; print(secrets.token_urlsafe(50))"` locally and paste the output. Never reuse the local dev default. |
| `DEBUG` | `False` | Must be exactly `False` (the code checks for the literal string `'True'`). |
| `ALLOWED_HOSTS` | `your-app.up.railway.app` | Comma-separated if you have more than one domain (e.g. add a custom domain later: `your-app.up.railway.app,mtbtrails.com`). You don't strictly need this — the app also auto-allows `RAILWAY_PUBLIC_DOMAIN` and `*.railway.app`/`*.up.railway.app` — but setting it explicitly is clearer. |
| `CSRF_TRUSTED_ORIGINS` | `https://your-app.up.railway.app` | Comma-separated, **must include the scheme** (`https://`). Also auto-populated from `RAILWAY_PUBLIC_DOMAIN` as a fallback. |
| `DATABASE_URL` | *(don't set manually)* | Railway injects this automatically when you attach a PostgreSQL plugin to this service — see step 2. |
| `CLOUDINARY_URL` | `cloudinary://<api_key>:<api_secret>@<cloud_name>` | From your Cloudinary dashboard's "API Environment variable" field. |
| `WEATHER_API_KEY` | *(your OpenWeatherMap key)* | Same key you use locally. |

Optional, only if you want outgoing email to work in production:

| Variable | Value |
|---|---|
| `EMAIL_USER` | your Gmail address |
| `EMAIL_PASSWORD` | a **new** Gmail App Password (not the leaked one) |

## 2. Attach PostgreSQL

In Railway: **New → Database → Add PostgreSQL** in the same project. Railway
automatically injects `DATABASE_URL` into every other service in that
project — you don't need to copy/paste it. The app uses it with
`conn_max_age=600` and `sslmode=require` automatically (see
`social/settings.py`).

## 3. Start command

Railway should auto-detect this as a Python/Django app via the `Procfile` at
the repo root:

```
web: python manage.py migrate --noinput && python manage.py collectstatic --noinput --upload-unhashed-files && gunicorn social.wsgi --log-file -
```

If Railway doesn't pick up the Procfile (or you'd rather set it explicitly),
set this as the service's **Custom Start Command** in Settings → Deploy:

```
python manage.py migrate --noinput && python manage.py collectstatic --noinput --upload-unhashed-files && gunicorn social.wsgi --bind 0.0.0.0:$PORT --log-file -
```

**Important gotcha**: always include `--upload-unhashed-files` when running
`collectstatic` in this project. `django-cloudinary-storage` (needed for
media uploads) replaces Django's `collectstatic` command with one that
silently copies *zero* files unless that flag is passed or you're hosting
static files on Cloudinary itself (we're not — static stays on WhiteNoise).
There's a comment explaining this right above `STATICFILES_STORAGE` in
`social/settings.py` if it ever needs revisiting.

## 4. First deploy checklist

- [ ] All env vars from the table above are set
- [ ] PostgreSQL plugin attached to the same project
- [ ] Push to the branch Railway is watching (or trigger a manual deploy)
- [ ] Watch the build/deploy logs for the `migrate` and `collectstatic` output
- [ ] Visit the deployed URL — confirm the feed loads, an image/avatar
      renders (Cloudinary), and a 404 shows the themed error page
- [ ] Check response headers include `Strict-Transport-Security` and
      `X-Frame-Options: DENY` (confirms the security settings are active)

## 5. Known, deliberately-skipped `check --deploy` warnings

Running `python manage.py check --deploy` locally with `DEBUG=False` shows
two warnings — both expected, not bugs:

- **`security.W009` (weak SECRET_KEY)** — only fires locally, because the
  local `.env` intentionally uses a clearly-fake default. Once you set a real
  `SECRET_KEY` in Railway, this goes away.
- **`security.W021` (HSTS preload not enabled)** — deliberate. We start with
  a modest `SECURE_HSTS_SECONDS=3600` (1 hour) so a misconfiguration doesn't
  lock out HTTP for a long time while you're still confirming HTTPS works
  end-to-end. Once you've verified the deployed site is solid over HTTPS for
  a while, raise `SECURE_HSTS_SECONDS` (e.g. to `31536000` — 1 year) and only
  then consider `SECURE_HSTS_PRELOAD = True` in `social/settings.py` (preload
  submission is hard to reverse, so don't rush it).

## 6. Local dev — nothing changes

Locally, as long as `.env` doesn't set `DATABASE_URL` or `CLOUDINARY_URL`,
everything keeps working exactly as before: SQLite, local `/media/` file
storage, `DEBUG=True`. See `.env` at the repo root for the current local
variables.
