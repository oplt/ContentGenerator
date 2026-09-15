"""Product-dormant feature modules.

Do not import routers/models from this package into the live API or model registry
unless the capability is completed (see ``docs/dormant-modules.md``).
"""

from backend.core.dormant_modules import DORMANT_MODULES, DORMANT_PACKAGE_NAMES

__all__ = ["DORMANT_MODULES", "DORMANT_PACKAGE_NAMES"]
