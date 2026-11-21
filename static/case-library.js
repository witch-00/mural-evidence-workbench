/* Save the same portable project to SQLite; images are kept by the server as private assets. */
window.caseLibrary = (() => {
  let id=null, version=null, image=null, generation=0, serial=0, dirty=false, timer=null, pending=null;
  let loading=false, blocked=false, lastSaved=null, historyTicket=0;
  const status=$('case-save-status'), title=$('case-title'), dialog=$('case-library');
  const list=$('case-list'), history=$('case-history');
  function message(text,error=false){status.textContent=text;status.dataset.error=String(error);}
  async function request(path,body){
    const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await response.json();
    if(!response.ok){const error=new Error(data.error||'档案请求失败。');error.status=response.status;throw error;}
    return data;
  }
  function label(){return (title.value.trim() || $('file-name').textContent.replace(/\.[^.]+$/,'') || '未命名壁画档案').slice(0,80);}
  function changed(){
    if(loading || !state.imageData)return;
    serial++;dirty=true;state.dirty=true;clearTimeout(timer);
    message(blocked?'此档案已有新版本，请另存副本或重新打开。':'正在等待自动保存…',blocked);
    if(!blocked)timer=setTimeout(()=>flush().catch(()=>{}),1600);
  }
  function onEvent(action){
    if(loading)return;
    if(action==='载入图片'||action==='恢复工作进度') {
      id=null;version=null;image=state.imageData;generation++;blocked=false;
      title.value=(action==='载入图片'?$('file-name').textContent.replace(/\.[^.]+$/,''):'导入的壁画工作档案').slice(0,80);
      $('case-save-copy').hidden=true;
    }
    changed();
  }
  async function flush(){
    clearTimeout(timer);
    if(loading || !state.imageData)return lastSaved;
    if(blocked)throw new Error('此档案已有新版本，请另存副本或重新打开。');
    if(pending){await pending;if(dirty)return flush();return lastSaved;}
    if(!dirty && id)return lastSaved;
    pending=(async()=>{
      while(dirty || !id) {
        const mark=serial, current=generation;
        const project=projectSnapshot();
        // A replacement image always starts a new archive, even if an older request completes later.
        if(id && image!==state.imageData){id=null;version=null;generation++;continue;}
        message('正在保存到本机档案…');
        try {
          const saved=await request(id?'/api/cases/'+id+'/save':'/api/cases',{
            project,title:label(),expected_version:version,kind:'autosave'
          });
          if(current!==generation)return saved;
          id=saved.id;version=saved.current_version;image=state.imageData;lastSaved=saved;
          try{localStorage.setItem('mural-last-case',id);}catch{}
          if(mark===serial){dirty=false;state.dirty=false;message('已保存至本机 · 版本 '+version);}
        } catch(error) {
          if(current===generation){
            if(error.status===409){blocked=true;$('case-save-copy').hidden=false;}
            message(error.message+' 当前编辑仍保留在页面中。',true);
          }
          throw error;
        }
      }
      return lastSaved;
    })();
    try{return await pending;}finally{pending=null;}
  }
  async function beforeReplace(){
    if(loading)return true;
    try{if(dirty||pending)await flush();return true;}
    catch(error){notify(error.message+' 可先导出工作文件，或另存副本。',true);return false;}
  }
  async function saveCopy(){
    if(!state.imageData)return notify('请先导入壁画图像。',true);
    if(pending)try{await pending;}catch{}
    id=null;version=null;generation++;blocked=false;dirty=true;serial++;
    title.value=(title.value || '壁画档案').slice(0,72)+' · 副本';
    $('case-save-copy').hidden=true;
    try{await flush();notify('已另存为新档案。');}catch(error){notify(error.message,true);}
  }
  function bindNewCase(buttonId,inputId){
    const input=$(inputId);
    $(buttonId).onclick=()=>input.click();
    input.onchange=async()=>{
      const file=input.files[0];input.value='';
      if(!file)return;
      if(!await beforeReplace())return;
      if(dialog.open)dialog.close();
      await loadImage(file);
      $('source-drawer').open=true;
      $('source-drawer').scrollIntoView({block:'start'});
    };
  }
  function button(text,run){const b=document.createElement('button');b.type='button';b.textContent=text;b.onclick=run;return b;}
  function time(value){return new Date(value).toLocaleString('zh-CN',{hour12:false});}
  async function openCase(caseId,number){
    try{
      if(!blocked && !await beforeReplace())return;
      const data=await request('/api/cases/'+caseId+(number?'?version='+number:''));
      loading=true;
      const blob=new Blob([JSON.stringify(data.project)],{type:'application/json'});
      if(!await restoreProject(blob))return;
      generation++;serial++;dirty=false;blocked=false;image=state.imageData;
      const fork=number && number!==data.case.current_version;
      id=fork?null:caseId;version=fork?null:data.case.current_version;
      if(id)try{localStorage.setItem('mural-last-case',id);}catch{}
      title.value=(data.case.title+(fork?' · 版本'+number+'副本':'')).slice(0,80);
      $('case-save-copy').hidden=true;
      message(fork?'历史版本已作为副本打开，编辑后另存。':'已打开本机档案 · 版本 '+version);
      dialog.close();
      $('observe').scrollIntoView({block:'start'});
    }catch(error){notify(error.message,true);}
    finally{loading=false;}
  }
  async function showHistory(item){
    const ticket=++historyTicket;
    history.replaceChildren();const heading=document.createElement('h3');heading.textContent=item.title;history.append(heading);
    history.append(button('打开最新版本',()=>openCase(item.id)));
    const note=document.createElement('p');note.className='case-help';note.textContent='旧版本以副本打开，保留当前档案的最新内容。';history.append(note);
    try{
      const data=await request('/api/cases/'+item.id+'/versions');
      if(ticket!==historyTicket)return;
      for(const row of data.versions){
        const line=document.createElement('div');line.className='case-version';
        const text=document.createElement('span');text.textContent='版本 '+row.version+' · '+time(row.created_at);
        line.append(text,button(row.version===item.current_version?'打开':'以副本打开',()=>openCase(item.id,row.version)));history.append(line);
      }
    }catch(error){notify(error.message,true);}
  }
  async function refresh(){
    list.replaceChildren();history.textContent='选择一份档案，查看版本。';
    try {
      const data=await request('/api/cases');
      if(!data.cases.length){list.textContent='尚无档案。导入图片后会自动保存。';return;}
      for(const item of data.cases){
        const entry=button('',()=>showHistory(item));entry.className='case-entry';
        const strong=document.createElement('strong');strong.textContent=item.title;
        const small=document.createElement('span');small.textContent='版本 '+item.current_version+' · '+time(item.updated_at);
        entry.append(strong,small);list.append(entry);
      }
    }catch(error){list.textContent=error.message;}
  }
  $('open-cases').onclick=()=>{dialog.showModal();refresh();};
  $('close-cases').onclick=()=>dialog.close();
  $('save-case').onclick=async()=>{
    if(!state.imageData)return notify('请先导入壁画图像。',true);
    changed();try{await flush();notify('已保存到本机档案。');}catch(error){notify(error.message,true);}
  };
  $('case-save-copy').onclick=saveCopy;
  bindNewCase('new-case','new-case-image');
  bindNewCase('new-case-in-library','new-case-image-library');
  title.addEventListener('input',changed);
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden' && dirty && !blocked)flush().catch(()=>{});});
  request('/api/cases').then(()=>{
    if(!state.imageData){
      message('导入图像后自动保存至本机');
      let previous;try{previous=localStorage.getItem('mural-last-case');}catch{}
      if(previous && !new URLSearchParams(location.search).has('trial'))openCase(previous);
    }
  }).catch(()=>message('本机档案暂不可用，可继续导出工作文件。',true));
  return {changed,onEvent,beforeReplace,flush,saveCopy,get id(){return id;},get version(){return version;}};
})();
