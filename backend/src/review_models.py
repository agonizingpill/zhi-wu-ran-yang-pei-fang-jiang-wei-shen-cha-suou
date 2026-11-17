from sqlalchemy import String,Float,Integer,ForeignKey,JSON,CheckConstraint,DateTime,func,Text
from sqlalchemy.orm import Mapped,mapped_column
from .database import Base

class SwatchReview(Base):
    """光谱串样审查结论。一次审查一行；重算产生新行，旧行置 superseded 留痕。"""
    __tablename__='swatch_reviews'
    __table_args__=(
        CheckConstraint("state IN ('current','superseded')"),
        CheckConstraint("verdict IN ('match','mismatch','inconclusive')"),
    )
    id:Mapped[int]=mapped_column(primary_key=True)
    swatch_id:Mapped[int]=mapped_column(ForeignKey('swatches.id'),index=True)
    verdict:Mapped[str]=mapped_column(String(20))
    expected_recipe_id:Mapped[int]=mapped_column(ForeignKey('dye_recipes.id'))
    nearest_recipe_id:Mapped[int|None]=mapped_column(ForeignKey('dye_recipes.id'),nullable=True)
    # 参与样本（排除自身、排除已撤回）、逐样本距离与判定依据全部落库
    evidence:Mapped[dict]=mapped_column(JSON)
    participant_count:Mapped[int]=mapped_column(Integer,default=0)
    nearest_distance:Mapped[float|None]=mapped_column(Float,nullable=True)
    decision_basis:Mapped[str]=mapped_column(Text,default='')
    # 计算所依据的源数据版本；写入时与当前版本不一致即拒绝落库，防止排队旧计算复活结论
    source_version:Mapped[int]=mapped_column(Integer)
    state:Mapped[str]=mapped_column(String(20),default='current')
    created_by:Mapped[str]=mapped_column(String(120),default='')
    superseded_reason:Mapped[str]=mapped_column(String(240),default='')
    # 证据不足（待复核）时主管人工复核留痕；复核通过后该结论可作为签批依据
    manual_override_by:Mapped[str]=mapped_column(String(120),default='')
    manual_override_note:Mapped[str]=mapped_column(String(300),default='')
    created_at:Mapped[object]=mapped_column(DateTime,server_default=func.now())
