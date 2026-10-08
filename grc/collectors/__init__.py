"""Evidence collectors. Importing this package registers all collectors."""
from . import cloud, drata, github  # noqa: F401
from .base import REGISTRY, CheckResult, run_check  # noqa: F401
