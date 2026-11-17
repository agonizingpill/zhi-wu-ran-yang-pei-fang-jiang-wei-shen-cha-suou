import {store,refresh} from '../store.js';import {api,session} from '../api.js';import {heading} from '../components/common.js';import {escape,decimal,notify,formData} from '../utils.js';import {REVIEW_VERDICTS,REVIEW_STATES} from '../constants.js';

const verdictClass={match:'approved',mismatch:'rejected',inconclusive:'verified'};
const recipeOf=id=>store.recipes.find(r=>r.id===id);
const currentReview=swid=>store.reviews.find(x=>x.swatch_id===swid&&x.state==='current');

export function render(){
 const isViewer=session().role==='viewer',isAdmin=session().role==='admin';
 const withdrawn=new Set((store.impacts?.withdrawn||[]).map(x=>x.id));
 const needReview=store.swatches.filter(s=>!s.withdrawn&&!currentReview(s.id));
 return heading('10','光谱串样审查：贴错配方也逃不过近邻归属','用其余有效染样的 36 波段近邻配方判断归属，排除自身与已撤回样本；保存参与样本、距离与判定依据。证据不足转待复核，色差门限继续有效。')
 +`<div class="split" style="grid-template-columns:1.55fr .9fr">
 <section class="panel">
  <h2>发起审查</h2>
  <div class="actions">
   <button id="run-all" class="primary" ${isViewer?'disabled':''}>审查全部待算染样（${needReview.length}）</button>
   <button id="rerun-all" ${isViewer?'disabled':''}>重算全部染样</button>
  </div>
  <p class="hint">近邻距离 = 36 波段反射率均方根距离；参与样本少于 3 张或缺少同配方佐证时转待复核。每次重算归档旧结论，不覆盖历史。</p>
  <h2>审查结论 · ${store.reviews.filter(x=>x.state==='current').length} 条有效 / ${store.reviews.filter(x=>x.state==='superseded').length} 条失效留痕</h2>
  <div style="max-height:520px;overflow:auto">
   <table><thead><tr><th>染样</th><th>登记配方</th><th>近邻配方</th><th>最近距离</th><th>判定</th><th>状态</th><th>操作</th></tr></thead><tbody>
   ${store.swatches.map(s=>{
    const rev=currentReview(s.id);const old=store.reviews.find(x=>x.swatch_id===s.id&&x.state==='superseded');
    const reg=recipeOf(s.recipe_id);
    if(s.withdrawn)return `<tr class="row-warn"><td>${escape(s.lot)}<br><small>已撤回</small></td><td>${escape(reg?.code)}</td><td colspan="3" class="hint">${escape(s.withdraw_reason)}</td><td><span class="status rejected">已撤回</span></td><td><button data-withdraw="${s.id}" disabled>主管撤回</button></td></tr>`;
    if(!rev)return `<tr><td>${escape(s.lot)}</td><td>${escape(reg?.code)}</td><td colspan="3" class="hint">尚未审查${old?'（旧结论已失效，需重算）':''}</td><td><span class="status verified">待审查</span></td><td><button data-run="${s.id}" ${isViewer?'disabled':''}>发起审查</button> <button data-withdraw="${s.id}" ${isAdmin?'':'disabled'}>主管撤回</button></td></tr>`;
    const near=recipeOf(rev.nearest_recipe_id);
    return `<tr><td>${escape(s.lot)}</td><td>${escape(reg?.code)}</td><td>${escape(near?.code||'—')}</td><td>${rev.nearest_distance==null?'—':decimal(rev.nearest_distance,4)}</td>
     <td><span class="status ${verdictClass[rev.verdict]}">${REVIEW_VERDICTS[rev.verdict]}</span>${rev.manual_override_by?'<br><small>人工:'+escape(rev.manual_override_by)+'</small>':''}</td>
     <td>${REVIEW_STATES[rev.state]}</td>
     <td><button data-evidence="${rev.id}">证据</button> <button data-run="${s.id}" ${isViewer?'disabled':''}>重算</button> <button data-withdraw="${s.id}" ${isAdmin?'':'disabled'}>主管撤回</button>${rev.verdict==='inconclusive'&&!rev.manual_override_by?` <button data-manual="${rev.id}" ${isAdmin?'':'disabled'}>人工复核</button>`:''}</td></tr>`;
   }).join('')}
   </tbody></table>
  </div>
 </section>
 <aside class="panel">
  <h2>受影响试验与阻断原因</h2>
  <p class="hint">源数据水位线版本：<strong>${store.impacts?.source_head??0}</strong>。撤回只让依赖它的审查失效；重算通过前拒绝复染签批、新建生产缸和未放行缸签放，已放行历史保留。</p>
  <h3>阻断中的复染试验（${store.impacts?.blocked_trials.length||0}）</h3>
  ${(store.impacts?.blocked_trials||[]).map(b=>`<article class="revision trial"><div class="code">TRIAL / ${String(b.trial_id).padStart(3,'0')} · ${escape(b.recipe_code||'')}</div>${b.reasons.map(x=>`<p class="hint">⛔ ${escape(x)}</p>`).join('')}</article>`).join('')||'<p class="hint">当前无阻断试验。</p>'}
  <h3>阻断中的生产缸（${store.impacts?.blocked_batches.length||0}）</h3>
  ${(store.impacts?.blocked_batches||[]).map(b=>`<article class="revision trial"><div class="code">${escape(b.code)} · ${escape(b.state)}</div>${b.reasons.map(x=>`<p class="hint">⛔ ${escape(x)}</p>`).join('')}</article>`).join('')||'<p class="hint">未放行缸无阻断；已放行历史不在此列。</p>'}
  <h3>已撤回失真染样（${withdrawn.size}）</h3>
  ${(store.impacts?.withdrawn||[]).map(w=>`<p class="hint">${escape(w.lot)} · ${escape(w.reason)}<br><small>${escape(w.by)}</small></p>`).join('')||'<p class="hint">暂无撤回记录。</p>'}
 </aside></div>
 <div id="evidence-panel" class="panel" style="display:none;margin-top:16px"></div>`;
}

