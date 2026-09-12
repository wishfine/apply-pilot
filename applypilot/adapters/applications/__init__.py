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
    FileUploadFiller,
    GenericApplicationAdapter,
    NativeSelectFiller,
    RadioCheckboxFiller,
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
    "FileUploadFiller",
    "GenericApplicationAdapter",
    "MokaApplicationAdapter",
    "MokaSearchSelectFiller",
    "NativeSelectFiller",
    "RadioCheckboxFiller",
    "StandardInputFiller",
]
