from datetime import date
from src.fulfillment_models import DyeLot,DyeIssue,ColorDispatch,ShadeComplaint
import math,random
from sqlalchemy import select,func
from src.database import Base,engine,Session
from src.models import User,DyeRecipe,Swatch,Trial
from src.production_models import RecipeRevision,DyeBatch
from src.auth import hash_password

def seed():
    Base.metadata.create_all(engine)
    from src.schema_patch import ensure_columns
    ensure_columns()
    import src.review_models  # noqa: F401  确保新表注册到 metadata 后再 create_all
    Base.metadata.create_all(engine)
    with Session() as db:
        for role in ['admin','colorist','viewer']:
            email=f'{role}@qise.test'
            if not db.scalar(select(User).where(User.email==email)):db.add(User(email=email,password=hash_password('Dye2026!'),role=role))
        recipes=[('DY-021','靛蓝亚麻',1.8,.4,.2),('DY-022','苔绿棉麻',.3,1.7,.7),('DY-023','赤陶平纹',.8,.3,1.5)]
        for code,name,a,b,c in recipes:
            if not db.scalar(select(DyeRecipe).where(DyeRecipe.code==code)):db.add(DyeRecipe(code=code,name=name,dye_a=a,dye_b=b,dye_c=c))
        db.flush();rr=db.scalars(select(DyeRecipe).order_by(DyeRecipe.id)).all();rng=random.Random(42)
        for i in range(60):
            lot=['REF-021','SAMPLE-021','SAMPLE-OFF'][i] if i<3 else f'SW-{i:03}'
            if db.scalar(select(Swatch).where(Swatch.lot==lot)):continue
            group=0 if i<3 else i%3
            l,a,b=(48,-2,-25) if i==0 else (48.7,-1.5,-24.5) if i==1 else (62,8,-14) if i==2 else (48+group*9+rng.uniform(-2,2),-2+group*6+rng.uniform(-1,1),-25+group*15+rng.uniform(-1,1))
            spectrum=[round(min(.95,max(.03,.26+group*.11+.1*math.sin(j/5+group)+rng.gauss(0,.012))),5) for j in range(36)]
            db.add(Swatch(recipe_id=rr[group].id,lot=lot,spectrum=spectrum,l=l,a=a,b=b,measured=True))
        prod=db.scalar(select(DyeRecipe).where(DyeRecipe.code=='DY-PROD'))
        if not prod:
            prod=DyeRecipe(code='DY-PROD',name='量产靛蓝基准',dye_a=1.8,dye_b=.4,dye_c=.2,locked=True);db.add(prod);db.flush()
        for lot,l,a,b in [('PROD-REF',48,-2,-25),('PROD-OK',48.5,-1.8,-24.8)]:
            if not db.scalar(select(Swatch).where(Swatch.lot==lot)):db.add(Swatch(recipe_id=prod.id,lot=lot,spectrum=[.3]*36,l=l,a=a,b=b))
        db.flush();ref=db.scalar(select(Swatch).where(Swatch.lot=='PROD-REF'));candidate=db.scalar(select(Swatch).where(Swatch.lot=='PROD-OK'))
        trial=db.scalar(select(Trial).where(Trial.recipe_id==prod.id,Trial.state=='approved'))
        if not trial:
            trial=Trial(recipe_id=prod.id,reference_swatch_id=ref.id,candidate_swatch_id=candidate.id,delta_e=.574456,state='approved',note='量产演示基准');db.add(trial);db.flush()
        if not db.scalar(select(DyeBatch).where(DyeBatch.code=='DB-DEMO-001')):db.add(DyeBatch(code='DB-DEMO-001',approved_trial_id=trial.id,kg=250,target_snapshot={'lot':ref.lot,'recipe_id':prod.id,'l':ref.l,'a':ref.a,'b':ref.b,'trial_delta_e':trial.delta_e}))
        for code,component,kg,expiry,state in [('DYE-A-1117','A',80,date(2027,12,31),'active'),('DYE-B-1117','B',40,date(2027,12,31),'active'),('DYE-C-1117','C',20,date(2027,12,31),'active'),('DYE-C-HOLD','C',5,date(2027,12,31),'quarantine'),('DYE-B-OLD','B',5,date(2026,1,1),'active')]:
            if not db.scalar(select(DyeLot).where(DyeLot.code==code)):db.add(DyeLot(code=code,component=component,available_kg=kg,expires_on=expiry,state=state))
        db.flush()
        # 串样演示：SAMPLE-MIS 实测色差合格（与 REF-021 ΔE≈0.995），但光谱来自苔绿配方群落，
        # 贴在靛蓝 DY-021 名下。光谱串样审查应判 mismatch，即使色差门限通过也拒绝签批。
        mis=db.scalar(select(Swatch).where(Swatch.lot=='SAMPLE-MIS'))
        if not mis:
            greenlike=[round(min(.95,max(.03,.26+1*.11+.1*math.sin(j/5+1)+rng.gauss(0,.006))),5) for j in range(36)]
            mis=Swatch(recipe_id=rr[0].id,lot='SAMPLE-MIS',spectrum=greenlike,l=48.7,a=-1.5,b=-24.5,measured=True)
            db.add(mis);db.flush()
        ref021=db.scalar(select(Swatch).where(Swatch.lot=='REF-021'))
        mis_trial=db.scalar(select(Trial).where(Trial.reference_swatch_id==ref021.id,Trial.candidate_swatch_id==mis.id))
        if not mis_trial:
            de=sum((getattr(ref021,k)-getattr(mis,k))**2 for k in ['l','a','b'])**.5
            db.add(Trial(recipe_id=rr[0].id,reference_swatch_id=ref021.id,candidate_swatch_id=mis.id,delta_e=de,state='draft',note='色差合格但疑似贴错配方的串样演示'))
        # 预生成光谱串样审查证据（幂等：仅补缺，不覆盖人工撤回/重算结果）
        from src.review_models import SwatchReview
        from src.spectral import review_swatch
        from src.models import SourceVersion
        if not db.scalar(select(SourceVersion).where(SourceVersion.id==1)):
            db.add(SourceVersion(id=1,version=1,note='seed 初始水位线'))
        valid=[s for s in db.scalars(select(Swatch).where(Swatch.measured==True,Swatch.withdrawn==False)).all()]
        for target in valid:
            if db.scalar(select(SwatchReview).where(SwatchReview.swatch_id==target.id,SwatchReview.state=='current')):continue
            participants=[{'id':s.id,'lot':s.lot,'recipe_id':s.recipe_id,'spectrum':s.spectrum} for s in valid if s.id!=target.id]
            outcome=review_swatch({'id':target.id,'lot':target.lot,'recipe_id':target.recipe_id,'spectrum':target.spectrum},participants,target.recipe_id)
            recipe_map={r.id:r for r in rr}
            nearest=outcome['nearest']
            db.add(SwatchReview(swatch_id=target.id,verdict=outcome['verdict'],expected_recipe_id=target.recipe_id,
                                nearest_recipe_id=nearest['recipe_id'] if nearest else None,
                                evidence={'target_lot':target.lot,'expected_recipe_code':recipe_map.get(target.recipe_id).code if target.recipe_id in recipe_map else None,
                                          'participants':outcome['participants'],'recipe_best':outcome['recipe_best'],'nearest':nearest},
                                participant_count=outcome['participant_count'],nearest_distance=nearest['distance'] if nearest else None,
                                decision_basis=outcome['decision_basis'],source_version=target.source_version,state='current',created_by='seed@qise.test'))
        db.commit()
        print({name:db.scalar(select(func.count()).select_from(model)) for name,model in [('users',User),('recipes',DyeRecipe),('swatches',Swatch)]})
if __name__=='__main__':seed()
