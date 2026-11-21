let activeRegion = null;
let activeInspector = 'regions';
let detailPanzoom = null;

function syncRegionPicker(picker, repair=false) {
  const ids=state.regions.map(row=>row.id);
  if(picker.children.length!==ids.length || [...picker.children].some((button,i)=>button.dataset.region!==ids[i])) {
    picker.replaceChildren(...ids.map(id=>{
      const button=document.createElement('button');button.type='button';button.dataset.region=id;button.textContent=id;
      button.onclick=()=>{
        activeRegion=id;
        if(repair)state.compareWhole=false;
        updateInspector();
        document.querySelector('.inspector-scroll').scrollTop=0;
        if(state.restored)showComparison().catch(error=>notify(error.message,true));
      };
      return button;
    }));
  }
  for(const button of picker.children)button.setAttribute('aria-pressed',String(button.dataset.region===activeRegion));
}

function updateInspector() {
  const previous=activeRegion;
  if(!state.regions.some(row => row.id === activeRegion)) activeRegion = state.regions[0]?.id || null;
  syncRegionPicker($('region-picker'));
  syncRegionPicker($('repair-region-picker'),true);
  $('repair-region-help').textContent=state.regions.length ? '切换对照局部；修复范围以原图涂抹为准。' : '框选关注区域后，可在此切换局部。';
  if(previous!==activeRegion && state.restored)showComparison().catch(error=>notify(error.message,true));
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
function revealPendingReview(row) {
  activeRegion=row.id; activeInspector='regions'; updateInspector();
  $('observe').scrollIntoView({block:'start'});
  const card=[...$('regions').children].find(item=>item.dataset.region===row.id);
  const issue=evidenceIssue(row);
  let field;
  if(issue.field==='references') {
    field=$('references');
  } else if(issue.field==='decision') {
    field=card.querySelector('.review-choices button');
  } else if(issue.field==='observation') {
    field=card.querySelector('textarea');
  } else {
    field=card.querySelector('[data-evidence="'+issue.field+'"]');
  }
  const details=field.closest('details');if(details)details.open=true;
  field.setAttribute('aria-invalid','true');
  field.scrollIntoView({block:'center'});field.focus();notify(row.id+'：'+issue.message,true);
}
function revealAdviceScope(row) {
  activeInspector='advice';updateInspector();
  const index=state.recommendations.indexOf(row),scope=$('recommendations').children[index].querySelector('.advice-scope');
  const error=scope.querySelector('.scope-error');
  error.textContent='请选择适用范围：整幅画面，或这条建议所针对的局部编号。';error.hidden=false;
  for(const input of scope.querySelectorAll('input'))input.setAttribute('aria-invalid','true');
  scope.scrollIntoView({block:'center'});scope.querySelector('input').focus({preventScroll:true});
  notify('建议 '+(index+1)+'：请在“建议适用范围”中点选整幅画面或局部编号。',true);
}
updateInspector();
