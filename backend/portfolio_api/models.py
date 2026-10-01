from django.db import models


class WatchlistItem(models.Model):
    """A development-only watchlist keyed by the API user identity."""

    user_id = models.CharField(max_length=255, db_index=True)
    symbol = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "symbol"],
                name="unique_user_watchlist_symbol",
            )
        ]
        ordering = ["-created_at"]
