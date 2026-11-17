from fastapi import APIRouter,Depends
from sqlalchemy import select
from .database import session
from .auth import current,editor,admin
from .models import Swatch
from .review_models import SwatchReview
from .review_schemas import ReviewRunInput,WithdrawInput,ManualReviewInput
from . import review_service as svc
router=APIRouter()

@router.get('/swatch-reviews')
def list_reviews(user=Depends(current),db=Depends(session)):
    return db.scalars(select(SwatchReview).order_by(SwatchReview.id.desc())).all()

@router.post('/swatch-reviews/run')
def run(data:ReviewRunInput,user=Depends(editor),db=Depends(session)):
    return svc.run_reviews(db,data.swatch_ids,user)

@router.post('/swatches/{key}/withdraw')
def withdraw(key:int,data:WithdrawInput,user=Depends(admin),db=Depends(session)):
    return svc.withdraw_swatch(db,key,data,user)

@router.post('/swatch-reviews/{key}/manual')
def manual(key:int,data:ManualReviewInput,user=Depends(admin),db=Depends(session)):
    return svc.manual_decide(db,key,data,user)

@router.get('/swatch-reviews/impacts')
def impacts(user=Depends(current),db=Depends(session)):
    return svc.impacts(db)
