from typing import Optional, Tuple

from pyspark.ml.recommendation import ALS
from pyspark.sql import DataFrame
from pyspark.sql.functions import col, lit
from pyspark.sql.types import DoubleType

from replay.models.base_rec import Recommender


class ALSWrap(Recommender):
    """ Обёртка для матричной факторизации `ALS на Spark
    <https://spark.apache.org/docs/latest/api/python/pyspark.mllib.html#pyspark.mllib.recommendation.ALS>`_.
    """

    _seed: Optional[int] = None
    _search_space = {
        "rank": {"type": "loguniform_int", "args": [8, 256]},
    }

    def __init__(
        self,
        rank: int = 10,
        implicit_prefs: bool = True,
        seed: Optional[int] = None,
    ):
        """
        Инициализирует параметры модели и сохраняет спарк-сессию.

        :param rank: матрицей какого ранга приближаем исходную
        :param implicit_prefs: используем ли модель для implicit feedback
        :param seed: random seed
        """
        self.rank = rank
        self.implicit_prefs = implicit_prefs
        self._seed = seed

    def _fit(
        self,
        log: DataFrame,
        user_features: Optional[DataFrame] = None,
        item_features: Optional[DataFrame] = None,
    ) -> None:
        self.model = ALS(
            rank=self.rank,
            userCol="user_idx",
            itemCol="item_idx",
            ratingCol="relevance",
            implicitPrefs=self.implicit_prefs,
            seed=self._seed,
            coldStartStrategy="drop",
        ).fit(log)
        self.model.itemFactors.cache()
        self.model.userFactors.cache()

    def _clear_cache(self):
        if hasattr(self, "model"):
            self.model.itemFactors.unpersist()
            self.model.userFactors.unpersist()

    # pylint: disable=too-many-arguments
    def _predict(
        self,
        log: DataFrame,
        k: int,
        users: DataFrame,
        items: DataFrame,
        user_features: Optional[DataFrame] = None,
        item_features: Optional[DataFrame] = None,
        filter_seen_items: bool = True,
    ) -> DataFrame:
        test_data = users.crossJoin(items).withColumn("relevance", lit(1))
        recs = (
            self.model.transform(test_data)
            .withColumn("relevance", col("prediction").cast(DoubleType()))
            .drop("prediction")
        )
        return recs

    def _predict_pairs(
        self,
        pairs: DataFrame,
        log: Optional[DataFrame] = None,
        user_features: Optional[DataFrame] = None,
        item_features: Optional[DataFrame] = None,
    ) -> DataFrame:
        return (
            self.model.transform(pairs)
            .withColumn("relevance", col("prediction").cast(DoubleType()))
            .drop("prediction")
        )

    def get_features(
        self, users: Optional[DataFrame], items: Optional[DataFrame]
    ) -> Tuple[Optional[DataFrame], Optional[DataFrame], int]:
        user_features = self.model.userFactors.withColumnRenamed(
            "id", "user_idx"
        ).withColumnRenamed("features", "user_factors")
        item_features = self.model.itemFactors.withColumnRenamed(
            "id", "item_idx"
        ).withColumnRenamed("features", "item_factors")

        return (
            users.join(user_features, how="left", on="user_idx")
            if users is not None
            else None,
            items.join(item_features, how="left", on="item_idx")
            if items is not None
            else None,
            self.model.rank,
        )
