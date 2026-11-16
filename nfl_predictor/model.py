"""Small regularized logistic model; preprocessing is fitted on training rows only."""

import numpy as np


def sigmoid(values):
    return 1 / (1 + np.exp(-np.clip(values, -35, 35)))


def design(frame, names, medians=None, mean=None, scale=None):
    values = frame[names].to_numpy(dtype=float)
    if np.isinf(values).any():
        raise ValueError("Infinite feature value")
    missing = np.isnan(values)
    if medians is None:
        medians = np.array([
            np.median(col[~np.isnan(col)]) if (~np.isnan(col)).any() else 0.
            for col in values.T
        ])
    filled = np.where(missing, np.asarray(medians), values)
    # Unknown inputs have their own indicators; an imputation is not measured zero.
    expanded = np.column_stack([filled, missing.astype(float)])
    if mean is None:
        mean = expanded.mean(axis=0)
        scale = expanded.std(axis=0)
        scale[scale < 1e-8] = 1.
    z = np.column_stack([np.ones(len(values)), (expanded - mean) / scale])
    return z, np.asarray(medians), np.asarray(mean), np.asarray(scale)


def fit(frame, names, alpha=60.):
    if frame.empty or not frame.target.isin([0, 1]).all():
        raise ValueError("Training requires decisive binary results")
    if alpha <= 0:
        raise ValueError("Regularization must be positive")
    z, medians, mean, scale = design(frame, names)
    y = frame.target.to_numpy(float)
    beta = np.zeros(z.shape[1])
    penalty = np.eye(len(beta)) * alpha
    penalty[0, 0] = 1e-6
    converged = False
    for iteration in range(80):
        p = sigmoid(z @ beta)
        weights = np.maximum(p * (1 - p), 1e-6)
        step = np.linalg.solve((z.T * weights) @ z + penalty,
                               z.T @ (p - y) + penalty @ beta)
        beta -= step
        if np.max(np.abs(step)) < 1e-7:
            converged = True
            break
    if not converged:
        raise RuntimeError("Logistic fit did not converge")
    return {"names": list(names), "medians": medians.tolist(),
            "mean": mean.tolist(), "scale": scale.tolist(), "beta": beta.tolist(),
            "alpha": float(alpha), "iterations": iteration + 1}


def predict(model, frame):
    z, *_ = design(frame, model["names"], model["medians"],
                    model["mean"], model["scale"])
    return sigmoid(z @ np.asarray(model["beta"]))


def scores(y, probabilities):
    y, p = np.asarray(y, dtype=float), np.asarray(probabilities, dtype=float)
    if len(y) == 0:
        return {"games": 0, "correct": 0, "accuracy": None,
                "brier": None, "log_loss": None}
    if y.shape != p.shape or not np.isin(y, [0, 1]).all():
        raise ValueError("Scores require aligned decisive outcomes")
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Invalid probabilities")
    clipped = np.clip(p, 1e-12, 1 - 1e-12)
    correct = int(((p >= .5) == y).sum())
    return {"games": len(y), "correct": correct, "accuracy": correct / len(y),
            "brier": float(np.mean((p - y) ** 2)),
            "log_loss": float(-np.mean(y * np.log(clipped) +
                                       (1 - y) * np.log(1 - clipped)))}
