"""Index newly available factsheets outside the question-answer request path."""

from django.core.management.base import BaseCommand, CommandError

from fundlens_rag.rag.factsheets import ensure_factsheets_indexed


class Command(BaseCommand):
    help = (
        "Index factsheets that are not yet in Qdrant. Docling parses a PDF "
        "only when no cached Markdown/chunk file exists."
    )

    def handle(self, *args, **options):
        try:
            indexed_documents = ensure_factsheets_indexed()
        except Exception as exc:
            raise CommandError(f"Factsheet indexing failed: {exc}") from exc

        if indexed_documents:
            document_list = ", ".join(indexed_documents)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Indexed {len(indexed_documents)} new factsheet(s): "
                    f"{document_list}"
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("No new factsheets to index."))
