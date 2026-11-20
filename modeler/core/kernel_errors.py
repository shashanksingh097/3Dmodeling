"""Plain words for failures that come from the geometry kernel or from a bug (PLAN item 63).

Commands check their own inputs and say what is wrong in their own words. What is
left is the kernel refusing values that passed those checks (an arc through three
points in a line, a fillet bigger than its face), and the rare bug. Instead of a
bare ``StdFail_NotDone: GC_MakeArcOfCircle::Value() - no result`` the user is told
which command failed, what that kind of failure usually means and what to try;
the kernel's own words stay at the end for a bug report.
"""

from __future__ import annotations

import re

# OCCT exception class -> what it usually means for the values given to a command
KERNEL = {
    "StdFail_NotDone": "the geometry kernel could not make the shape from these values",
    "Standard_ConstructionError": "these values do not make a valid shape (points in a line or on top of "
                                  "each other, a zero or negative size, an axis of no length)",
    "Standard_DomainError": "a value is outside what the kernel can work with here",
    "Standard_OutOfRange": "a value is outside the range the kernel can work with here",
    "Standard_RangeError": "a value is outside the range the kernel can work with here",
    "Standard_NullObject": "the kernel was given an empty shape (an earlier step may have made nothing)",
    "Standard_NoSuchObject": "the kernel could not find a part of the shape it needed",
    "Standard_DimensionError": "the kernel was given lists of different lengths",
    "Standard_NumericError": "the numbers are too large or too small for the kernel",
    "Standard_DivideByZero": "a size works out as zero where the kernel divides by it",
    "Standard_Overflow": "the numbers are too large for the kernel",
    "Standard_Underflow": "the numbers are too small for the kernel",
    "Standard_TypeMismatch": "the kernel was given the wrong kind of shape here",
    "Standard_NotImplemented": "the kernel cannot do this for this kind of shape",
    "Standard_Failure": "the geometry kernel failed on these values",
    "BRepBuilderAPI_NotDone": "the kernel could not build the shape from these values",
    "TopoDS_UnCompatibleShapes": "the kernel was given the wrong kind of shape here",
    "Geom_UndefinedValue": "the curve or surface has no value at that place",
    "Geom_UndefinedDerivative": "the curve or surface is not smooth at that place",
    "gp_VectorWithNullMagnitude": "a direction of zero length was given (two points on top of each other?)",
}

HINT = ("Try values further from the limits (smaller fillets, sizes that are not zero, points that "
        "are not in a line), or do it in two smaller steps")

PYTHON = {
    ZeroDivisionError: "a size or count works out as zero where it is divided by",
    OverflowError: "a number is too large",
    MemoryError: "there is not enough memory for this; try a coarser setting or a smaller model",
}


def is_kernel(exc: BaseException) -> bool:
    mod = type(exc).__module__ or ""
    return mod.startswith("OCP") or type(exc).__name__ in KERNEL


def explain(command: str, exc: BaseException) -> str:
    """One message for the user: which command, what it means, what to try, and the raw words."""
    name = type(exc).__name__
    raw = re.sub(r"\s+", " ", str(exc)).strip()
    detail = f"{name}: {raw}" if raw else name
    head = f"{command}: " if command else ""
    if (type(exc).__module__ or "").startswith("modeler.") and raw:
        # the program's own geometry errors (GearError, SheetError ...) already say what is wrong
        return raw if command and raw.upper().startswith(command.upper()) else head + raw
    if is_kernel(exc):
        meaning = KERNEL.get(name, KERNEL["Standard_Failure"])
        return f"{head}{meaning}. {HINT}. (kernel: {detail})"
    for kind, meaning in PYTHON.items():
        if isinstance(exc, kind):
            return f"{head}{meaning}. (details: {detail})"
    if isinstance(exc, OSError):
        where = f" {exc.filename}" if getattr(exc, "filename", None) else ""
        why = exc.strerror or raw or name
        return f"{head}could not use the file{where}: {why}"
    if isinstance(exc, ValueError) and re.search(r"math domain|nan|inf", raw, re.I):
        return f"{head}a value works out as impossible (a square root of a negative number, or similar). " \
               f"Check the sizes. (details: {detail})"
    return (f"{head}this failed inside the program, which is a bug and not your mistake. Undo is safe; "
            f"please report it with Help > Report a problem. (details: {detail})")
