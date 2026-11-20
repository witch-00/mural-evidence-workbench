const evidenceFields = [
  ['reference','依据位置与可见特征','例如：R1 右缘，细暗线沿纹样延伸；或《资料名》第 2 页图 3',80],
  ['alternative','其他可能解释（选填）','例如：细暗线可能为原有笔线，尚不能认定为裂隙',60],
  ['reason','补充意见（选填）','补充所选理由；选择“其他理由”时必填',80],
  ['follow_up','判断边界（选填）','例如：本图只支持记录色差，不能判断颜料、材质与成因',60]
];
const reviewLabels = {adopt:'采纳描述',revise:'修改后采纳',reject:'不采纳',insufficient:'本图无法判断'};
const reviewChoices = Object.keys(reviewLabels);
const legacyDecisions = {'保留观察':'adopt','修正观察':'revise','暂缓判断':'insufficient'};
const evidenceSources = {image:'原图对照',reference:'资料对照',opinion:'无直接依据'};
const reasonLabels = {visible:'原图特征相符',reference_match:'参考资料相符',overstated:'原描述推断过度',
  motif:'原有笔线或纹样',artifact:'拍摄或画质影响',no_feature:'未见所述异常',extent:'位置或范围不准',
  resolution:'分辨率不足',cause:'照片不能判定成因',no_reference:'缺少对照资料',other:'其他理由'};
const reasonChoices = {adopt:['visible','reference_match','other'],revise:['overstated','motif','artifact','extent','other'],
  reject:['no_feature','motif','artifact','overstated','other'],insufficient:['resolution','artifact','cause','no_reference','other']};
