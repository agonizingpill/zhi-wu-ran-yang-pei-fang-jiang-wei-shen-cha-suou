from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from .models import Swatch,Trial,DyeRecipe,SourceVersion
from .review_models import SwatchReview
from .spectral import review_swatch
from .recipe_service import log

def bump_source(db,note):
    """源数据水位线单调递增；只用于留痕与裁决先后，不参与业务外键。"""
    row=db.scalar(select(SourceVersion).where(SourceVersion.id==1).with_for_update())
    if not row:
        row=SourceVersion(id=1,version=1,note=note);db.add(row)
    else:
        row.version=row.version+1;row.note=note
    db.flush();return row.version

def _lock_swatches(db,swatch_ids):
    if not swatch_ids:return {}
    rows=db.scalars(select(Swatch).where(Swatch.id.in_(swatch_ids)).order_by(Swatch.id).with_for_update()).all()
    return {s.id:s for s in rows}

def _invalidate_for(db,swatch_id,reason):
    """依赖该染样的审查全部失效：以被审查者或以参与样本身份依赖都算。"""
    reviews=db.scalars(select(SwatchReview).where(SwatchReview.state=='current')).all()
    changed=0
    for review in reviews:
        depends=review.swatch_id==swatch_id or any(p.get('swatch_id')==swatch_id for p in review.evidence.get('participants',[]))
        if depends:
            review.state='superseded';review.superseded_reason=reason;changed+=1
    return changed

def run_reviews(db,swatch_ids,user):
    ids=sorted(set(swatch_ids)) if swatch_ids else list(db.scalars(select(Swatch.id)).all())
    if not ids:raise HTTPException(409,'暂无染样可审查')
    targets=_lock_swatches(db,ids)
    if len(targets)!=len(ids):raise HTTPException(404,'部分染样不存在')
    # 有效参与样本：measured、未撤回；被审查者自身在每个子计算中再排除
    pool=db.scalars(select(Swatch).where(Swatch.measured==True,Swatch.withdrawn==False)).all()
    recipes={r.id:r for r in db.scalars(select(DyeRecipe)).all()}
    results=[]
    for swatch_id in ids:
        target=targets[swatch_id]
        if target.withdrawn:raise HTTPException(409,f'染样 {target.lot} 已撤回标记失真，不能再审查')
        expected=target.recipe_id
        participants=[{'id':s.id,'lot':s.lot,'recipe_id':s.recipe_id,'spectrum':s.spectrum}
                      for s in pool if s.id!=target.id]
        outcome=review_swatch({'id':target.id,'lot':target.lot,'recipe_id':expected,'spectrum':target.spectrum},
                              participants,expected)
        old=db.scalar(select(SwatchReview).where(SwatchReview.swatch_id==target.id,SwatchReview.state=='current').with_for_update())
        # 写入前再次核对源版本：排队中的旧计算在落库瞬间必须让位于更新后的源数据
        if old and old.source_version!=target.source_version:
            old.state='superseded';old.superseded_reason='落库前源数据已更新，旧计算结论作废'
            old=None
        if old:
            old.state='superseded';old.superseded_reason='发起重算，旧结论归档'
        nearest=outcome['nearest']
        review=SwatchReview(
            swatch_id=target.id,verdict=outcome['verdict'],expected_recipe_id=expected,
            nearest_recipe_id=nearest['recipe_id'] if nearest else None,
            evidence={'target_lot':target.lot,'expected_recipe_code':recipes.get(expected).code if expected in recipes else None,
                      'participants':outcome['participants'],'recipe_best':outcome['recipe_best'],
                      'nearest':nearest},
            participant_count=outcome['participant_count'],
            nearest_distance=nearest['distance'] if nearest else None,
            decision_basis=outcome['decision_basis'],
            source_version=target.source_version,state='current',created_by=user.email)
        db.add(review);db.flush()
        results.append(review)
    log(db,user,f'光谱串样审查 {len(results)} 张：'+','.join(f"{r.evidence['target_lot']}={r.verdict}" for r in results))
    db.commit()
    return results

def withdraw_swatch(db,key,data,user):
    target=db.scalar(select(Swatch).where(Swatch.id==key).with_for_update())
    if not target:raise HTTPException(404,'染样不存在')
    if target.withdrawn:raise HTTPException(409,'该染样已撤回，不能重复撤回')
    target.withdrawn=True;target.withdrawn_by=user.email;target.withdraw_reason=data.reason
    target.withdrawn_at=datetime.utcnow()
    target.source_version=target.source_version+1;target.source_updated_at=datetime.utcnow()
    invalidated=_invalidate_for(db,target.id,f'依赖染样 {target.lot} 被主管撤回（{data.reason}）')
    version=bump_source(db,f'撤回染样 {target.lot}，{invalidated} 条审查失效')
    log(db,user,f'撤回失真染样 {target.lot}：{data.reason}；源版本→{version}，失效审查 {invalidated} 条')
    db.commit()
    return {'swatch_id':target.id,'lot':target.lot,'source_version':target.source_version,
            'invalidated_reviews':invalidated,'source_version_head':version}

