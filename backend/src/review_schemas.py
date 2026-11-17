from typing import Literal
from pydantic import BaseModel,Field,ConfigDict,field_validator

class ReviewInputs(BaseModel):
    model_config=ConfigDict(allow_inf_nan=False)
    @field_validator('*',mode='before')
    @classmethod
    def trim(cls,v):
        if isinstance(v,str):return v.strip()
        return v

class ReviewRunInput(ReviewInputs):
    # 为空时审查所有缺有效结论（含失效后需重算）的染样
    swatch_ids:list[int]=Field(default_factory=list,max_length=100)

class WithdrawInput(ReviewInputs):
    reason:str=Field(min_length=5,max_length=300)

class ManualReviewInput(ReviewInputs):
    note:str=Field(min_length=5,max_length=300)
    accept:bool
