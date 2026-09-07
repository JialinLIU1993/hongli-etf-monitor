"""Manual connectivity check. Importing this file never requests live data."""


def main():
    import akshare as ak

    try:
        print("Fetching index value...")
        print(ak.stock_zh_index_value_csindex(symbol="000922").tail())
        print("Fetching Treasury rate...")
        print(ak.bond_zh_us_rate().tail())
    except Exception as exc:
        print(f"Error: {exc}")


if __name__ == "__main__":
    main()
