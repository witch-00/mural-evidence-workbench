/* Image-specific evidence stays editable; reviewed literature templates retain their wording. */
window.adviceSources = (() => {
  let data=null, fetching=null, selectedRow=null, category='conservation';
  const labels={conservation:'保护建议',display:'数字展示',outreach:'公众传播'};
  const dialog=$('advice-library'), templates=$('advice-templates');
  async function load(){
    if(data)return data;
    if(!fetching)fetching=fetch('/api/references').then(async r=>{
      if(!r.ok)throw new Error('文献目录加载失败，请稍后重试。');
      data=await r.json();return data;
    }).finally(()=>{fetching=null;});
    return fetching;
  }
  function item(id){return data?.templates.find(t=>t.id===id);}
  function source(id){return data?.sources.find(s=>s.id===id);}
  function link(source,locator){
    const p=document.createElement('p'),a=document.createElement('a');
    a.href=source.full_text_url||source.url;a.target='_blank';a.rel='noopener noreferrer';
    a.textContent='['+source.id+'] '+source.authors+'（'+source.year+'）'+source.short_title;
    p.append(a,document.createElement('br'),document.createTextNode(locator||source.locator));return p;
  }
  function apply(template){
    if(!state.recommendations.includes(selectedRow))return notify('当前建议已变化，请重新打开。',true);
    Object.assign(selectedRow,{template_id:template.id,category:template.category,source_ids:[...template.source_ids],
      action:template.action,risk:template.risk});
    // The book's general principle must never be substituted for the user's evidence in this image.
    invalidateReview();eventRecord('选择文献建议',{template_id:template.id,source_ids:template.source_ids});
    renderLists();dialog.close();
    notify('已关联文献。请补充或核对这条建议的“本图依据”。');
  }
  function render(){
    templates.replaceChildren();
    for(const t of data.templates.filter(t=>t.category===category)){
      const card=document.createElement('article');card.className='template-card';
      const heading=document.createElement('h3');heading.textContent=t.label;
      const action=document.createElement('p');action.textContent=t.action;
      const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='文献依据、风险与适用范围';details.append(summary);
      for(const [label,text] of [['文献原则',t.basis],['可能风险',t.risk],['适用条件',t.applicability],['适用边界',t.limitations]]){
        const p=document.createElement('p'),b=document.createElement('strong');b.textContent=label+'：';p.append(b,document.createTextNode(text));details.append(p);
      }
      for(const id of t.source_ids)details.append(link(source(id),t.source_locators[id]));
      const use=document.createElement('button');use.type='button';use.textContent='采用这条建议';use.dataset.template=t.id;use.onclick=()=>apply(t);
      card.append(heading,action,details,use);templates.append(card);
    }
    for(const b of $('advice-categories').children)b.setAttribute('aria-pressed',String(b.dataset.category===category));
  }
  async function open(row){
    selectedRow=row;category=labels[row.category]?row.category:'conservation';dialog.showModal();templates.textContent='正在读取已核验的文献目录…';
    try{await load();render();}catch(error){templates.textContent=error.message;}
  }
  function attach(card,row,index){
    const t=item(row.template_id);
    if(t){
      const tag=document.createElement('span');tag.className='advice-category-label';tag.textContent=labels[t.category]+' · '+t.label;card.append(tag);
      const note=document.createElement('p');note.className='reference-note';note.textContent='行动与风险按文献模板保留。请确认建议适用范围，并填写本图的具体依据。';card.append(note);
      const details=document.createElement('details'),summary=document.createElement('summary');
      details.className='reference-details';summary.textContent='查看专业文献依据';details.append(summary);
      const principle=document.createElement('p');principle.textContent='文献原则：'+t.basis;details.append(principle);
      const bounds=document.createElement('p');bounds.textContent='适用范围：'+t.applicability+' '+t.limitations;details.append(bounds);
      for(const id of t.source_ids)details.append(link(source(id),t.source_locators[id]));card.append(details);
      for(const key of ['action','risk'])card.querySelector('[data-advice="'+key+'"]').readOnly=true;
    }else{
      const note=document.createElement('p');note.className='reference-missing';note.textContent='导出观察卡前，请选择一条有具体文献依据的建议。';card.append(note);
    }
    const choose=document.createElement('button');choose.type='button';choose.className='reference-choose';choose.textContent=t?'更换文献建议':'从权威文献选择建议';choose.setAttribute('aria-label','建议 '+(index+1)+' '+choose.textContent);choose.onclick=()=>open(row);card.append(choose);
  }
  function issue(row){
    if(!data)return '文献目录尚未就绪，请稍后重试。';
    const t=item(row.template_id);
    if(!t)return '请选择一条已核验的文献建议。';
    if(row.action!==t.action || row.risk!==t.risk)return '行动或风险已改变，请重新选择文献建议，本案差异写在本图依据中。';
    if(!row.basis?.trim())return '请填写本图中支持这条建议的具体可见依据。';
    return '';
  }
  function reveal(row){
    activeInspector='advice';updateInspector();$('observe').scrollIntoView({block:'start'});
    const index=state.recommendations.indexOf(row),card=$('recommendations').children[index];
    const field=!row.basis?.trim()?card.querySelector('[data-advice=basis]'):card.querySelector('.reference-choose');
    field.scrollIntoView({block:'center'});field.focus();notify('建议 '+(index+1)+'：'+issue(row),true);
  }
  for(const [value,name] of Object.entries(labels)){
    const b=document.createElement('button');b.type='button';b.dataset.category=value;b.textContent=name;
    b.onclick=()=>{category=value;if(data)render();};$('advice-categories').append(b);
  }
  $('close-advice-library').onclick=()=>dialog.close();
  load().then(()=>{if(state.imageData)renderLists();}).catch(()=>{});
  return {load,attach,issue,reveal,open};
})();
