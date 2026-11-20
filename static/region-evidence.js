const evidenceFields = [
  ['reference','依据出处与位置','如：原图 R1 右缘，或参考图 2 左上方',80],
  ['alternative','另一种解释（有分歧时填写）','这处痕迹还有什么可能？',60],
  ['reason','复核理由','写下支持你作出决定的可见细节',80],
  ['follow_up','还需核实','如：需更高分辨率图像来核对线条边缘',60]
];
const reviewChoices = ['保留观察','修正观察','暂缓判断'];
function hasEvidence(row) {
  const e = row.evidence;
  return e && reviewChoices.includes(e.decision) && e.reference?.trim() && e.reason?.trim()
    && (e.decision !== '暂缓判断' || e.follow_up?.trim());
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
  if(value.decision && !reviewChoices.includes(value.decision)) throw new Error('工作文件中的复核决定无效。');
  e.decision = value.decision || '';
  return e;
}
function evidenceEditor(row) {
  const box = document.createElement('fieldset');
  box.className = 'region-evidence';
  const title = document.createElement('legend');
  title.textContent = row.id+' 区域证据卡';
  box.append(title);
  const e = row.evidence ??= {};
  const decision = document.createElement('select');
  decision.add(new Option('选择复核决定',''));
  for(const choice of reviewChoices) decision.add(new Option(choice,choice));
  decision.value = e.decision || '';
  decision.onchange = () => { e.decision = decision.value; invalidateReview(); };
  function addField(name,input) {
    const label = document.createElement('label');
    label.append(document.createTextNode(name),input);
    box.append(label);
    input.setAttribute('aria-label',row.id+' '+name);
  }
  for(const [key,name,hint,max] of evidenceFields) {
    if(key === 'reason') addField('人工决定',decision);
    addField(name,textarea(e[key] || '',hint,max,value => { e[key] = value; }));
  }
  return box;
}