function evidenceIssue(row) {
  const e=row.evidence || {};
  if(!reviewChoices.includes(e.decision))return {field:'decision',message:'请选择复核意见。'};
  if(!Object.hasOwn(evidenceSources,e.source_type))return {field:'source_type',message:'请选择依据类型。'};
  if(e.source_type==='opinion' && ['adopt','revise'].includes(e.decision))
    return {field:'source_type',message:'没有直接依据，不能采纳描述。请补充依据，或选择“不采纳／本图无法判断”。'};
  if(e.source_type==='reference' && !$('references').value.trim())
    return {field:'references',message:'请在“图像与资料”登记参考资料的标题、页码或链接。'};
  if(!reasonChoices[e.decision].includes(e.reason_code))return {field:'reason_code',message:'请选择本次结论的理由。'};
  if(e.reason_code==='reference_match' && e.source_type!=='reference')
    return {field:'source_type',message:'请选择“资料对照”，并登记资料出处。'};
  if(e.decision==='revise' && initialRow(row,'regions')?.observation===row.observation)
    return {field:'observation',message:'描述尚未修改，请先修订上方描述，或选择“采纳描述”。'};
  for(const key of [...(['adopt','revise'].includes(e.decision)?['reference']:[]),...(e.reason_code==='other'?['reason']:[])])
    if(!e[key]?.trim())return {field:key,message:'请填写“'+evidenceFields.find(item=>item[0]===key)[1]+'”。'};
  return null;
}
function hasEvidence(row) {
  return !evidenceIssue(row);
}
function readEvidence(value) {
  if(value === undefined) return {};
  if(!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('工作文件的区域复核记录无效。');
  const e = {};
  for(const [key,label,,max] of evidenceFields) {
    if(value[key] === undefined) continue;
    if(typeof value[key] !== 'string' || value[key].length > max)
      throw new Error('工作文件的“'+label+'”内容无效。');
    e[key] = value[key];
  }
  e.decision = legacyDecisions[value.decision] || value.decision || '';
  if(e.decision && !reviewChoices.includes(e.decision)) throw new Error('工作文件中的复核决定无效。');
  if(value.reason_code && !Object.hasOwn(reasonLabels,value.reason_code))throw new Error('工作文件中的复核理由无效。');
  e.reason_code=value.reason_code || '';
  if(value.include_note !== undefined && typeof value.include_note!=='boolean')throw new Error('补充说明选项无效。');
  e.include_note=value.include_note || false;
  if(value.source_type !== undefined && value.source_type !== '' && !Object.hasOwn(evidenceSources,value.source_type))
    throw new Error('工作文件中的依据类型无效。');
  e.source_type = value.source_type || '';
  return e;
}
function evidenceEditor(row) {
  const box = document.createElement('fieldset');
  box.className = 'region-evidence';
  const title = document.createElement('legend');
  title.textContent = row.id+' · 本次结论';
  box.append(title);
  const e = row.evidence ??= {};
  const choices = document.createElement('div');
  choices.className = 'review-choices';
  choices.setAttribute('role','group');
  choices.setAttribute('aria-label',row.id+' 本次结论');
  for(const value of reviewChoices) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = reviewLabels[value];
    button.dataset.decision = value;
    button.setAttribute('aria-pressed',String(e.decision === value));
    button.onclick = () => {
      e.decision = value;
      if(!reasonChoices[value].includes(e.reason_code))e.reason_code='';
      for(const item of choices.children) item.setAttribute('aria-pressed',String(item === button));
      renderReasons();
      for(const field of box.querySelectorAll('[aria-invalid]'))field.removeAttribute('aria-invalid');
      invalidateReview();
    };
    choices.append(button);
  }
  box.append(choices);
  const reasons=document.createElement('fieldset');reasons.className='evidence-sources evidence-reasons';
  function renderReasons() {
    reasons.replaceChildren();reasons.hidden=!e.decision;
    const legend=document.createElement('legend');legend.textContent='选择理由';reasons.append(legend);
    for(const value of reasonChoices[e.decision] || []) {
      const label=document.createElement('label'),input=document.createElement('input');
      input.type='radio';input.name='evidence-reason-'+row.id;input.value=value;
      input.id='evidence-reason-'+row.id+'-'+value;input.checked=e.reason_code===value;
      input.dataset.evidence='reason_code';label.htmlFor=input.id;
      input.onchange=()=>{
        e.reason_code=value;
        for(const field of reasons.querySelectorAll('[aria-invalid]'))field.removeAttribute('aria-invalid');
        if(value==='other'){extras.open=true;extras.querySelector('[data-evidence=reason]').focus();}
        invalidateReview();
      };
      label.append(input,document.createTextNode(reasonLabels[value]));reasons.append(label);
    }
  }
  renderReasons();box.append(reasons);
  const sourceGroup=document.createElement('fieldset');
  sourceGroup.className='evidence-sources';
  const sourceLegend=document.createElement('legend');sourceLegend.textContent='依据类型';sourceGroup.append(sourceLegend);
  for(const [value,name] of Object.entries(evidenceSources)) {
    const label=document.createElement('label'),input=document.createElement('input');
    input.type='radio';input.name='evidence-source-'+row.id;input.value=value;
    input.id='evidence-source-'+row.id+'-'+value;input.checked=e.source_type===value;
    input.dataset.evidence='source_type';label.htmlFor=input.id;
    input.onchange=()=>{e.source_type=value;for(const field of sourceGroup.querySelectorAll('[aria-invalid]'))field.removeAttribute('aria-invalid');invalidateReview();};
    label.append(input,document.createTextNode(name));sourceGroup.append(label);
  }
  box.append(sourceGroup);
  const help=document.createElement('p');help.className='evidence-help';help.id='evidence-help-'+row.id;
  help.textContent='选择本次结论与理由。图像信息不足时，选择“本图无法判断”即可完成记录。';box.append(help);
  const extras=document.createElement('details'),extraTitle=document.createElement('summary');
  extras.className='evidence-extras';extraTitle.textContent='补充说明（选填）';extras.append(extraTitle);
  const extraHelp=document.createElement('p');extraHelp.className='evidence-help';
  extraHelp.textContent='默认仅随工作进度保存。选择“其他理由”时，所填理由会写入卡片。';extras.append(extraHelp);
  const includeLabel=document.createElement('label'),include=document.createElement('input');
  include.type='checkbox';include.id='include-note-'+row.id;include.checked=!!e.include_note;
  includeLabel.htmlFor=include.id;includeLabel.className='include-note';
  include.onchange=()=>{e.include_note=include.checked;invalidateReview();};
  includeLabel.append(include,document.createTextNode('将补充说明写入观察卡'));extras.append(includeLabel);
  for(const [key,name,hint,max] of evidenceFields) {
    const label = document.createElement('label');
    const input = textarea(e[key] || '',hint,max,value => { e[key] = value; });
    input.dataset.evidence = key;
    input.id='evidence-'+row.id+'-'+key;label.htmlFor=input.id;
    input.name=key;
    input.setAttribute('aria-describedby',help.id);
    input.addEventListener('input',()=>input.removeAttribute('aria-invalid'));
    label.append(document.createTextNode(name),input);
    if(key==='reference')box.append(label);else extras.append(label);
  }
  box.append(extras);
  return box;
}
