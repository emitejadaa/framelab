"""Exceptions whose ``code`` travels to the frontend as a protocol error code."""


class FramelabError(Exception):
    """Base class: ``code`` becomes the envelope's ``error.code`` (i18n key ``errors.<code>``)."""

    code = "internal"


class BadRequest(FramelabError, ValueError):
    """A protocol request has missing or malformed parameters."""

    code = "bad_request"
