let activeRegion = null;
let activeInspector = 'regions';
let detailPanzoom = null;

function updateInspector() {
  if(!state.regions.some(row => row.id === activeRegion)) activeRegion = state.regions[0]?.id;
  const picker = $('region-picker');
  picker.replaceChildren();
  for(const row of state.regions) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = row.id;
    button.setAttribute('aria-pressed', String(row.id === activeRegion));
    button.onclick = () => {
      activeRegion = row.id;
      updateInspector();
      document.querySelector('.inspector-scroll').scrollTop = 0;
    };
    picker.append(button);
  }
  for(const card of $('regions').children) {
    card.hidden = !!card.dataset.region && card.dataset.region !== activeRegion;
  }
  document.querySelector('.results-column .result-panel').hidden = activeInspector !== 'regions';
  document.querySelector('.recommendation-panel').hidden = activeInspector !== 'advice';
  $('show-regions').setAttribute('aria-pressed', String(activeInspector === 'regions'));
  $('show-advice').setAttribute('aria-pressed', String(activeInspector === 'advice'));
}
for(const name of ['regions','advice']) {
  $('show-'+name).onclick = () => {
    activeInspector = name;
    updateInspector();
    document.querySelector('.inspector-scroll').scrollTop = 0;
  };
}

function fitDetail() {
  const canvas = $('detail-canvas');
  detailPanzoom?.destroy();
  detailPanzoom = null;
  canvas.style.transform = '';
  const mobile = matchMedia('(max-width:760px)').matches;
  const widthLimit = mobile ? innerWidth*.94 : Math.min(700,innerWidth*.94-304);
  const heightLimit = Math.max(80,innerHeight*(mobile ? .43 : .7)-48);
  const scale = Math.min(1.6, widthLimit/canvas.width, heightLimit/canvas.height);
  const width = Math.max(1,Math.floor(canvas.width*scale));
  const height = Math.max(1,Math.floor(canvas.height*scale));
  canvas.style.width = width+'px';
  canvas.style.height = height+'px';
  const stage = document.querySelector('.detail-scroll');
  stage.parentElement.style.setProperty('--crop-width',width+'px');
  stage.parentElement.classList.toggle('narrow-crop',width<280);
  stage.style.width = width+'px';
  stage.style.height = height+'px';
  if(window.Panzoom) {
    detailPanzoom = Panzoom(canvas,{minScale:1,maxScale:8,panOnlyWhenZoomed:true});
  }
}
function openDetail() {
  if(!$('detail-view').open) $('detail-view').showModal();
  fitDetail();
}
$('detail-view').addEventListener('close',()=>{
  detailPanzoom?.destroy();
  detailPanzoom = null;
});
$('detail-zoom-in').onclick = () => detailPanzoom?.zoomIn();
$('detail-zoom-out').onclick = () => detailPanzoom?.zoomOut();
$('detail-fit').onclick = fitDetail;
document.querySelector('.detail-scroll').addEventListener('wheel',e=>{
  if(detailPanzoom) detailPanzoom.zoomWithWheel(e);
},{passive:false});
window.addEventListener('resize',()=>{
  if($('detail-view').open) fitDetail();
  layoutCanvas();
});
for(const name of ['full','local']) {
  $('compare-'+name).onclick = () => {
    state.compareWhole = name === 'full';
    $('compare-full').setAttribute('aria-pressed',String(state.compareWhole));
    $('compare-local').setAttribute('aria-pressed',String(!state.compareWhole));
    if(state.restored) showComparison();
  };
}
$('compare-detail').onclick = async () => {
  if(!state.restored) return notify('生成候选后，可在这里放大核对。');
  const revision = state.repairRevision;
  const [before,after] = await Promise.all([
    loadImageElement($('before-img').src),loadImageElement($('after-img').src)
  ]);
  if(revision !== state.repairRevision) return;
  const canvas = $('detail-canvas');
  canvas.width = before.width*2;
  canvas.height = before.height;
  const context = canvas.getContext('2d');
  context.drawImage(before,0,0);
  context.drawImage(after,before.width,0);
  $('detail-title').textContent = '修复核对 · 左侧原图 / 右侧候选';
  $('detail-observation').textContent = '左侧为原图，右侧为同位置的修复候选。\n\n重点检查线条是否连续、边缘有无模糊或新增纹样，再决定是否采用。\n\n可滚轮缩放，拖动画面查看细节。';
  openDetail();
};
$('source-drawer').addEventListener('toggle',layoutCanvas);
updateInspector();
