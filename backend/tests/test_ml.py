"""Optional model contract checks. Numerical test tensors never enter application data."""

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("timm")
from app.ml.model import GeoMineXNet
from app.ml.train import loss_fn


def test_model_gradients_and_concession_mask():
    torch.set_num_threads(2)
    model = GeoMineXNet(image_size=64)
    before, after = torch.rand(1, 6, 64, 64), torch.rand(1, 6, 64, 64)
    output = model(before, after, legal=torch.ones(1, 1, 64, 64))
    assert output["raw_logits"].shape == (1, 1, 64, 64)
    assert output["outside_concessions"].count_nonzero() == 0
    assert torch.isfinite(output["probability"]).all()
    loss = loss_fn(
        output["raw_logits"],
        torch.zeros(1, 1, 64, 64),
        torch.ones(1, 1, 64, 64),
        torch.zeros(1, 1, 64, 64),
    )
    loss.backward()
    assert model.decoder[-1].weight.grad is not None
    assert torch.isfinite(model.decoder[-1].weight.grad).all()
