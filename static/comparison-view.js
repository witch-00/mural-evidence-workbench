let fullscreenPanzoom=null;
let comparisonSources=null;

function updateCompareButtons() {
  for(const prefix of ['compare','fullscreen']) {
    $(prefix+'-full').setAttribute('aria-pressed',String(!!state.compareWhole));
    $(prefix+'-local').setAttribute('aria-pressed',String(!state.compareWhole));
  }
}
function fitComparison() {
  if(!comparisonSources)return;
  fullscreenPanzoom?.destroy();
  fullscreenPanzoom=null;
  const stage=$('fullscreen-stage'),pair=$('fullscreen-pair');
  const image=$('fullscreen-after');
  if(!image.naturalWidth || !image.naturalHeight)return;
  const scale=Math.min(stage.clientWidth/image.naturalWidth,stage.clientHeight/image.naturalHeight);
  pair.style.width=Math.floor(image.naturalWidth*scale)+'px';
  pair.style.height=Math.floor(image.naturalHeight*scale)+'px';
  if(window.Panzoom) {
    fullscreenPanzoom=Panzoom(pair,{minScale:1,maxScale:8,panOnlyWhenZoomed:true,exclude:[$('fullscreen-range')]});
  }
}
function syncComparisonView(before,after,caption) {
  comparisonSources={before,after,caption};
  updateCompareButtons();
  $('comparison-caption').textContent=caption;
  $('inline-comparison-caption').textContent=caption;
  if($('comparison-view').open) updateFullscreenImages();
}
async function updateFullscreenImages() {
  const sources=comparisonSources;
  await Promise.all([
    loadImageElement(sources.before),loadImageElement(sources.after)
  ]);
  if(sources!==comparisonSources || !$('comparison-view').open)return;
  $('fullscreen-before').src=sources.before;$('fullscreen-after').src=sources.after;
  await $('fullscreen-after').decode();
  if(sources!==comparisonSources || !$('comparison-view').open)return;
  $('fullscreen-range').value=50;moveFullscreenDivider();fitComparison();
}
function moveFullscreenDivider() {
  const split=Number($('fullscreen-range').value);
  $('fullscreen-before-clip').style.clipPath='inset(0 '+(100-split)+'% 0 0)';
  $('fullscreen-divider').style.left=split+'%';
}
$('fullscreen-range').oninput=moveFullscreenDivider;
$('compare-detail').onclick=async()=>{
  if(!state.restored)return notify('先涂出要补的位置，再点“预览修复效果”。');
  await showComparison();
  if(!state.restored)return;
  $('comparison-view').showModal();
  updateFullscreenImages();
};
$('close-comparison').onclick=()=>$('comparison-view').close();
$('comparison-view').addEventListener('close',()=>{
  fullscreenPanzoom?.destroy();fullscreenPanzoom=null;
});
$('fullscreen-in').onclick=()=>fullscreenPanzoom?.zoomIn();
$('fullscreen-out').onclick=()=>fullscreenPanzoom?.zoomOut();
$('fullscreen-fit').onclick=fitComparison;
$('fullscreen-stage').addEventListener('wheel',e=>{
  if(fullscreenPanzoom)fullscreenPanzoom.zoomWithWheel(e);
},{passive:false});
window.addEventListener('resize',()=>{
  if($('comparison-view').open)fitComparison();
});
for(const prefix of ['compare','fullscreen']) {
  for(const view of ['full','local']) {
    $(prefix+'-'+view).onclick=()=>{
      state.compareWhole=view==='full';
      updateCompareButtons();
      if(state.restored)showComparison();
      else notify('预览修复效果后，可以在这里切换对照视野。');
    };
  }
}


function fitInlineComparison() {
  const image=$('after-img'),pair=document.querySelector('.compare-inner'),stage=$('compare');
  if(!image.naturalWidth || !image.naturalHeight || pair.hidden)return;
  const scale=Math.min(stage.clientWidth/image.naturalWidth,stage.clientHeight/image.naturalHeight);
  pair.style.width=Math.floor(image.naturalWidth*scale)+'px';
  pair.style.height=Math.floor(image.naturalHeight*scale)+'px';
}
$('after-img').addEventListener('load',fitInlineComparison);
window.addEventListener('resize',fitInlineComparison);
