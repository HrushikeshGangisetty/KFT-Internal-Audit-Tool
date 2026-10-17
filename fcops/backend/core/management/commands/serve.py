"""Run the app on a production-style server with a bounded thread pool.

`runserver` creates a new thread — and therefore a new database connection —
for every request. Against a database in another region that means paying a TLS
handshake on each one, which is most of the latency a user feels. It also rules
out persistent connections, because they would accumulate until the pooler
refuses new clients.

A fixed thread pool fixes both: at most `--threads` connections exist, so they
can be kept open and reused. On a link to a distant region this removes roughly
half a second from every request.

    python manage.py serve                 # 0.0.0.0:8000, 6 threads
    python manage.py serve --threads 12
"""
from django.core.management.base import BaseCommand
from django.db import connections


class Command(BaseCommand):
    help = "Serve the application with waitress and a bounded thread pool."

    def add_arguments(self, parser):
        parser.add_argument("--host", default="0.0.0.0")
        parser.add_argument("--port", type=int, default=8000)
        parser.add_argument("--threads", type=int, default=6,
                            help="Worker threads, and therefore the maximum "
                                 "number of database connections held.")
        parser.add_argument("--conn-max-age", type=int, default=60,
                            help="Seconds to keep a database connection open. "
                                 "0 disables connection reuse.")

    def handle(self, *args, **options):
        try:
            from waitress import serve
        except ImportError:
            raise SystemExit(
                "waitress is not installed. Run: pip install -r requirements.txt")

        from config.wsgi import application

        threads = options["threads"]
        max_age = options["conn_max_age"]

        # Safe here in a way it is not under runserver: the pool is bounded, so
        # connections cannot accumulate past `threads`.
        settings_dict = connections["default"].settings_dict
        settings_dict["CONN_MAX_AGE"] = max_age
        settings_dict["CONN_HEALTH_CHECKS"] = max_age > 0

        from django.conf import settings
        where = settings.DATABASE_DESCRIPTION
        self.stdout.write(self.style.MIGRATE_HEADING("FC Ops"))
        self.stdout.write(f"  serving   http://{options['host']}:{options['port']}")
        self.stdout.write(f"  threads   {threads} "
                          f"(at most {threads} database connections)")
        self.stdout.write(f"  database  {where['mode']} — {where['host']}")
        self.stdout.write(
            f"  reuse     connections kept for {max_age}s"
            if max_age else "  reuse     off — a new connection per request")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Ready. Ctrl-C to stop."))

        serve(application, host=options["host"], port=options["port"],
              threads=threads, ident="fcops")