function evidenceHtml(rev){
 const parts=(rev.evidence?.participants||[]).slice(0,12).map(p=>`<tr><td>${escape(p.lot)}</td><td>${escape(recipeOf(p.recipe_id)?.code||p.recipe_id)}</td><td>${decimal(p.distance,5)}</td></tr>`).join('');
 return `<h2>审查证据 #${rev.id} · ${escape(rev.evidence?.target_lot||'')} <span class="status ${verdictClass[rev.verdict]}">${REVIEW_VERDICTS[rev.verdict]}</span></h2>
 <p class="hint">参与样本 ${rev.participant_count} 张（已排除自身与撤回样本） · 源数据版本 ${rev.source_version} · 计算人 ${escape(rev.created_by)}</p>
 <p><strong>判定依据：</strong>${escape(rev.decision_basis)}</p>
 ${rev.superseded_reason?`<p class="hint">失效原因：${escape(rev.superseded_reason)}</p>`:''}
 ${rev.manual_override_note?`<p class="hint">人工复核：${escape(rev.manual_override_note)}</p>`:''}
 <table><thead><tr><th>参与染样</th><th>所属配方</th><th>光谱距离</th></tr></thead><tbody>${parts}</tbody></table>
 <p class="hint">仅展示距离最近的 12 条，完整参与样本与距离已随审查记录持久化。</p>`;
}

export function bind(rerender){
 const run=async ids=>{try{const r=await api('/swatch-reviews/run','POST',{swatch_ids:ids});await refresh();rerender();notify(`审查完成 ${r.length} 条：`+r.map(x=>REVIEW_VERDICTS[x.verdict]).join('、'));}catch(e){notify(e.message);}};
 document.querySelector('#run-all').onclick=()=>run(needReview.map(s=>s.id));
 document.querySelector('#rerun-all').onclick=()=>run(store.swatches.filter(s=>!s.withdrawn).map(s=>s.id));
 document.querySelectorAll('[data-run]').forEach(b=>b.onclick=()=>run([Number(b.dataset.run)]));
 document.querySelectorAll('[data-evidence]').forEach(b=>b.onclick=()=>{
   const rev=store.reviews.find(x=>x.id===Number(b.dataset.evidence));
   const panel=document.querySelector('#evidence-panel');panel.style.display='block';panel.innerHTML=evidenceHtml(rev);panel.scrollIntoView({behavior:'smooth'});
 });
 document.querySelectorAll('[data-withdraw]').forEach(b=>b.onclick=async()=>{
   if(b.disabled)return;const reason=prompt('请输入撤回该染样的依据（不少于 5 字）：');if(reason===null)return;
   try{const r=await api('/swatches/'+b.dataset.withdraw+'/withdraw','POST',{reason});await refresh();rerender();notify(`已撤回，${r.invalidated_reviews} 条依赖审查失效，源版本→${r.source_version_head}`);}catch(e){notify(e.message);}
 });
 document.querySelectorAll('[data-manual]').forEach(b=>b.onclick=async()=>{
   const note=prompt('人工复核说明（不少于 5 字）：');if(note===null)return;
   const accept=confirm('确定复核通过、确认该染样归属成立？\n（取消则按串样驳回）');
   try{await api('/swatch-reviews/'+b.dataset.manual+'/manual','POST',{note,accept});await refresh();rerender();notify('人工复核已记录');}catch(e){notify(e.message);}
 });
}
