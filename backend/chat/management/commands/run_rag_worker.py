"""Run the separate worker that executes queued FundLens RAG questions."""

from django.core.management.base import BaseCommand

from chat.rag_jobs import run_rag_worker


class Command(BaseCommand):
    help = "Poll the database and process queued FundLens RAG answer jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process at most one queued job and exit.",
        )
        parser.add_argument(
            "--poll-interval",
            type=float,
            default=1.0,
            help="Seconds to wait between empty-queue checks (default: 1).",
        )

    def handle(self, *args, **options):
        if options["once"]:
            processed = run_rag_worker(once=True)
            if processed:
                self.stdout.write(self.style.SUCCESS("Processed one RAG job."))
            else:
                self.stdout.write("No queued RAG jobs.")
            return

        poll_interval = options["poll_interval"]
        if poll_interval <= 0:
            self.stderr.write("--poll-interval must be greater than zero.")
            return

        self.stdout.write("FundLens RAG worker running. Press Ctrl+C to stop.")
        run_rag_worker(poll_interval=poll_interval)
