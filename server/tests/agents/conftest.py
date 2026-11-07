import pytest

from app.agents.contracts import OrderInput
from app.agents.demo import FixtureBackend
from app.agents.fixtures import create_fixtures


@pytest.fixture(scope="session")
def fixture_dir(tmp_path_factory):
    root = tmp_path_factory.mktemp("synthetic")
    create_fixtures(root)
    return root


@pytest.fixture
def backend(tmp_path, fixture_dir):
    adapter = FixtureBackend(tmp_path / "runtime", fixture_dir)
    order = OrderInput.model_validate_json((fixture_dir / "order.json").read_text(encoding="utf-8"))
    adapter.put_order(order)
    return adapter
