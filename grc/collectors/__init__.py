"""Evidence collectors. Importing this package registers all collectors."""
from . import cloud, docstores, drata, github, jira, registry  # noqa: F401
from .base import REGISTRY, CheckResult, run_check  # noqa: F401
