web: python manage.py migrate --noinput && python manage.py collectstatic --noinput --upload-unhashed-files && gunicorn social.wsgi --log-file -
release: python manage.py migrate --noinput && python manage.py collectstatic --noinput --upload-unhashed-files
