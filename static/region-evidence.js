const evidenceFields = [
  ['reference','你参考了哪里？','例如：R1 放大的原图，或参考图 2 的左上角',80],
  ['alternative','还有别的可能吗？（可选）','例如：这条细线也可能是原来的笔线',60],
  ['reason','你为什么这样判断？','例如：细线沿着花纹走，暂时无法确定是裂缝',80],
  ['follow_up','还需要看什么？','例如：需要一张更清楚的照片',60]
];
const reviewChoices = ['保留观察','修正观察','暂缓判断'];
const reviewLabels = {'保留观察':'描述准确','修正观察':'我改过描述','暂缓判断':'暂时拿不准'};
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
  title.textContent = row.id+' 这条描述准确吗？';
  box.append(title);
  const e = row.evidence ??= {};
  const choices = document.createElement('div');
  choices.className = 'review-choices';
  choices.setAttribute('role','group');
  choices.setAttribute('aria-label',row.id+' 这条描述准确吗');
  for(const value of reviewChoices) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = reviewLabels[value];
    button.dataset.decision = value;
    button.setAttribute('aria-pressed',String(e.decision === value));
    button.onclick = () => {
      e.decision = value;
      for(const item of choices.children) item.setAttribute('aria-pressed',String(item === button));
      invalidateReview();
    };
    choices.append(button);
  }
  box.append(choices);
  for(const [key,name,hint,max] of evidenceFields) {
    const label = document.createElement('label');
    const input = textarea(e[key] || '',hint,max,value => { e[key] = value; });
    input.dataset.evidence = key;
    input.setAttribute('aria-label',row.id+' '+name);
    label.append(document.createTextNode(name),input);
    box.append(label);
  }
  return box;
}
