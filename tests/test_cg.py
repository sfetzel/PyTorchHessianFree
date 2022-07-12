"""Test the cg-method used by the `HessianFree` optimizer."""

import pytest
import torch

from hessianfree.cg import cg
from test_utils import get_linear_system

SEEDS = [0, 1, 42]
SEEDS_IDS = [f"seed = {s}" for s in SEEDS]

DIMS = [3, 10, 50]
DIMS_IDS = [f"dim = {dim}" for dim in DIMS]

TOLS = [1e-3, 1e-6]
TOLS_IDS = [f"tol = {tol:e}" for tol in TOLS]

ATOLS = [1e-3, 1e-6]
ATOLS_IDS = [f"atol = {atol:e}" for atol in ATOLS]

DEVICES = ["cpu"]
if torch.cuda.is_available():
    DEVICES.append(torch.device("cuda"))
DEVICES_IDS = [f"device = {d}" for d in DEVICES]


@pytest.mark.parametrize("seed", SEEDS, ids=SEEDS_IDS)
@pytest.mark.parametrize("dim", DIMS, ids=DIMS_IDS)
@pytest.mark.parametrize("tol", TOLS, ids=TOLS_IDS)
@pytest.mark.parametrize("atol", ATOLS, ids=ATOLS_IDS)
@pytest.mark.parametrize("device", DEVICES, ids=DEVICES_IDS)
def test_cg_residuals(seed, dim, tol, atol, device):
    """Apply cg (without preconditioning) to a randomly chosen linear system
    until convergence. Check that the residual is within the specified
    tolerances.
    """

    msg = f"seed={seed}, dim={dim}, tol={tol}, atol={atol}, device={device}"
    print("\n===== RUN `test_cg_x_iters` =====\nwith " + msg)

    # Define problem
    A, b, x_exact = get_linear_system(dim, seed=seed, device=device)

    def A_func(x):
        return torch.matmul(A, x)

    # Apply cg until convergence
    x_iters, _ = cg(
        A_func,
        b,
        M=None,
        max_iter=10 * dim,  # `dim` only sufficient under exact arithmetics
        tol=tol,
        atol=atol,
        martens_conv_crit=False,
        store_x_at_iters=[],
        verbose=False,
    )
    x_cg = x_iters[-1]

    # Analyse results
    diff_norm = torch.linalg.norm(x_exact - x_cg).item()
    print(f"||x - x_cg|| = {diff_norm:.3e}")

    res_norm = torch.linalg.norm(A_func(x_cg) - b)
    b_norm = torch.linalg.norm(b)
    print(f"||b|| = {b_norm:.3e}")
    assert res_norm <= max(tol * b_norm, atol), "cg did not converge."


# Default tolerances for terminating cg
TOL = 1e-5
ATOL = 1e-6


@pytest.mark.parametrize("seed", SEEDS, ids=SEEDS_IDS)
@pytest.mark.parametrize("dim", DIMS, ids=DIMS_IDS)
@pytest.mark.parametrize("device", DEVICES, ids=DEVICES_IDS)
def test_cg_m_iters(seed, dim, device):
    """Apply cg (without preconditioning) to a randomly chosen linear system.
    The output `m_iters` has to correspond to evaluations of the quadratic
    `0.5 x^T A x - b^T x`.
    """

    msg = f"seed={seed}, dim={dim}, device={device}"
    print("\n===== RUN `test_cg_m_iters` =====\nwith " + msg)

    # Define problem
    A, b, _ = get_linear_system(dim, seed=seed, device=device)

    def A_func(x):
        return torch.matmul(A, x)

    # Apply cg (with default tolerances)
    x_iters, m_iters = cg(
        A_func,
        b,
        M=None,
        max_iter=10 * dim,  # `dim` only sufficient under exact arithmetics
        tol=TOL,
        atol=ATOL,
        martens_conv_crit=True,
        store_x_at_iters=list(range(10 * dim)),
        verbose=False,
    )

    # Analyse results
    def quadratic(x):
        return 0.5 * torch.dot(x, torch.matmul(A, x)) - torch.dot(b, x)

    quadratic_vals = torch.zeros(len(m_iters))
    for i in range(len(m_iters)):
        quadratic_vals[i] = quadratic(x_iters[i])
    m_vals = torch.Tensor(m_iters)

    error_msg = "Discrepancy between quadratic and `m_iters`"
    assert torch.allclose(quadratic_vals, m_vals), error_msg


@pytest.mark.parametrize("seed", SEEDS, ids=SEEDS_IDS)
@pytest.mark.parametrize("dim", DIMS, ids=DIMS_IDS)
@pytest.mark.parametrize("device", DEVICES, ids=DEVICES_IDS)
def test_pcg(seed, dim, device):
    """Test the preconditioned cg-method. We use three preconditioners: `None`,
    the identity matrix and the inverse of the system matrix `A` of the linear
    system. We make sure that the first two cases yield the same result and that
    the third case converges in not more than 2 iterations (theoretically, it
    should be one, but for large `dim`, an additional iteration seems to be
    needed to achieve convergence).
    """

    msg = f"seed={seed}, dim={dim}, device={device}"
    print("\n===== RUN `test_pcg` =====\nwith " + msg)

    # Define problem, compute inverse
    A, b, x_exact = get_linear_system(dim, seed=seed, device=device)
    A_inv = torch.linalg.inv(A)

    def A_func(x):
        return torch.matmul(A, x)

    # Define preconditioners
    def A_inverse(x):
        return torch.matmul(A_inv, x)

    def identity(x):
        return x

    # Gather results with preconditioning
    x_list = []
    for M_func in [None, identity, A_inverse]:
        x_iters, _ = cg(
            A_func,
            b,
            M=M_func,
            max_iter=10 * dim,  # `dim` only sufficient under exact arithmetics
            tol=TOL,
            atol=ATOL,
            martens_conv_crit=False,
            store_x_at_iters=list(range(10 * dim)),
            verbose=False,
        )
        x_list.append(x_iters)

    # Give explicit names
    x_none = x_list[0]
    x_identity = x_list[1]
    x_A_inverse = x_list[2]

    # Check results
    error_msg = "`None` and `identity` don't yield the same result"
    assert len(x_none) == len(x_identity), error_msg

    for x_1, x_2 in zip(x_none, x_identity):
        assert torch.equal(x_1, x_2), error_msg

    error_msg = "`A_inverse` needs more then 2 iterations."
    num_iterations = len(x_A_inverse) - 1  # `x0` is the first entry
    assert num_iterations <= 2, error_msg


if __name__ == "__main__":

    # Define problem
    dim = 3
    A, b, x_exact = get_linear_system(dim)

    def A_func(x):
        return torch.matmul(A, x)

    # Apply cg
    x_iters, m_iters = cg(
        A_func,
        b,
        M=None,
        max_iter=10 * dim,  # `dim` only sufficient under exact arithmetics
        tol=TOL,
        atol=ATOL,
        martens_conv_crit=True,
        store_x_at_iters=[0, 7],
        verbose=True,
    )

    print("\nx_iters:")
    for iter, x in enumerate(x_iters):
        print(f"iter {iter}: x = ", x)

    print("\nm_iters:")
    for iter, m in enumerate(m_iters):
        print(f"iter {iter}: m = ", m.item())