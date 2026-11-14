from . import handlers  # noqa: F401  (registers the commands)
from . import curve_handlers, pattern_handlers, project_handlers  # noqa: F401  (more commands)
from . import feature_handlers, measure_handlers  # noqa: F401  (datums, features, measuring)
from . import sketch_handlers  # noqa: F401  (sketches, EXTRUDE, REVOLVE)
from .processor import REGISTRY, CommandError, Entry, Processor, Result

__all__ = ["Processor", "Result", "Entry", "CommandError", "REGISTRY"]
from . import part_handlers  # noqa: F401  (parts, instances, the part library)
from . import thread_handlers  # noqa: F401  (THREAD, SPRING)
from . import shape_handlers  # noqa: F401  (TEXT, SURFACE, PUSHPULL, DELFACE)
from . import layer_handlers  # noqa: F401  (LAYER, COLOR, MATERIAL, ISOLATE)
from . import sketch_edit_handlers  # noqa: F401  (STRIM, SEXTEND, SFILLET, SOFFSET, SMIRROR, SPATTERN, SPROJECT)
from . import check_handlers  # noqa: F401  (ASSERT, DESCRIBE, SELFOR, LINT, DIFF)
from . import nurbs_handlers  # noqa: F401  (NURBS, MOVEPT, WEIGHT, KNOT, DEGREE, REBUILD, NSURF, NETWORK, FILL, SEW)
from . import surface_handlers  # noqa: F401  (BLEND, EXTEND, TRIM, PROJECT, MOVEFACE, REPLACEFACE)
from . import analysis_handlers  # noqa: F401  (ANALYZE)
from . import deform_handlers  # noqa: F401  (BEND, TWIST, TAPER, STRETCH, FLOW, SWEEPVOL)
from . import contact_handlers  # noqa: F401  (CONTACT, CLEARANCE)
