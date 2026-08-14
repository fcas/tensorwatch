# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Defense-in-depth RestrictedUnpickler for TensorWatch.

Uses an **allowlist** approach: only modules that TensorWatch legitimately
needs for serialization are permitted.  Everything else is blocked by default.

Allowed module families:
  - Python builtins and standard-library data types (collections, datetime,
    decimal, fractions, numbers, uuid)
  - Pickle internals (_codecs, copyreg, _collections — used by the pickle
    protocol itself)
  - numpy, torch, pandas — data-science libraries whose objects appear in
    StreamItem values
  - tensorwatch — the library's own data classes

WARNING: This is NOT a complete sandbox.  Pickle allowlists reduce the attack
surface dramatically compared to blocklists, but do not eliminate all risk.
Do not load pickle data from untrusted sources.
"""

import io
import pickle
import logging

# ---------------------------------------------------------------------------
# Allowlist — a module is permitted if its top-level package appears here.
# Any module NOT in this set is rejected outright.
# ---------------------------------------------------------------------------
_ALLOWED_PREFIXES = frozenset({
    # Python built-in / standard-library data types
    'builtins',
    'collections', '_collections',   # _collections holds C-accelerated types
    'datetime',
    'decimal',
    'fractions',
    'numbers',
    'uuid',
    # Pickle protocol internals (required for __reduce__ reconstruction)
    'copyreg',
    '_codecs',
    # Data-science libraries
    'numpy',
    'torch',
    'pandas',
    # TensorWatch's own types
    'tensorwatch',
})

# Even within allowed modules, these builtins are too dangerous to permit.
_BLOCKED_BUILTINS = frozenset({
    'eval', 'exec', 'compile', '__import__',
    'open', 'input', 'breakpoint',
    'exit', 'quit',
    'globals', 'locals', 'vars',
    'getattr', 'setattr', 'delattr',
})

_log = logging.getLogger(__name__)


class RestrictedUnpickler(pickle.Unpickler):
    """Unpickler that only allows classes from explicitly approved modules.

    Uses an allowlist (not a blocklist), so unknown or newly-introduced
    dangerous modules are blocked by default.
    """

    def find_class(self, module, name):
        top_module = module.split('.')[0]

        # Reject any module not in the allowlist
        if top_module not in _ALLOWED_PREFIXES:
            _log.warning("Pickle restricted: blocked %s.%s (module '%s' not in allowlist)",
                         module, name, top_module)
            raise pickle.UnpicklingError(
                "Blocked: module '{}' is not in the allowlist "
                "(attempted to load {}.{})".format(top_module, module, name))

        # Block dangerous builtins even though 'builtins' is allowed
        if top_module == 'builtins' and name in _BLOCKED_BUILTINS:
            _log.warning("Pickle restricted: blocked builtins.%s", name)
            raise pickle.UnpicklingError(
                "Blocked: builtins.{} is not allowed".format(name))

        return super().find_class(module, name)


def restricted_loads(data: bytes):
    """Deserialize bytes using RestrictedUnpickler."""
    return RestrictedUnpickler(io.BytesIO(data)).load()


def restricted_load(f):
    """Deserialize from a file object using RestrictedUnpickler."""
    return RestrictedUnpickler(f).load()
