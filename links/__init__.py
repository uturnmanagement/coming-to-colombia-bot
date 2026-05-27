"""External-link abstractions: Telegram dispatcher, future API clients.

`links/` is the only place new code talks to the outside world. Everything
above it (agents/, intel/) must call through these dispatchers — keeping
DRY_RUN enforcement and rate limiting in one place.
"""
