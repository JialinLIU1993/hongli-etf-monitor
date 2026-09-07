"""单元测试: data_loader 增量更新逻辑"""
import pytest
import pandas as pd
import numpy as np
import os
import sys
from collections import OrderedDict
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.data_loader import fetch_etf_data, _normalize


@pytest.fixture(autouse=True)
def isolate_provider_configuration(monkeypatch):
    monkeypatch.setenv('ETF_DATA_PROVIDER', 'akshare')
    monkeypatch.delenv('HITHINK_FINANCE_API_KEY', raising=False)


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

    def test_numeric_cleanup_and_duplicate_dates(self):
        raw = _mock_api_df('2023-01-02', '2023-01-06')
        raw.loc[0, '日期'] = 'invalid'
        raw.loc[1, '收盘'] = -1
        raw.loc[2, '最高'] = np.inf
        valid = raw.iloc[[3, 4]].copy()
        raw = pd.concat([raw, valid.iloc[[0]]], ignore_index=True)
        raw['成交量'] = raw['成交量'].astype(str)
        result = _normalize(raw)
        assert result.index.tolist() == list(pd.to_datetime(valid['日期']))
        assert pd.api.types.is_numeric_dtype(result['volume'])

    def test_does_not_modify_api_dataframe(self):
        raw = _mock_api_df('2023-01-02', '2023-01-06')
        original = raw.copy(deep=True)
        _normalize(raw)
        pd.testing.assert_frame_equal(raw, original)

    def test_rejects_incomplete_schema(self):
        with pytest.raises(ValueError, match='价格列'):
            _normalize(pd.DataFrame({'日期': ['2023-01-02'], '收盘': [1.0]}))

    def test_rejects_missing_dates(self):
        with pytest.raises(ValueError, match='日期列'):
            _normalize(_mock_api_df('2023-01-02', '2023-01-06').drop(columns='日期'))

    def test_optional_missing_volume_preserves_valid_prices(self):
        raw = _mock_api_df('2023-01-02', '2023-01-06')
        raw.loc[0, '成交量'] = np.nan
        raw.loc[1, '成交量'] = -1
        result = _normalize(raw, allow_missing_volume=True)
        assert len(result) == 4
        assert pd.isna(result.loc['2023-01-02', 'volume'])
        assert pd.Timestamp('2023-01-03') not in result.index
        assert len(_normalize(raw)) == 3


