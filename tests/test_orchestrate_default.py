import importlib.util
import sys
from pathlib import Path

ASO_DIR = Path(__file__).resolve().parents[1]
ORCH = ASO_DIR / "orchestrate.skill"
sys.path.insert(0, str(ASO_DIR / "_lib"))
spec = importlib.util.spec_from_file_location("orchestrate", ORCH, loader=importlib.machinery.SourceFileLoader("orchestrate", str(ORCH)))
orch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orch)


def test_default_strategy_is_aso():
    import inspect
    sig = inspect.signature(orch.run)
    assert sig.parameters["strategy"].default == "aso"
