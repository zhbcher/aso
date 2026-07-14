# generator/registry.py -- Plugin registry for evolve generators
# Manages loading and registration of .skill generator plugins

import os
import sys

# Add _lib to import path
_lib_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "_lib")
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)



class GeneratorRegistry:
    """Registry for evolution generator plugins."""

    def __init__(self):
        self._generators = {}
        self._load_builtin()

    def _load_builtin(self):
        """Load built-in generators."""
        try:
            from generator.bilevel import Generator as BilevelGenerator
            gen = BilevelGenerator()
            self._generators[gen.name] = gen
        except Exception as e:
            # P2-C fix: Output to stderr instead of stdout
            print(f"Warning: Failed to load bilevel generator: {e}", file=sys.stderr)
        try:
            from generator.skill_opt_refactor import SkillOptRefactor
            self._generators[SkillOptRefactor.name] = SkillOptRefactor()
        except Exception as e:
            print(f"Warning: Failed to load ASO (skill-opt) generator: {e}", file=sys.stderr)

    def get(self, name: str):
        """Get a generator by name."""
        return self._generators.get(name)

    def list_generators(self) -> list[str]:
        """List available generator names."""
        return list(self._generators.keys())

    def register(self, name: str, generator):
        """Register a custom generator."""
        self._generators[name] = generator


# Singleton instance
_registry = None


def get_registry() -> GeneratorRegistry:
    """Get the global generator registry singleton."""
    global _registry
    if _registry is None:
        _registry = GeneratorRegistry()
    return _registry


def get_generator(name: str):
    """Convenience function to get a generator by name from the registry.

    P2-C fix: orchestrate.skill calls 'from registry import get_generator'
    but this function was missing, causing silent ImportError.
    """
    return get_registry().get(name)
