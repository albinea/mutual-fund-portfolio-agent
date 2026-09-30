from typing import Callable, Optional

from app.schemas import LLMResponse


class LLMFallback:
    """
    Primary LLM -> secondary LLM -> cached response.
    """

    def __init__(
        self,
        primary: Callable,
        secondary: Optional[Callable] = None,
    ):
        self.primary = primary
        self.secondary = secondary
        self.cached_response: Optional[LLMResponse] = None

    def invoke(self, prompt: str) -> LLMResponse:
        """
        Try primary model first.
        If it fails, try secondary model.
        If both fail, return cached response if available.
        """

        # Primary model
        try:
            response = self.primary(prompt)

            if response is not None:
                self.cached_response = response

            return response

        except Exception as primary_error:
            print(
                f"Primary LLM failed: {primary_error}"
            )

        # Secondary model
        if self.secondary is not None:
            try:
                response = self.secondary(prompt)

                if response is not None:
                    self.cached_response = response

                return response

            except Exception as secondary_error:
                print(
                    f"Secondary LLM failed: {secondary_error}"
                )

        # Cached response
        if self.cached_response is not None:
            return self.cached_response

        raise RuntimeError(
            "All LLM providers failed and no cached response is available."
        )