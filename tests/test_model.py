import unittest

import numpy as np
import pandas as pd

from nfl_predictor.model import fit, predict, scores


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.train = pd.DataFrame({"x": [-2., -1., np.nan, 1., 2., 3.],
                                   "target": [0, 0, 0, 1, 1, 1]})

    def test_preprocessing_cannot_learn_from_prediction_rows(self):
        model = fit(self.train, ["x"])
        expected = predict(model, pd.DataFrame({"x": [np.nan]}))[0]
        actual = predict(model, pd.DataFrame({"x": [np.nan, 1e8]}))[0]
        self.assertEqual(expected, actual)
        self.assertEqual(model["medians"], [1.])
        self.assertEqual(len(model["beta"]), 3)  # intercept, x, missing indicator

    def test_missing_column_in_training_can_be_predicted(self):
        self.train["x"] = np.nan
        self.assertTrue(np.isfinite(predict(fit(self.train, ["x"]), self.train)).all())

    def test_ties_cannot_train_binary_model(self):
        self.train["target"] = self.train.target.astype(float)
        self.train.loc[0, "target"] = .5
        with self.assertRaises(ValueError):
            fit(self.train, ["x"])

    def test_scores_by_hand(self):
        result = scores([1, 0], [.8, .4])
        self.assertAlmostEqual(result["brier"], .1)
        self.assertEqual(result["correct"], 2)
        self.assertEqual(scores([], [])["brier"], None)
        with self.assertRaises(ValueError):
            scores([1], [np.nan])

    def test_monotonic_signal_and_serializable_model(self):
        import json
        model = json.loads(json.dumps(fit(self.train, ["x"])))
        result = predict(model, pd.DataFrame({"x": [-3., 3.]}))
        self.assertLess(result[0], result[1])