class TestFetchWithMock:
    """使用 mock 测试 fetch_etf_data 的增量逻辑。"""

    @pytest.fixture(autouse=True)
    def setup_tmpdir(self, tmp_path, monkeypatch):
        """每个测试使用临时目录作为 DATA_DIR。"""
        self.data_dir = str(tmp_path / 'data')
        os.makedirs(self.data_dir, exist_ok=True)
        monkeypatch.setattr('src.data_loader.DATA_DIR', self.data_dir)
        monkeypatch.setattr('src.data_loader.SEED_DATA_DIR', str(tmp_path / 'seed'))
        # Do not let process-level coverage from other tests affect assertions.
        monkeypatch.setattr('src.data_loader._RECENT_REQUESTS', OrderedDict())

    def _save_cache(self, symbol, df, adjust='qfq'):
        file_path = os.path.join(self.data_dir, f"{symbol}_{adjust}.csv")
        df.to_csv(file_path)

    def _save_seed(self, symbol, df, adjust='qfq'):
        seed_dir = os.path.join(self.data_dir, 'seed')
        os.makedirs(seed_dir, exist_ok=True)
        file_path = os.path.join(seed_dir, f"{symbol}_{adjust}.csv")
        df.to_csv(file_path)
        return seed_dir

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
    def test_seed_initializes_cache(self, mock_api, monkeypatch):
        """无运行时缓存但有 seed 数据时，应先用 seed 初始化，避免全量拉取。"""
        seeded = _normalize(_mock_api_df('2023-01-01', '2023-01-31'))
        seed_dir = self._save_seed('510880', seeded)
        monkeypatch.setattr('src.data_loader.SEED_DATA_DIR', seed_dir)

        result = fetch_etf_data("510880", start_date="20230110", end_date="20230120")

        assert not result.empty
        assert not mock_api.called, "seed 覆盖请求范围时不应调用 API"
        assert os.path.exists(os.path.join(self.data_dir, "510880_qfq.csv"))

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

    @patch('src.data_loader.ak.fund_etf_hist_em')
    @pytest.mark.parametrize('contents', ['', 'not,a,price,file\nhello,world,1,2\n'])
    def test_unreadable_cache_recovers_from_api(self, mock_api, contents):
        file_path = os.path.join(self.data_dir, '510880_qfq.csv')
        with open(file_path, 'w') as handle:
            handle.write(contents)
        mock_api.return_value = _mock_api_df('2023-01-02', '2023-01-06')
        result = fetch_etf_data('510880', '20230102', '20230106')
        assert len(result) == 5
        assert result.attrs['data_source'] == 'api'
        assert len(pd.read_csv(file_path)) == 5

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_unreadable_cache_and_api_failure_return_empty(self, mock_api):
        with open(os.path.join(self.data_dir, '510880_qfq.csv'), 'w') as handle:
            handle.write('broken cache')
        mock_api.side_effect = RuntimeError('unavailable')
        result = fetch_etf_data('510880', '20230102', '20230106')
        assert result.empty
        assert 'warning' in result.attrs

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_empty_forced_refresh_preserves_valid_cache(self, mock_api):
        cached = _normalize(_mock_api_df('2023-01-02', '2023-01-31'))
        self._save_cache('510880', cached)
        file_path = os.path.join(self.data_dir, '510880_qfq.csv')
        original = open(file_path).read()
        mock_api.return_value = pd.DataFrame()
        result = fetch_etf_data('510880', '20230110', '20230120', force_update=True)
        pd.testing.assert_frame_equal(result, cached.loc['2023-01-10':'2023-01-20'])
        assert open(file_path).read() == original
        assert 'warning' in result.attrs

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_smaller_force_refresh_preserves_both_cache_ends(self, mock_api):
        cached = _normalize(_mock_api_df('2023-01-02', '2023-01-31'))
        self._save_cache('510880', cached)
        mock_api.return_value = _mock_api_df('2023-01-02', '2023-01-31')
        result = fetch_etf_data('510880', '20230110', '20230120', force_update=True)
        assert mock_api.call_args.kwargs['start_date'] == '20230102'
        assert mock_api.call_args.kwargs['end_date'] == '20230131'
        assert result.index.min() == pd.Timestamp('2023-01-10')
        assert result.index.max() == pd.Timestamp('2023-01-20')
        assert len(pd.read_csv(os.path.join(self.data_dir, '510880_qfq.csv'))) == len(cached)

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_write_failure_keeps_fresh_data_and_old_file(self, mock_api):
        cached = _normalize(_mock_api_df('2023-01-02', '2023-01-20'))
        self._save_cache('510880', cached)
        file_path = os.path.join(self.data_dir, '510880_qfq.csv')
        original = open(file_path).read()
        mock_api.return_value = _mock_api_df('2023-01-23', '2023-01-31')
        with patch('src.data_loader.os.replace', side_effect=PermissionError('read only')):
            result = fetch_etf_data('510880', '20230102', '20230131')
        assert result.index.max() == pd.Timestamp('2023-01-31')
        assert result.attrs['data_source'] == 'api'
        assert '保存失败' in result.attrs['warning']
        assert open(file_path).read() == original
        assert not any(name.endswith('.tmp') for name in os.listdir(self.data_dir))

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_holiday_range_is_not_requested_repeatedly(self, mock_api):
        mock_api.return_value = _mock_api_df('2023-01-02', '2023-01-06')
        fetch_etf_data('510880', '20230101', '20230108')
        result = fetch_etf_data('510880', '20230101', '20230108')
        assert mock_api.call_count == 1
        assert len(result) == 5
        assert result.attrs['data_source'] == 'cache'

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_empty_increment_is_checked_once_until_ttl(self, mock_api):
        cached = _normalize(_mock_api_df('2023-01-02', '2023-01-06'))
        self._save_cache('510880', cached)
        mock_api.return_value = pd.DataFrame()
        with patch('src.data_loader.monotonic', return_value=0):
            fetch_etf_data('510880', '20230102', '20230108')
        with patch('src.data_loader.monotonic', return_value=299):
            fetch_etf_data('510880', '20230102', '20230108')
        assert mock_api.call_count == 1
        with patch('src.data_loader.monotonic', return_value=301):
            fetch_etf_data('510880', '20230102', '20230108')
        assert mock_api.call_count == 2

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_today_candle_refreshes_after_ttl(self, mock_api):
        today = pd.Timestamp.now().normalize()
        raw = _mock_api_df('2023-01-02', '2023-01-02')
        raw['日期'] = today.strftime('%Y-%m-%d')
        self._save_cache('510880', _normalize(raw))
        raw.loc[0, '收盘'] = 1.005
        mock_api.return_value = raw
        date_str = today.strftime('%Y%m%d')
        result = fetch_etf_data('510880', date_str, date_str)
        assert mock_api.call_count == 1
        assert result['close'].iloc[-1] == 1.005
        fetch_etf_data('510880', date_str, date_str)
        assert mock_api.call_count == 1
        with patch('src.data_loader.monotonic', return_value=float('inf')):
            fetch_etf_data('510880', date_str, date_str)
        assert mock_api.call_count == 2

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_new_adjustment_factor_refreshes_entire_history(self, mock_api):
        original = _mock_api_df('2023-01-02', '2023-01-31')
        original[['开盘', '收盘', '最高', '最低']] *= 2
        cached = _normalize(original).loc[:'2023-01-20']
        self._save_cache('510880', cached)
        revised = _mock_api_df('2023-01-02', '2023-01-31')
        mock_api.side_effect = [revised.iloc[14:].copy(), revised]
        result = fetch_etf_data('510880', '20230102', '20230131')
        assert mock_api.call_count == 2
        assert mock_api.call_args.kwargs['start_date'] == '20230102'
        pd.testing.assert_frame_equal(result, _normalize(revised), check_freq=False)

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_incomplete_adjustment_refresh_does_not_mix_prices(self, mock_api):
        original = _mock_api_df('2023-01-02', '2023-01-31')
        original[['开盘', '收盘', '最高', '最低']] *= 2
        cached = _normalize(original).loc[:'2023-01-20']
        self._save_cache('510880', cached)
        file_path = os.path.join(self.data_dir, '510880_qfq.csv')
        original_file = open(file_path).read()
        revised = _mock_api_df('2023-01-02', '2023-01-31').iloc[14:].copy()
        mock_api.return_value = revised
        result = fetch_etf_data('510880', '20230102', '20230131')
        assert mock_api.call_count == 2
        pd.testing.assert_frame_equal(result, cached)
        assert 'warning' in result.attrs
        assert open(file_path).read() == original_file

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_force_update_bypasses_recent_request(self, mock_api):
        mock_api.return_value = _mock_api_df('2023-01-02', '2023-01-06')
        fetch_etf_data('510880', '20230101', '20230108')
        fetch_etf_data('510880', '20230101', '20230108', force_update=True)
        assert mock_api.call_count == 2

    @patch('src.data_loader.ak.fund_etf_hist_em')
    @pytest.mark.parametrize('symbol,start,end,adjust', [
        ('../510880', '20230101', '20230108', 'qfq'),
        ('510880', '20230108', '20230101', 'qfq'),
        ('510880', 'NaT', '20230108', 'qfq'),
        ('510880', '20230101', '20230108', '../qfq'),
    ])
    def test_invalid_request_is_rejected_before_network(self, mock_api, symbol, start, end, adjust):
        with pytest.raises(ValueError):
            fetch_etf_data(symbol, start, end, adjust)
        assert not mock_api.called

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_failed_proxy_retry_restores_environment(self, mock_api, monkeypatch):
        monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:7897')
        monkeypatch.delenv('https_proxy', raising=False)

        def failed_request(**kwargs):
            if mock_api.call_count == 2:
                assert 'HTTPS_PROXY' not in os.environ
            raise RuntimeError('ProxyError: unavailable')

        mock_api.side_effect = failed_request
        result = fetch_etf_data('510880', '20230102', '20230106')
        assert result.empty
        assert mock_api.call_count == 2
        assert os.environ['HTTPS_PROXY'] == 'http://127.0.0.1:7897'
        assert 'https_proxy' not in os.environ