def manual_decide(db,key,data,user):
    review=db.scalar(select(SwatchReview).where(SwatchReview.id==key).with_for_update())
    if not review:raise HTTPException(404,'审查记录不存在')
    if review.state!='current':raise HTTPException(409,'该审查结论已失效，请重算后再复核')
    if review.verdict!='inconclusive':raise HTTPException(409,'仅证据不足（待复核）结论需要主管人工复核')
    if review.manual_override_by:raise HTTPException(409,'该待复核结论已人工裁决，不能重复执行')
    target=db.get(Swatch,review.swatch_id)
    if target.withdrawn or target.source_version!=review.source_version:
        review.state='superseded';review.superseded_reason='人工复核前源数据已变化，旧结论作废'
        db.commit();raise HTTPException(409,'源数据已更新，旧审查失效，请重新发起审查')
    review.manual_override_by=user.email;review.manual_override_note=(('复核通过：' if data.accept else '复核驳回：')+data.note)
    if not data.accept:
        review.verdict='mismatch';review.decision_basis=review.decision_basis+'；主管人工复核驳回，按串样处理'
    else:
        review.decision_basis=review.decision_basis+'；主管人工复核通过，归属成立可签批'
    log(db,user,f'主管人工复核审查 {key} → {review.verdict}')
    db.commit();return review

def current_review(db,swatch_id):
    return db.scalar(select(SwatchReview).where(SwatchReview.swatch_id==swatch_id,SwatchReview.state=='current'))

def swatch_gate(db,swatch_id,label='候选染样'):
    """签批闸门：撤回、无有效审查、串样、待复核均拒绝；色差门限由试验流程另行执行。"""
    swatch=db.get(Swatch,swatch_id)
    if not swatch:raise HTTPException(409,f'{label}不存在')
    if swatch.withdrawn:raise HTTPException(409,f'{label} {swatch.lot} 已被主管撤回标记失真，重算通过前拒绝签批')
    review=current_review(db,swatch_id)
    if not review:raise HTTPException(409,f'{label} {swatch.lot} 尚无光谱串样审查，请先发起审查')
    if review.source_version!=swatch.source_version:
        raise HTTPException(409,f'{label} {swatch.lot} 的审查依据已过期（源数据更新），请重新审查')
    if review.verdict=='mismatch':
        raise HTTPException(409,f'{label} {swatch.lot} 光谱串样审查判定串样（近邻配方 {review.nearest_recipe_id}），拒绝签批')
    if review.verdict=='inconclusive':
        raise HTTPException(409,f'{label} {swatch.lot} 审查证据不足处于待复核，需主管人工复核后再签批')
    return review

def trial_blockers(db,trial):
    """返回试验当前的阻断原因列表（空列表即放行；不含色差门限以外的历史保留判断）。"""
    reasons=[]
    for swatch_id,label in [(trial.candidate_swatch_id,'候选染样'),(trial.reference_swatch_id,'目标染样')]:
        swatch=db.get(Swatch,swatch_id)
        if not swatch:
            reasons.append(f'{label}不存在');continue
        if swatch.withdrawn:reasons.append(f'{label} {swatch.lot} 已撤回标记失真')
        review=current_review(db,swatch_id)
        if not review:reasons.append(f'{label} {swatch.lot} 缺少光谱串样审查')
        elif review.source_version!=swatch.source_version:reasons.append(f'{label} {swatch.lot} 审查因源数据更新失效，待重算')
        elif review.verdict=='mismatch':reasons.append(f'{label} {swatch.lot} 审查判定串样')
        elif review.verdict=='inconclusive':reasons.append(f'{label} {swatch.lot} 审查证据不足待复核')
    return reasons

def batch_blockers(db,batch):
    """未放行缸次：沿用其来源试验的阻断原因；已放行历史缸次永不阻断（历史保留）。"""
    if batch.state=='released':return []
    trial=db.get(Trial,batch.approved_trial_id)
    if not trial:return ['来源复染试验不存在']
    return trial_blockers(db,trial)

def impacts(db):
    # 含已批准试验：批准后撤回/失效会阻断新建生产缸，同样属于受影响试验
    trials=db.scalars(select(Trial).order_by(Trial.id)).all()
    trial_rows=[]
    for trial in trials:
        reasons=trial_blockers(db,trial)
        if reasons:
            recipe=db.get(DyeRecipe,trial.recipe_id)
            trial_rows.append({'trial_id':trial.id,'state':trial.state,'recipe_code':recipe.code if recipe else None,
                               'reasons':reasons})
    from .production_models import DyeBatch
    batches=db.scalars(select(DyeBatch).order_by(DyeBatch.id)).all()
    batch_rows=[]
    for batch in batches:
        reasons=batch_blockers(db,batch)
        if reasons:
            batch_rows.append({'batch_id':batch.id,'code':batch.code,'state':batch.state,'reasons':reasons})
    withdrawn=db.scalars(select(Swatch).where(Swatch.withdrawn==True).order_by(Swatch.id)).all()
    return {'source_head':db.scalar(select(SourceVersion.version).where(SourceVersion.id==1)) or 0,
            'withdrawn':[{'id':s.id,'lot':s.lot,'reason':s.withdraw_reason,'by':s.withdrawn_by} for s in withdrawn],
            'blocked_trials':trial_rows,'blocked_batches':batch_rows}
