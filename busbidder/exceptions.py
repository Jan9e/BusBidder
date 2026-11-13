"""Domain exceptions. Every failure category is explicit so the
report can justify the invalid-record policy (reject / correct / quarantine)."""


class BusBidderError(Exception):
    """Base class for all application errors."""


class DataError(BusBidderError):
    """Anything that goes wrong while loading or validating source data."""


class MissingDataError(DataError):
    """A required field is absent or empty."""


class InconsistentDataError(DataError):
    """Fields parse, but contradict each other (e.g. arrival before departure)."""


class InvalidValueError(DataError):
    """Field parses but violates a range or format rule (e.g. rating > 5)."""


class UnknownReferenceError(DataError):
    """A referenced identifier (destination, company) does not exist."""


class WeightValidationError(BusBidderError):
    """Weights are out of [0,1] or do not sum to 1.0."""


class BookingError(BusBidderError):
    """Seat gone, invalid selection, or persistence failure."""