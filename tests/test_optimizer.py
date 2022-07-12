"""Test the `HessianFree` optimizer."""

import pytest
import torch

from hessianfree.optimizer import HessianFree
from test_utils import (
    get_linear_system,
    get_small_nn_testproblem,
    TargetFuncModel,
)

SEEDS = [0, 1, 42]
SEEDS_IDS = [f"seed = {s}" for s in SEEDS]

CURV_OPTS = ["hessian", "ggn"]
CURV_OPTS_IDS = [f"curvature_opt = {c}" for c in CURV_OPTS]

DEVICES = ["cpu"]
if torch.cuda.is_available():
    DEVICES.append(torch.device("cuda"))
DEVICES_IDS = [f"device = {d}" for d in DEVICES]


@pytest.mark.parametrize("seed", SEEDS, ids=SEEDS_IDS)
@pytest.mark.parametrize("curvature_opt", CURV_OPTS, ids=CURV_OPTS_IDS)
@pytest.mark.parametrize("device", DEVICES, ids=DEVICES_IDS)
def test_on_neural_network(seed, curvature_opt, device):
    """This simply sets up and runs the `HessianFree` optimizer on a small
    neural network. Apart from running without throwing an error, no further
    checks are applied.
    """

    msg = f"seed={seed}, curvature_opt={curvature_opt}, device={device}"
    print("\n===== TEST `HessianFree` on a small neural network =====\n" + msg)

    # Create test problem
    torch.manual_seed(seed)
    model, data, loss_function = get_small_nn_testproblem(
        freeze_first_layer=True, device=device
    )
    inputs, targets = data

    def eval_loss_and_outputs():
        outputs = model(inputs)
        loss = loss_function(outputs, targets)
        return loss, outputs

    # Set up optimizer
    damping = 1.5 if curvature_opt == "hessian" else 0.1
    opt = HessianFree(
        model.parameters(),
        curvature_opt=curvature_opt,
        damping=damping,
        verbose=True,
    )

    # Perform some update steps
    for step_idx in range(3):
        print(f"\n===== STEP {step_idx} =====")
        opt.step(eval_loss_and_outputs)


DIMS = [3, 5, 10]
DIMS_IDS = [f"dim = {d}" for d in DIMS]


@pytest.mark.parametrize("seed", SEEDS, ids=SEEDS_IDS)
@pytest.mark.parametrize("dim", DIMS, ids=DIMS_IDS)
@pytest.mark.parametrize("device", DEVICES, ids=DEVICES_IDS)
def test_on_quadratic(seed, dim, device):
    """This function sets up and runs the `HessianFree` optimizer on a quadratic
    function. In this particular case, it has to converge in a single Newton
    step.

    NOTE: This test case is resticted to lower dimensions because for
    `dim > 10`, Martens' convergence criterion is triggered in `cg` which
    prevents `cg` from running until actual convergence.
    """

    msg = f"seed={seed}, dim={dim}, device={device}"
    print("\n===== TEST `HessianFree` on a quadratic =====\n" + msg)

    # Create test problem
    torch.manual_seed(seed)
    init_params = (torch.rand((dim, 1)) - 0.5).to(device)

    A, b, _ = get_linear_system(dim, seed=seed, device=device)
    assert torch.all(torch.linalg.eigvalsh(A) > 0), "Matrix A is not pos. def."
    b = b.reshape(dim, 1)
    c = (torch.rand(1) - 0.5).to(device)

    def quadratic(x):
        return 0.5 * x.T @ A @ x + x.T @ b + c

    model = TargetFuncModel(quadratic, init_params)
    opt_params = torch.linalg.solve(A, -b)
    print("\nopt_params = ", opt_params.T)

    def eval_loss_and_outputs():
        return model.eval_loss(), None

    # Set up optimizer
    opt = HessianFree(
        [model.params],
        curvature_opt="hessian",  # use the Hessian
        lr=1.0,
        use_linesearch=False,  # fixed lerning rate
        damping=0.0,  # no damping
        adapt_damping=False,
        use_cg_backtracking=False,  # no cg-backtracking
        verbose=True,
    )

    # Training
    def eval_dist_to_opt():
        return torch.linalg.norm(model.params - opt_params).detach().item()

    init_dist = eval_dist_to_opt()
    print(f"\nInitial distance to optimum = {init_dist}")

    opt.step(eval_loss_and_outputs)

    final_dist = eval_dist_to_opt()
    print(f"\nFinal distance to optimum = {final_dist}")
    assert torch.allclose(model.params, opt_params, atol=1e-3)


if __name__ == "__main__":

    test_on_neural_network(seed=0, curvature_opt="hessian", device="cpu")
    test_on_neural_network(seed=0, curvature_opt="ggn", device="cpu")
    test_on_quadratic(seed=0, dim=5, device="cpu")
