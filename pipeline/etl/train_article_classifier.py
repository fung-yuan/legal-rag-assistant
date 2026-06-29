import os
import pickle
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

INPUT_CSV = "data/etl_intermediate/labeled_article_context.csv"
OUTPUT_MODEL = "pipeline/models/article_classifier.pkl"

def main():
    print("Training ML article boundary classifier...")
    if not os.path.exists(INPUT_CSV):
        print(f"Error: {INPUT_CSV} not found! Run generate_classifier_data.py first.")
        return

    # Load labeled training dataset
    df = pd.read_csv(INPUT_CSV, encoding="utf-8")
    df = df.dropna()
    print(f"Loaded {len(df)} samples for training.")

    X = df["context"].tolist()
    y = df["label"].tolist()

    # Build Pipeline: TF-IDF Vectorizer + Logistic Regression Classifier
    # We use character n-grams of range 2-to-5 to handle OCR spelling errors
    model_pipeline = Pipeline([
        ('vectorizer', TfidfVectorizer(
            analyzer='char_wb',
            ngram_range=(2, 5),
            lowercase=True
        )),
        ('classifier', LogisticRegression(
            C=3.0,                  # Strong regularization weight
            class_weight='balanced', # Balance weights for definition vs reference
            max_iter=1000
        ))
    ])

    # Train model
    print("Training TF-IDF + Logistic Regression pipeline...")
    model_pipeline.fit(X, y)
    print("Training completed successfully!")

    # Verify model accuracy on training data as a sanity check
    train_acc = model_pipeline.score(X, y)
    print(f"Sanity check - Training Accuracy: {train_acc * 100:.2f}%")

    # Save trained pipeline using pickle
    os.makedirs(os.path.dirname(OUTPUT_MODEL), exist_ok=True)
    with open(OUTPUT_MODEL, 'wb') as f:
        pickle.dump(model_pipeline, f)
    print(f"Model saved successfully to {OUTPUT_MODEL}!")

if __name__ == "__main__":
    main()
