"""Thin entry point for the same local demo service used by smoke tests."""

from sentinel_ops.demo_service import create_app

__all__ = ["create_app"]
