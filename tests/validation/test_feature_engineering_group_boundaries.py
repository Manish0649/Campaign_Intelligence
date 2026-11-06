import pandas as pd

from scripts.build_m5_features import add_lagged_rolling_features


def test_rolling_features_do_not_carry_values_between_products():
    dates = pd.date_range("2020-01-01", periods=45, freq="D")
    frame = pd.DataFrame(
        [
            {"product_id": product, "date": day, "sales_units": value, "sell_price": 1.0}
            for product, value in (("SKU-A", 100), ("SKU-B", 1))
            for day in dates
        ]
    )
    result = add_lagged_rolling_features(frame)
    sku_b = result[result["product_id"] == "SKU-B"].reset_index(drop=True)

    # First 35 observations do not have a complete lag-28 history.
    assert pd.isna(sku_b.loc[0, "lag_28"])
    assert not pd.isna(sku_b.loc[34, "lag_28"])
    assert sku_b.loc[34, "rolling_mean_28"] == 1.0

    # At day 36, the 7-day rolling mean uses only SKU-B observations.
    assert sku_b.loc[35, "rolling_mean_7"] == 1.0
    assert sku_b.loc[35, "rolling_mean_28"] == 1.0


def test_rolling_features_are_null_during_each_product_warmup():
    dates = pd.date_range("2020-01-01", periods=20, freq="D")
    frame = pd.DataFrame(
        [{"product_id": p, "date": d, "sales_units": 5, "sell_price": 2.0}
         for p in ["A", "B"] for d in dates]
    )
    result = add_lagged_rolling_features(frame)
    first_b = result[result["product_id"] == "B"].iloc[0]
    assert pd.isna(first_b["lag_28"])
    assert pd.isna(first_b["rolling_mean_28"])
