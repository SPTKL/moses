// State regressions for the dependency-free browser client. Run with node --test.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function client() {
  const nodes = new Map();
  const document = { body: {}, addEventListener() {}, getElementById(id) {
    if (!nodes.has(id)) nodes.set(id, { value: '', addEventListener() {}, replaceChildren() {}, focus() {} });
    return nodes.get(id);
  }};
  const context = vm.createContext({ document, AbortController, Error, Intl, Date, Set, console });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../src/moses/static/app.js'), 'utf8'), context);
  // Keep state transitions real; rendering is covered in browser integration.
  vm.runInContext('renderPage = () => {}; renderCatalog = () => {};', context);
  return { run: source => vm.runInContext(source, context), context, nodes };
}

test('geometry summaries recognize coordinates without hiding ordinary descriptive text', () => {
  const app = client();
  for (const [value, expected] of [
    ['MULTIPOLYGON (((0 0, 1 0, 0 0)))', 'MultiPolygon'],
    ['SRID=4326;POINT Z (1 2 3)', 'Point'],
    ['POLYGON EMPTY', 'Polygon'],
    [{ type: 'Point', coordinates: [1, 2] }, 'Point'],
    ['Point of interest', null],
    ['Polygon count is provisional', null],
    [{ type: 'Point', description: 'A business label' }, null],
  ]) {
    app.context.cellValue = value;
    assert.equal(app.run("geometryLabel(cellValue, 'description', null)"), expected);
  }
  assert.equal(app.run("geometryLabel({base64:'AQ=='}, 'geometry', 'geometry')"), 'Geometry');
});

for (const interrupted of ['versions', 'preview', 'compare', 'download']) {
  test(`failed refresh releases canceled ${interrupted} and permits retry`, async () => {
    const app = client();
    app.run(`state.token = 'test'; state.datasetId = 'ds_a'; state.busy = '${interrupted}';
      state.versions = ${interrupted === 'versions' ? '[]' : '[{version_id:"ver_a"}]'};
      api = async () => { throw new Error('Service unavailable'); };`);
    await app.run('refresh()');
    assert.equal(app.run('state.busy'), null);
    assert.equal(app.run('state.listError'), 'Service unavailable');
    if (interrupted === 'versions') assert.equal(app.run('state.pageError'), 'Service unavailable');
    // A retry can recover to an empty warehouse instead of keeping a stale detail view.
    app.run('api = async () => ({datasets: []});');
    await app.run('refresh()');
    assert.equal(app.run('state.busy'), null);
    assert.equal(app.run('state.datasetId'), null);
    assert.equal(app.run('state.versions.length'), 0);
  });
}

test('a late preview cannot restore data after sign-out', async () => {
  const app = client();
  let finish;
  app.context.pendingResponse = new Promise(resolve => { finish = resolve; });
  app.run(`state.token = 'test'; state.datasetId = 'ds_a'; state.versionId = 'ver_a';
    api = () => pendingResponse;`);
  const pending = app.run('loadPreview()');
  app.run('signOut()');
  finish({ rows: [{ secret: 'old result' }] });
  await pending;
  assert.equal(app.run('state.token'), null);
  assert.equal(app.run('state.preview'), null);
  assert.equal(app.run('state.datasetId'), null);
  assert.equal(app.nodes.get('app').hidden, true);
});

test('a late version response cannot replace a newer dataset selection', async () => {
  const app = client();
  let finish;
  app.context.firstResponse = new Promise(resolve => { finish = resolve; });
  app.run(`state.token = 'test'; state.datasets = [{dataset_id:'ds_a'}, {dataset_id:'ds_b'}];
    api = route => route.includes('ds_a') ? firstResponse : Promise.resolve({versions: []});`);
  const first = app.run("selectDataset('ds_a')");
  await app.run("selectDataset('ds_b')");
  finish({ versions: [{ version_id: 'ver_a' }] });
  await first;
  assert.equal(app.run('state.datasetId'), 'ds_b');
  assert.equal(app.run('state.versions.length'), 0);
});

test('a late map response cannot restore features after sign-out', async () => {
  const app = client();
  let finish;
  app.context.pendingMap = new Promise(resolve => { finish = resolve; });
  app.run(`state.token = 'test'; state.datasetId = 'ds_a'; state.versionId = 'ver_a';
    state.tab = 'Data'; state.dataView = 'Map'; api = () => pendingMap;`);
  const pending = app.run('loadMap()');
  app.run('signOut()');
  finish({ type: 'FeatureCollection', features: [{ properties: { secret: 'old map' } }] });
  await pending;
  assert.equal(app.run('state.token'), null);
  assert.equal(app.run('state.mapData'), null);
  assert.equal(app.run('state.datasetId'), null);
  assert.equal(app.nodes.get('app').hidden, true);
});

test('a late map response for an old version cannot replace a new version map', async () => {
  const app = client();
  let finishOld, finishNew;
  app.context.oldMap = new Promise(resolve => { finishOld = resolve; });
  app.context.newMap = new Promise(resolve => { finishNew = resolve; });
  app.run(`state.token = 'test'; state.datasetId = 'ds_a'; state.versionId = 'ver_old';
    state.versions = [{version_id:'ver_old'}, {version_id:'ver_new'}];
    state.tab = 'Data'; state.dataView = 'Map';
    api = route => route.includes('ver_old') ? oldMap : newMap;`);
  const pendingOld = app.run('loadMap()');
  app.run("selectVersion('ver_new')");
  finishNew({ type: 'FeatureCollection', version_id: 'ver_new', features: [] });
  await Promise.resolve();
  finishOld({ type: 'FeatureCollection', version_id: 'ver_old', features: [{properties:{stale:true}}] });
  await pendingOld;
  await Promise.resolve();
  assert.equal(app.run('state.versionId'), 'ver_new');
  assert.equal(app.run('state.mapData?.version_id'), 'ver_new');
});

test('a nonspatial map response returns to the usable table view', async () => {
  const app = client();
  app.run(`state.token = 'test'; state.datasetId = 'ds_a'; state.versionId = 'ver_a';
    state.tab = 'Data'; state.dataView = 'Map'; state.preview = {rows:[]};
    api = async () => { const error = new Error('This version has no mappable geometry.'); error.status = 422; throw error; };`);
  await app.run('loadMap()');
  assert.equal(app.run('state.dataView'), 'Table');
  assert.equal(app.run('state.mapData'), null);
  assert.equal(app.run('state.mapError'), 'This version has no mappable geometry.');
  assert.equal(app.run('state.busy'), null);
});
