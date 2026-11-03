"""Question sorting (DSO2 backup, and DSO1 idea B "predict the problem type").

TF-IDF (word + character n-grams) and logistic regression, trained on the Bitext
customer messages of the 17 order-linked intents. Evaluated on a held-out 20%.
"""

# How it works: the message is turned into numbers with TF-IDF (how important each word and each 3-5 letter
# piece is), then a logistic regression picks the most likely intent. Simple, fast (milliseconds) and
# explainable.
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline

from callverse.config import POLICY_DIR, RAW_DIR, load_yaml

# The trained model is saved here: artifacts/policies/intent_classifier.joblib.
MODEL_FILE = "intent_classifier.joblib"
BITEXT_FILE = RAW_DIR / "bitext" / "bitext-retail-ecommerce-llm-chatbot-training-dataset.csv"


def intent_groups() -> dict[str, str]:
    """Intent -> intent group (wismo, cancel_refund, post_delivery, order_admin)."""
    groups = load_yaml("data")["generation"]["contacts"]["intent_groups"]
    return {intent: group for group, intents in groups.items() for intent in intents}


@dataclass
class IntentPrediction:
    # intent: e.g. track_order; intent_group: wismo, cancel_refund, post_delivery or order_admin; confidence:
    # the probability of that intent (0 to 1).
    intent: str
    intent_group: str
    confidence: float


class IntentClassifier:
    """Predicts one of the 17 order-linked intents from a customer message."""

    def __init__(self, pipeline: Pipeline, metrics: dict[str, Any] | None = None) -> None:
        self.pipeline = pipeline
        self.metrics = metrics or {}
        self.groups = intent_groups()

    def predict(self, text: str) -> IntentPrediction:
        # predict_proba gives one probability per intent; we keep the highest one.
        probabilities = self.pipeline.predict_proba([text])[0]
        best = int(probabilities.argmax())
        intent = str(self.pipeline.classes_[best])
        return IntentPrediction(intent, self.groups.get(intent, "order_admin"), float(probabilities[best]))

    @classmethod
    def train(cls, test_size: float = 0.2, seed: int = 42) -> "IntentClassifier":
        # Bitext: a public dataset of customer-service messages, each labelled with its intent.
        data = pd.read_csv(BITEXT_FILE)
        data = data[data["intent"].isin(intent_groups())]
        data = data[~data["tags"].fillna("").str.contains("W")]  # offensive messages excluded
        # Keep 20% of the messages aside for testing; stratify keeps the same intent shares in both parts.
        train, test = train_test_split(data, test_size=test_size, random_state=seed, stratify=data["intent"])
        # The pipeline: two TF-IDF feature sets joined together (words and word pairs; character 3-5 grams,
        # which resist typos), then a logistic regression.
        pipeline = Pipeline(
            [
                (
                    "features",
                    FeatureUnion(
                        [
                            ("words", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
                            (
                                "chars",
                                TfidfVectorizer(
                                    analyzer="char_wb", ngram_range=(3, 5), min_df=3, sublinear_tf=True
                                ),
                            ),
                        ]
                    ),
                ),
                ("model", LogisticRegression(max_iter=2000, C=5.0)),
            ]
        )
        # Train on 80%, then measure accuracy and macro F1 on the unseen 20%.
        pipeline.fit(train["instruction"], train["intent"])
        predicted = pipeline.predict(test["instruction"])
        groups = intent_groups()
        metrics = {
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "accuracy": float(accuracy_score(test["intent"], predicted)),
            "macro_f1": float(f1_score(test["intent"], predicted, average="macro")),
            # group_accuracy: the right problem GROUP (enough to route the chat to the right desk).
            "group_accuracy": float(
                accuracy_score(test["intent"].map(groups), pd.Series(predicted).map(groups))
            ),
        }
        return cls(pipeline, metrics)

    def save(self, path: Path = POLICY_DIR / MODEL_FILE) -> None:
        """Save the model and its metrics with joblib (a fast pickle for scikit-learn objects)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"pipeline": self.pipeline, "metrics": self.metrics}, path)

    @classmethod
    def load_or_train(cls, path: Path = POLICY_DIR / MODEL_FILE) -> "IntentClassifier":
        """Load the saved model, or train and save it the first time."""
        if path.exists():
            payload = joblib.load(path)
            return cls(payload["pipeline"], payload["metrics"])
        settings = load_yaml("agents")["advisor"]["intent_classifier"]
        classifier = cls.train(float(settings["test_size"]), int(settings["random_seed"]))
        classifier.save(path)
        return classifier
