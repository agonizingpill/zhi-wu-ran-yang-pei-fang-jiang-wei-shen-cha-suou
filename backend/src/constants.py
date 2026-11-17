from enum import StrEnum
class Role(StrEnum):
    ADMIN='admin'
    COLORIST='colorist'
    VIEWER='viewer'
class TrialState(StrEnum):
    DRAFT='draft'
    VERIFIED='verified'
    APPROVED='approved'
    REJECTED='rejected'
class ReviewVerdict(StrEnum):
    MATCH='match'              # 近邻配方与登记配方一致，归属成立
    MISMATCH='mismatch'        # 近邻配方不同，判定串样
    INCONCLUSIVE='inconclusive'  # 证据不足，转待复核
class ReviewState(StrEnum):
    CURRENT='current'          # 依据当前源数据有效
    SUPERSEDED='superseded'    # 源数据更新后失效（依赖撤回或样本源变更）
# 审查证据门限：参与染样（排除自身、排除撤回）少于该数即证据不足
MIN_PARTICIPANTS=3
# 近邻归属置信边：期望配方最优距离须不劣于非期望配方最优距离的该倍数，否则待复核
NEAR_MARGIN=1.15
# 色差门限继续沿用既有工艺规则，不被光谱审查替代
DELTA_E_LIMIT=3.0
