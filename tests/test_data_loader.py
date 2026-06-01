"""单元测试: data_loader 增量更新逻辑"""
import pytest
import pandas as pd
import numpy as np
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.data_loader import fetch_etf_data, _normalize, DATA_DIR


def _mock_api_df(start, end):
    """构造模拟 API 返回的 DataFrame。"""
    dates = pd.bdate_range(start, end)
    n = len(dates)
    if n == 0:
        return pd.DataFrame()
    prices = np.linspace(1.0, 1.1, n)
    df = pd.DataFrame({
        '日期': dates.strftime('%Y-%m-%d'),
        '开盘': prices * 0.99,
        '收盘': prices,
        '最高': prices * 1.01,
        '最低': prices * 0.98,
        '成交量': [1000000] * n,
        '成交额': [10000000] * n,
        '振幅': [1.0] * n,
        '涨跌幅': [0.1] * n,
        '涨跌额': [0.01] * n,
        '换手率': [0.5] * n,
    })
    return df


class TestNormalize:
    """_normalize 函数测试。"""

    def test_column_rename(self):
        df = _mock_api_df('2023-01-01', '2023-01-10')
        result = _normalize(df)
        assert 'close' in result.columns
        assert 'open' in result.columns
        assert result.index.name == 'date'

    def test_sorted_index(self):
        df = _mock_api_df('2023-01-01', '2023-01-20')
        result = _normalize(df)
        assert result.index.is_monotonic_increasing


class TestFetchWithMock:
    """使用 mock 测试 fetch_etf_data 的增量逻辑。"""

    @pytest.fixture(autouse=True)
    def setup_tmpdir(self, tmp_path, monkeypatch):
        """每个测试使用临时目录作为 DATA_DIR。"""
        self.data_dir = str(tmp_path / 'data')
        os.makedirs(self.data_dir, exist_ok=True)
        monkeypatch.setattr('src.data_loader.DATA_DIR', self.data_dir)

    def _save_cache(self, symbol, df, adjust='qfq'):
        file_path = os.path.join(self.data_dir, f"{symbol}_{adjust}.csv")
        df.to_csv(file_path)

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_full_fetch_no_cache(self, mock_api):
        """无缓存时应全量拉取。"""
        mock_api.return_value = _mock_api_df('2023-01-01', '2023-01-31')
        result = fetch_etf_data("510880", start_date="20230101", end_date="20230131")
        assert not result.empty
        assert mock_api.called

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_proxy_error_retries_without_proxy(self, mock_api, monkeypatch):
        """代理失败时应临时绕过代理重试，避免误回退旧缓存。"""
        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7897")
        mock_api.side_effect = [
            Exception("ProxyError: cannot connect to proxy"),
            _mock_api_df('2023-01-01', '2023-01-31'),
        ]

        result = fetch_etf_data("510880", start_date="20230101", end_date="20230131")

        assert not result.empty
        assert mock_api.call_count == 2
        assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:7897"

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_cache_hit(self, mock_api):
        """缓存完全覆盖时不应调用 API。"""
        cached = _normalize(_mock_api_df('2023-01-01', '2023-01-31'))
        self._save_cache('510880', cached)

        result = fetch_etf_data("510880", start_date="20230110", end_date="20230120")
        assert not result.empty
        assert not mock_api.called, "缓存命中时不应调用 API"

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_incremental_update(self, mock_api):
        """缓存部分覆盖时应仅拉取增量。"""
        # 缓存到 1月20日 (用 bdate_range 确保日期一致)
        cached = _normalize(_mock_api_df('2023-01-02', '2023-01-20'))
        self._save_cache('510880', cached)

        # 请求到 1月31日 → 只拉增量
        mock_api.return_value = _mock_api_df('2023-01-23', '2023-01-31')
        result = fetch_etf_data("510880", start_date="20230102", end_date="20230131")
        assert mock_api.called
        assert len(result) > len(cached)

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_yesterday_cache_does_not_skip_requested_end_date(self, mock_api):
        """缓存只到结束日前一天时，仍应尝试拉取结束日数据。"""
        cached = _normalize(_mock_api_df('2023-01-02', '2023-01-30'))
        self._save_cache('510880', cached)

        mock_api.return_value = _mock_api_df('2023-01-31', '2023-01-31')
        result = fetch_etf_data("510880", start_date="20230102", end_date="20230131")

        assert mock_api.called, "缓存缺少结束日时应触发增量更新"
        assert result.index.max() == pd.Timestamp("2023-01-31")

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_force_update_bypasses_cache(self, mock_api):
        """force_update=True 应全量刷新。"""
        cached = _normalize(_mock_api_df('2023-01-01', '2023-01-31'))
        self._save_cache('510880', cached)

        mock_api.return_value = _mock_api_df('2023-01-01', '2023-01-31')
        fetch_etf_data("510880", start_date="20230101", end_date="20230131", force_update=True)
        assert mock_api.called, "force_update 应跳过缓存"

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_incremental_fails_gracefully(self, mock_api):
        """增量拉取失败时应回退到缓存。"""
        cached = _normalize(_mock_api_df('2023-01-02', '2023-01-20'))
        self._save_cache('510880', cached)

        mock_api.side_effect = Exception("Network Error")
        # 请求起始 = 缓存起始，增量失败，应返回缓存数据
        result = fetch_etf_data("510880", start_date="20230102", end_date="20230131")
        assert not result.empty, "增量失败应回退到缓存"

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_api_failure_no_cache(self, mock_api):
        """无缓存 + API 失败 → 返回空 DataFrame。"""
        mock_api.side_effect = Exception("Network Error")
        result = fetch_etf_data("999999", start_date="20230101", end_date="20230131")
        assert result.empty
