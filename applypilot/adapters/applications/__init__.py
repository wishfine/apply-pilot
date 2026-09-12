"""Application adapter module implementing strategy-composed adapters and component fillers."""

from applypilot.adapters.applications.base import (
    ApplicationAdapter,
    BaseApplicationAdapter,
    ComponentFiller,
    FillResult,
)
from applypilot.adapters.applications.beisen import (
    BeisenApplicationAdapter,
    BeisenModalSchoolPicker,
)
from applypilot.adapters.applications.generic import (
    GenericApplicationAdapter,
    StandardInputFiller,
)
from applypilot.adapters.applications.moka import (
    MokaApplicationAdapter,
    MokaSearchSelectFiller,
)

__all__ = [
    "ApplicationAdapter",
    "BaseApplicationAdapter",
    "BeisenApplicationAdapter",
    "BeisenModalSchoolPicker",
    "ComponentFiller",
    "FillResult",
    "GenericApplicationAdapter",
    "MokaApplicationAdapter",
    "MokaSearchSelectFiller",
    "StandardInputFiller",
]