class TestHithinkProvider:
    @pytest.fixture(autouse=True)
    def setup_tmpdir(self, tmp_path, monkeypatch):
        self.data_dir = tmp_path / 'data'
        self.data_dir.mkdir()
        self.seed_dir = tmp_path / 'seed'
        self.seed_dir.mkdir()
        monkeypatch.setattr('src.data_loader.DATA_DIR', str(self.data_dir))
        monkeypatch.setattr('src.data_loader.SEED_DATA_DIR', str(self.seed_dir))
        monkeypatch.setattr('src.data_loader._RECENT_REQUESTS', OrderedDict())

    def _prices(self, start='2023-01-02', end='2023-01-06'):
        return _normalize(_mock_api_df(start, end))

    def _cache(self, prices, provider='hithink'):
        name = '510880_hithink_original.csv' if provider == 'hithink' else '510880_qfq.csv'
        path = self.data_dir / name
        prices.to_csv(path)
        return path

    @patch('src.hithink_api.HithinkClient')
    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_fetch_uses_isolated_cache_and_original_price_basis(self, ak_api, client):
        ak_cache = self._cache(self._prices() * 10, provider='akshare')
        ak_contents = ak_cache.read_bytes()
        prices = self._prices()
        prices.loc['2023-01-02', ['volume', 'amount']] = np.nan
        client.return_value.fetch_etf_history.return_value = prices

        result = fetch_etf_data('510880', '20230102', '20230106',
                                provider='hithink', api_key='test-key')

        client.assert_called_once_with('test-key')
        client.return_value.fetch_etf_history.assert_called_once_with('510880', '20230102', '20230106')
        ak_api.assert_not_called()
        assert len(result) == 5
        assert pd.isna(result['volume'].iloc[0])
        assert pd.isna(result['amount'].iloc[0])
        assert result.attrs['provider'] == 'hithink'
        assert result.attrs['price_basis'] == '接口原始口径（无复权选项）'
        assert result.attrs['volume_unit'] == '接口原始单位'
        assert result.attrs['data_source'] == 'api'
        assert 'test-key' not in str(result.attrs)
        assert ak_cache.read_bytes() == ak_contents
        own_cache = self.data_dir / '510880_hithink_original.csv'
        assert own_cache.exists()
        assert 'test-key' not in own_cache.read_text()

        cached = fetch_etf_data('510880', '20230102', '20230106',
                                provider='hithink', api_key='test-key')
        assert len(cached) == 5
        assert pd.isna(cached['volume'].iloc[0])
        assert cached.attrs['provider'] == 'hithink'
        assert cached.attrs['data_source'] == 'cache'
        assert client.call_count == 1

    @patch('src.hithink_api.HithinkClient')
    def test_missing_key_returns_only_same_provider_cache(self, client):
        self._cache(self._prices(), provider='akshare')
        (self.seed_dir / '510880_qfq.csv').write_text('unused AkShare seed')
        with patch('src.data_loader._seed_cache_if_available') as seed:
            empty = fetch_etf_data('510880', '20230102', '20230106', provider='hithink')
        assert empty.empty
        assert '尚未配置' in empty.attrs['warning']
        assert empty.attrs['provider'] == 'hithink'
        seed.assert_not_called()

        own_cache = self._cache(self._prices())
        old_contents = own_cache.read_bytes()
        result = fetch_etf_data('510880', '20230103', '20230105',
                                provider='hithink', force_update=True)
        assert len(result) == 3
        assert result.attrs['data_source'] == 'cache'
        assert '尚未配置' in result.attrs['warning']
        assert own_cache.read_bytes() == old_contents
        client.assert_not_called()

    @pytest.mark.parametrize('adjust', ['qfq', 'hfq'])
    @patch('src.hithink_api.HithinkClient')
    def test_explicit_adjusted_prices_rejected(self, client, adjust):
        with pytest.raises(ValueError, match='不支持'):
            fetch_etf_data('510880', '20230102', '20230106', adjust,
                           provider='hithink', api_key='test-key')
        client.assert_not_called()
        assert list(self.data_dir.iterdir()) == []

    @patch('src.hithink_api.HithinkClient')
    def test_environment_selects_provider_and_key(self, client, monkeypatch):
        monkeypatch.setenv('ETF_DATA_PROVIDER', 'hithink')
        monkeypatch.setenv('HITHINK_FINANCE_API_KEY', 'env-key')
        client.return_value.fetch_etf_history.return_value = self._prices()
        result = fetch_etf_data('510880', '20230102', '20230106')
        client.assert_called_once_with('env-key')
        assert result.attrs['provider'] == 'hithink'

    @patch('src.hithink_api.HithinkClient')
    def test_explicit_blank_key_does_not_use_environment_key(self, client, monkeypatch):
        monkeypatch.setenv('HITHINK_FINANCE_API_KEY', 'env-key')
        result = fetch_etf_data('510880', '20230102', '20230106',
                                provider='hithink', api_key=' ')
        assert result.empty
        assert '尚未配置' in result.attrs['warning']
        client.assert_not_called()

    @patch('src.hithink_api.HithinkClient')
    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_failure_does_not_fall_back_to_other_source_or_expose_key(self, ak_api, client, caplog):
        self._cache(self._prices(), provider='akshare')
        client.return_value.fetch_etf_history.side_effect = RuntimeError('Authorization: secret-api-key')
        result = fetch_etf_data('510880', '20230102', '20230106',
                                provider='hithink', api_key='secret-api-key')
        assert result.empty
        assert result.attrs['provider'] == 'hithink'
        assert 'secret-api-key' not in caplog.text
        assert 'secret-api-key' not in str(result.attrs)
        ak_api.assert_not_called()

    @patch('src.hithink_api.HithinkClient')
    def test_failure_preserves_same_provider_cache(self, client):
        from src.hithink_api import HithinkAPIError
        own_cache = self._cache(self._prices())
        old_contents = own_cache.read_bytes()
        client.return_value.fetch_etf_history.side_effect = HithinkAPIError('authentication')
        result = fetch_etf_data('510880', '20230102', '20230110',
                                provider='hithink', api_key='test-key')
        assert len(result) == 5
        assert '权限不足' in result.attrs['warning']
        assert own_cache.read_bytes() == old_contents
        client.return_value.fetch_etf_history.assert_called_once_with('510880', '20230106', '20230110')

    @patch('src.hithink_api.HithinkClient')
    def test_holiday_ttl_and_force_refresh(self, client):
        client.return_value.fetch_etf_history.return_value = self._prices()
        with patch('src.data_loader.monotonic', return_value=0):
            fetch_etf_data('510880', '20230101', '20230108', provider='hithink', api_key='test-key')
        with patch('src.data_loader.monotonic', return_value=299):
            cached = fetch_etf_data('510880', '20230101', '20230108', provider='hithink', api_key='test-key')
        assert client.call_count == 1
        assert cached.attrs['data_source'] == 'cache'
        with patch('src.data_loader.monotonic', return_value=301):
            fetch_etf_data('510880', '20230101', '20230108', provider='hithink', api_key='test-key')
            fetch_etf_data('510880', '20230101', '20230108', provider='hithink',
                           api_key='test-key', force_update=True)
        assert client.call_count == 3

    @patch('src.hithink_api.HithinkClient')
    def test_today_candle_refreshes_after_ttl(self, client):
        today = pd.Timestamp.now().normalize()
        prices = self._prices('2023-01-02', '2023-01-02')
        prices.index = pd.DatetimeIndex([today], name='date')
        self._cache(prices)
        prices.loc[today, 'close'] = 1.005
        client.return_value.fetch_etf_history.return_value = prices
        date = today.strftime('%Y%m%d')
        result = fetch_etf_data('510880', date, date, provider='hithink', api_key='test-key')
        assert result['close'].iloc[0] == 1.005
        fetch_etf_data('510880', date, date, provider='hithink', api_key='test-key')
        assert client.call_count == 1
        with patch('src.data_loader.monotonic', return_value=float('inf')):
            fetch_etf_data('510880', date, date, provider='hithink', api_key='test-key')
        assert client.call_count == 2

    @patch('src.hithink_api.HithinkClient')
    def test_failed_atomic_write_retains_updated_prices_and_original_cache(self, client):
        own_cache = self._cache(self._prices())
        old_contents = own_cache.read_bytes()
        client.return_value.fetch_etf_history.return_value = self._prices('2023-01-06', '2023-01-10')
        with patch('src.data_loader.os.replace', side_effect=PermissionError('read only')):
            result = fetch_etf_data('510880', '20230102', '20230110', provider='hithink', api_key='test-key')
        assert result.index.max() == pd.Timestamp('2023-01-10')
        assert result.attrs['data_source'] == 'api'
        assert '保存失败' in result.attrs['warning']
        assert own_cache.read_bytes() == old_contents
        assert not list(self.data_dir.glob('*.tmp'))

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_akshare_metadata_keeps_requested_adjustment(self, ak_api):
        ak_api.return_value = _mock_api_df('2023-01-02', '2023-01-06')
        result = fetch_etf_data('510880', '20230102', '20230106', adjust='hfq', provider='akshare')
        assert result.attrs['provider'] == 'akshare'
        assert result.attrs['price_basis'] == '后复权'
        assert (self.data_dir / '510880_hfq.csv').exists()

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_akshare_failure_cannot_use_hithink_history(self, ak_api):
        own_cache = self._cache(self._prices())
        old_contents = own_cache.read_bytes()
        ak_api.side_effect = RuntimeError('unavailable')
        result = fetch_etf_data('510880', '20230102', '20230106', provider='akshare')
        assert result.empty
        assert result.attrs['provider'] == 'akshare'
        assert own_cache.read_bytes() == old_contents

    @patch('src.data_loader.ak.fund_etf_hist_em')
    def test_invalid_provider_rejected_before_io(self, ak_api):
        with pytest.raises(ValueError, match='行情来源'):
            fetch_etf_data('510880', '20230102', '20230106', provider='../invalid')
        ak_api.assert_not_called()
        assert list(self.data_dir.iterdir()) == []
