"""Exceptions whose ``code`` travels to the frontend as a protocol error code."""


class FramelabError(Exception):
    """Base class: ``code`` becomes the envelope's ``error.code`` (i18n key ``errors.<code>``)."""

    code = "internal"
