const repairMethods = [
  {id:'ai',label:'自动补全',hint:'LaMa 根据周围内容补画'},
  {id:'sample',label:'借用原图',hint:'借另一处完好图案来补'},
  {id:'telea',label:'细缝填色',hint:'用两侧颜色填细小缝隙'},
  {id:'wanx',label:'百炼重绘',hint:'通过百炼生成，需要额度'},
  {id:'auto',label:'按形状处理',hint:'自动选择传统算法',advanced:true},
  {id:'texture',label:'比对周围纹理',hint:'从附近寻找相似的小块',advanced:true},
  {id:'peel',label:'分层填补',hint:'先补底色，再匹配纹理',advanced:true},
  {id:'hybrid',label:'补全后匹配纹理',hint:'LaMa 与纹理匹配组合',advanced:true}
];
function syncRepairMethods() {
  const select = $('repair-method');
  for(const method of repairMethods) {
    const button = document.querySelector('[data-method="'+method.id+'"]');
    const option = select.querySelector('option[value="'+method.id+'"]');
    const localBlocked = ['ai','hybrid'].includes(method.id) && (state.onsite || state.aiAllowed === false);
    button.disabled = option.disabled || localBlocked;
    button.hidden = option.hidden || localBlocked;
    button.setAttribute('aria-pressed',String(select.value === method.id));
  }
  const more=document.querySelector('.more-methods');
  if(more.dataset.method !== select.value) {
    more.open=!!repairMethods.find(method=>method.id === select.value)?.advanced;
    more.dataset.method=select.value;
  }
}
for(const method of repairMethods) {
  const button = document.createElement('button');
  button.type = 'button';
  button.dataset.method = method.id;
  const name = document.createElement('strong');
  const note = document.createElement('span');
  name.textContent = method.label; note.textContent = method.hint;
  button.append(name,note);
  button.onclick = () => {
    if($('repair-method').value === method.id) return;
    $('repair-method').value = method.id;
    $('repair-method').dispatchEvent(new Event('change'));
  };
  $(method.advanced ? 'advanced-method-buttons' : 'repair-method-buttons').append(button);
}
syncRepairMethods();
