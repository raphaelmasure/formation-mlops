"""
Main script.
"""
import os
import s3fs
import tempfile
import sys
import fasttext
import mlflow
import pandas as pd
import nltk
import pyarrow.parquet as pq
from sklearn.model_selection import train_test_split
from preprocessor import Preprocessor

from constants import TEXT_FEATURE, Y, DATA_PATH
from fasttext_wrapper import FastTextWrapper


def load_data():
    """
    Load data for training and test.
    """
    fs = s3fs.S3FileSystem(
        client_kwargs={"endpoint_url": "https://minio.lab.sspcloud.fr"}
    )
    df = pq.ParquetDataset(DATA_PATH, filesystem=fs).read_pandas().to_pandas()
    return df.sample(frac=0.001)


def train(
    remote_server_uri,
    experiment_name,
    run_name,
    dim,
    lr,
    epoch,
    wordNgrams,
    minn,
    maxn,
    minCount,
    bucket,
    thread
):
    """
    Train a FastText model.
    """
    nltk.download('stopwords')

    mlflow.set_tracking_uri(remote_server_uri)
    mlflow.set_experiment(experiment_name)
    with mlflow.start_run(run_name=run_name):
        # Get preprocessor and data
        preprocessor = Preprocessor()
        df = load_data()

        # Preprocess data to train and test a FastText model
        df = preprocessor.clean_text(df, TEXT_FEATURE)

        X_train, X_test, y_train, y_test = train_test_split(
            df[TEXT_FEATURE],
            df[Y],
            test_size=0.2,
            random_state=0,
            shuffle=True,
        )

        df_train = pd.concat([X_train, y_train], axis=1)
        df_test = pd.concat([X_test, y_test], axis=1)

        # Train the model and log to MLflow tracking server
        params = {
            "dim": dim,
            "lr": lr,
            "epoch": epoch,
            "wordNgrams": wordNgrams,
            "minn": minn,
            "maxn": maxn,
            "minCount": minCount,
            "bucket": bucket,
            "thread": thread,
            "loss": "ova",
            "label_prefix": "__label__",
        }
        with tempfile.TemporaryDirectory() as tmpdirname:
            training_data_path = os.path.join(tmpdirname, "training_data.txt")
            with open(training_data_path, "w", encoding="utf-8") as file:
                for item in df_train.iterrows():
                    formatted_item = (
                        f"__label__{item[1][Y]} {item[1][TEXT_FEATURE]}"
                    )
                    file.write(f"{formatted_item}\n")

                model = fasttext.train_supervised(
                    file.name, **params, verbose=2
                )

            # Save model for logging
            model_path = os.path.join(tmpdirname, run_name + ".bin")
            model.save_model(model_path)

            artifacts = {
                "model_path": model_path,
            }

            mlflow.pyfunc.log_model(
                artifact_path=run_name,
                python_model=FastTextWrapper(),
                code_path=[
                    "src/fasttext_wrapper.py",
                    "src/preprocessor.py",
                    "src/constants.py"
                ],
                artifacts=artifacts,
            )

        # Log parameters
        for param_name, param_value in params.items():
            mlflow.log_param(param_name, param_value)

        # Evaluation
        test_texts = []
        for item in df_test.iterrows():
            formatted_item = item[1][TEXT_FEATURE]
            test_texts.append(formatted_item)

        predictions = model.predict(test_texts, k=1)
        predictions = [x[0].replace("__label__", "") for x in predictions[0]]

        booleans = [
            prediction == label
            for prediction, label in zip(predictions, df_test[Y])
        ]
        accuracy = sum(booleans) / len(booleans)

        # Log accuracy
        mlflow.log_metric("accuracy", accuracy)


if __name__ == "__main__":
    remote_server_uri = sys.argv[1]
    experiment_name = sys.argv[2]
    run_name = sys.argv[3]
    dim = sys.arv[4]
    lr = sys.arv[5]
    epoch = sys.arv[6]
    wordNgrams = sys.arv[7]
    minn = sys.arv[8]
    maxn = sys.arv[9]
    minCount = sys.arv[10]
    bucket = sys.arv[11]
    thread = sys.arv[12]

    train(
        remote_server_uri,
        experiment_name,
        run_name,
        dim,
        lr,
        epoch,
        wordNgrams,
        minn,
        maxn,
        minCount,
        bucket,
        thread
    )
