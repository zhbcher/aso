from __future__ import annotations

from dataclasses import dataclass, field

print('At module load: list is', type(list))
print('field is', field)

@dataclass
class MechanismSpec:
    name: str = ""
    applicable_to: list[str] = field(default_factory=list)

print('MechanismSpec defined OK')
