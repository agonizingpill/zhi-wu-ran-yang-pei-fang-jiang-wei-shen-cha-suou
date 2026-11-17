"""光谱串样审查的纯计算部分。

用其余有效染样（排除被审查染样自身、排除已撤回染样）的 36 波段反射率，
按欧氏距离（与 PCA 同构的波段空间距离，取均方根使量纲回到反射率）找近邻，
以近邻染样所属配方判断被审查染样的配方归属。本模块不触碰数据库，便于单测。
"""
import math
from .constants import MIN_PARTICIPANTS,NEAR_MARGIN

def spectral_distance(left,right):
    if len(left)!=len(right):
        raise ValueError('光谱波段数不一致，无法比较')
    total=sum((float(x)-float(y))**2 for x,y in zip(left,right))
    return math.sqrt(total/len(left))

def review_swatch(target,participants,expected_recipe_id):
    """target: 被审查染样 dict（id/lot/recipe_id/spectrum）。
    participants: 其余有效染样 dict 列表（已由服务层排除自身与撤回样本）。
    返回 verdict、参与样本、逐样本距离、近邻与判定依据。"""
    distances=[]
    for sample in participants:
        distance=spectral_distance(target['spectrum'],sample['spectrum'])
        distances.append({'swatch_id':sample['id'],'lot':sample['lot'],'recipe_id':sample['recipe_id'],
                          'distance':round(distance,6)})
    distances.sort(key=lambda item:item['distance'])
    recipe_best={}
    for item in distances:
        recipe_best.setdefault(item['recipe_id'],item['distance'])
    nearest=distances[0] if distances else None
    basis=[]
    if len(distances)<MIN_PARTICIPANTS:
        verdict='inconclusive'
        basis.append(f'参与样本仅 {len(distances)} 张（要求不少于 {MIN_PARTICIPANTS} 张），证据不足转待复核')
    else:
        same_recipe=[d for d in distances if d['recipe_id']==expected_recipe_id]
        other=[d for d in distances if d['recipe_id']!=expected_recipe_id]
        if not same_recipe:
            verdict='inconclusive'
            basis.append('其余有效染样中没有与登记配方同配方的样本，无法佐证归属，转待复核')
        else:
            best_same=min(same_recipe,key=lambda d:d['distance'])
            best_other=min(other,key=lambda d:d['distance']) if other else None
            basis.append(f"登记配方最近邻 {best_same['lot']} 距离 {best_same['distance']:.6f}")
            if best_other is None:
                verdict='match'
                basis.append('不存在其他配方的有效样本，近邻归属为登记配方')
            else:
                basis.append(f"他配方最近邻 {best_other['lot']} 距离 {best_other['distance']:.6f}，置信边 {NEAR_MARGIN}")
                if best_same['distance']<=best_other['distance']:
                    verdict='match'
                    basis.append('登记配方近邻距离不大于他配方，归属成立')
                elif best_other['distance']<best_same['distance']/NEAR_MARGIN:
                    verdict='mismatch'
                    basis.append('他配方近邻显著更近（超过置信边），判定串样')
                else:
                    verdict='inconclusive'
                    basis.append('两配方距离接近、未超过置信边，证据不足转待复核')
    return {'verdict':verdict,'participants':distances,'participant_count':len(distances),
            'nearest':nearest,'recipe_best':[{'recipe_id':rid,'distance':round(d,6)} for rid,d in sorted(recipe_best.items(),key=lambda kv:kv[1])],
            'decision_basis':'；'.join(basis)}
