import json
from pathlib import Path
import subprocess
import shutil
import pytest
from scripts.build_pages import build


def test_public_artifact(tmp_path):
    build(tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {'index.html', 'app.css', 'app.js', 'plotly.min.js', 'market.json', '.nojekyll'}
    data = json.loads((tmp_path / 'market.json').read_text())
    assert set(data) == {'schema', 'provider', 'source', 'price_basis', 'assets', 'data_as_of', 'built_at'}
    assert set(data['assets']) == {'510880', '512890'}
    assert data['data_as_of'] == min(a['rows'][-1]['date'] for a in data['assets'].values())
    for asset in data['assets'].values():
        assert asset['optimization']
        assert all(set(r) == {'date', 'open', 'high', 'low', 'close', 'volume', 'ma', 'upper_band', 'lower_band', 'position', 'signal'} for r in asset['rows'])


def test_browser_ledger(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is unavailable')
    source = Path('web/app.js').read_text().split("document.querySelectorAll('[data-page]').forEach(b=>b.onclick")[0]
    assertions = '''
const assert=require('node:assert/strict');
data={assets:{'510880':{rows:[{close:3}]},'512890':{rows:[{close:1}]}}};
const buy={date:'2026-01-01',symbol:'510880',side:'buy',quantity:100,price:2,fee:1,note:''};
assert.equal(validRecord({...buy,date:'2026-02-31'}),false);
assert.equal(validRecord({...buy,quantity:1e20}),false);
assert.equal(validRecord({...buy,price:Infinity}),false);
assert.throws(()=>portfolio([{...buy,side:'sell'}]),/卖出/);
const result=portfolio([buy,{...buy,date:'2026-01-02',side:'sell',quantity:40,price:3,fee:1}]);
assert.equal(result.positions[0].quantity,60);
assert.ok(Math.abs(result.realized-38.6)<1e-9);
assert.ok(Math.abs(result.positions[0].cost-120.6)<1e-9);
'''
    script=tmp_path/'ledger.cjs'
    script.write_text(source+assertions)
    subprocess.run([node,str(script)],check=True)
