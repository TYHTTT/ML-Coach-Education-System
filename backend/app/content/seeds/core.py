"""Versioned project-authored lessons and worked examples.

Example arithmetic is checked with a finite catalogue of trusted calculations.
"""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any


ORIGIN = "instructor_authored"
AUTHOR_LABEL = "项目自编教学示例"


def calculate(kind: str, a: list[Any]) -> Any:
    """Only fixed, trusted calculations used by these seed fixtures."""
    if kind == "linear":
        return a[0] * a[1] + a[2]
    if kind == "sum":
        return sum(a)
    if kind == "length":
        return len(a[0])
    if kind == "at":
        return a[0][a[1]]
    if kind == "count_nonzero":
        return sum(x != 0 for x in a[0])
    if kind == "count_equal":
        return sum(x == a[1] for x in a[0])
    if kind == "count_at_least":
        return sum(x >= a[1] for x in a[0])
    if kind == "max_abs":
        return max(abs(x) for x in a[0])
    if kind == "minimum":
        return min(a[0])
    if kind == "count_outside_unit_interval":
        return sum(not 0 <= x <= 1 for x in a[0])
    if kind == "second_moment":
        return a[0] ** 2 + a[1]
    if kind == "reciprocal_quadratic_derivative":
        return -2 * a[0] / (1 + a[0] ** 2) ** 2
    if kind == "product":
        return math.prod(a)
    if kind == "ratio":
        return a[0] / a[1]
    if kind == "power":
        return a[0] ** a[1]
    if kind == "log":
        return math.log(a[0]) if len(a) == 1 else math.log(a[0], a[1])
    if kind == "exp":
        return math.exp(a[0])
    if kind == "dot":
        return sum(x * y for x, y in zip(a[0], a[1], strict=True))
    if kind == "norm":
        return math.sqrt(sum(x * x for x in a))
    if kind == "vector_add":
        return [x + y for x, y in zip(a[0], a[1], strict=True)]
    if kind == "matrix_product":
        return [[sum(x * y for x, y in zip(row, col, strict=True))
                 for col in zip(*a[1], strict=True)] for row in a[0]]
    if kind == "mean":
        return sum(a) / len(a)
    if kind == "variance":
        mu = sum(a) / len(a)
        return sum((x - mu) ** 2 for x in a) / len(a)
    if kind == "expectation":
        return sum(x * p for x, p in zip(a[0], a[1], strict=True))
    if kind == "discrete_variance":
        mu = calculate("expectation", a)
        return sum((x - mu) ** 2 * p for x, p in zip(a[0], a[1], strict=True))
    if kind == "bernoulli_variance":
        return a[0] * (1 - a[0])
    if kind == "binomial":
        n, k, p = a
        return math.comb(n, k) * p ** k * (1 - p) ** (n - k)
    if kind == "power_derivative":
        coefficient, power, x = a
        return coefficient * power * x ** (power - 1)
    if kind == "polynomial_derivative":
        coefficients, x = a
        return sum(i * c * x ** (i - 1) for i, c in enumerate(coefficients) if i)
    if kind == "chain_power":
        outer_power, inner_slope, inner_offset, x = a
        return outer_power * (inner_slope * x + inner_offset) ** (outer_power - 1) * inner_slope
    if kind == "quadratic_gradient":
        cx, cy, x, y = a
        return [2 * cx * x, 2 * cy * y]
    if kind == "cross_partial":
        x, y = a
        return [2 * x * y + 1, x * x]
    if kind == "sigmoid":
        return 1 / (1 + math.exp(-a[0]))
    if kind == "sigmoid_derivative":
        p = calculate("sigmoid", a)
        return p * (1 - p)
    if kind == "cross_entropy":
        y, p = a
        return -(y * math.log(p) + (1 - y) * math.log(1 - p))
    if kind == "binary_entropy":
        p = a[0]
        return -(p * math.log(p) + (1 - p) * math.log(1 - p))
    if kind == "linear_loss":
        xs, ys, w, b = a
        return sum((w * x + b - y) ** 2 for x, y in zip(xs, ys, strict=True)) / (2 * len(xs))
    if kind == "linear_gradients":
        xs, ys, w, b = a
        residuals = [w * x + b - y for x, y in zip(xs, ys, strict=True)]
        return [sum(r * x for r, x in zip(residuals, xs, strict=True)) / len(xs), sum(residuals) / len(xs)]
    if kind == "gradient_step":
        return a[0] - a[1] * a[2]
    if kind == "finite_difference_square":
        x, h = a
        return ((x + h) ** 2 - x * x) / h
    if kind == "quadratic_value":
        cx, cy, x, y = a
        return cx * x * x + cy * y * y
    if kind == "component":
        operation, arguments, index = a
        return calculate(operation, arguments)[index]
    if kind == "squared_distance":
        return sum((x - y) ** 2 for x, y in zip(a[0], a[1], strict=True))
    if kind == "log_odds":
        return math.log(a[0] / (1 - a[0]))
    if kind == "odds":
        return a[0] / (1 - a[0])
    raise ValueError(f"Unregistered trusted calculation: {kind}")


def E(name: str, family: str, title: str, problem: str, givens: dict,
      target: str, steps: list[tuple[str, str, str, str, str]],
      answer: str, checks: list[tuple[str, list[Any], Any]], mistakes: list[str]) -> dict:
    return dict(name=name, family=family, title=title, problem=problem,
                givens=givens, target=target, steps=steps, answer=answer,
                checks=checks, mistakes=mistakes)


def T(title: str, objectives: list[str], prerequisites: str, problem: str,
      concepts: list[str], formulas: list[tuple[str, str, str]], summary: str,
      examples: list[dict]) -> dict:
    return dict(title=title, objectives=objectives, prerequisites=prerequisites,
                problem=problem, concepts=concepts, formulas=formulas, summary=summary,
                examples=examples)


TOPICS: dict[str, dict] = {
    "la.vectors": T(
        "标量、向量与矩阵：把样本写成有形状的数据",
        ["将两个特征按固定顺序组成向量", "区分样本数、特征数和向量分量", "完成向量加法并检查形状"],
        "只需实数四则运算；特征必须采用一致顺序和单位。",
        "两位学生的学习时长和练习数分别是 (2, 5)、(3, 4)，怎样保存它们并计算合计？",
        ["标量是一个数；向量是按顺序排列的数，分量顺序有含义。", "本课默认样本向量为列向量，两个特征的形状为 2×1。", "数据矩阵按行放样本：n 个样本、d 个特征形成 n×d 的 X。"],
        [("u+v=(u_1+v_1,u_2+v_2)", "u、v 是同维向量；下标标识同一种特征", "只有同维且对应特征单位一致时可相加"),
         ("X\\in\\mathbb R^{n\\times d}", "n 为样本数，d 为特征数", "每个样本具有相同特征定义与顺序")],
        "先写出形状和分量含义，再做逐分量运算；向量长度是分量个数，不是分量之和。",
        [E("feature_addition", "vector.component-addition", "两个特征向量相加", "u=(2,5)，v=(3,4)，求 u+v。", {"u":[2,5],"v":[3,4]}, "合计向量及其形状",
           [("对齐含义","u,v∈R²","时长对应时长，练习数对应练习数","形状均为 2×1","向量相加要求对应分量有一致含义。"),
            ("逐项相加","u+v=(u₁+v₁,u₂+v₂)","(2+3,5+4)","(5,9)","不能把两个向量所有分量合并成一个标量。"),
            ("解释与校验","(u+v)-v=u","(5-3,9-4)","(2,5)","用逆运算恢复原向量检验结果。")],
           "u+v=(5,9)，形状 2×1。", [("vector_add",[[2,5],[3,4]],[5,9])], ["把向量维数误认为分量的和", "交换特征顺序后直接相加"]),
         E("scalar_change", "vector.scalar-scaling", "单位换算是整体缩放", "位移向量 v=(0.5,-1.2) 米，换算成厘米。", {"v_m":[0.5,-1.2],"cm_per_m":100}, "厘米表示的向量",
           [("确定换算因子","1 m=100 cm","两个分量均乘 100","缩放系数为 100","同一单位换算应用到每一个分量。"),
            ("分别计算","100v=(100v₁,100v₂)","(100×0.5,100×(-1.2))","(50,-120)","负号表示方向，换单位不改变方向。"),
            ("检验量纲","v_cm/100=v_m","(50/100,-120/100)","(0.5,-1.2) m","换回米后与原数据一致。")],
           "(50,-120) cm。", [("product",[100,0.5],50),("product",[100,-1.2],-120)], ["只缩放第一个分量", "将负方向误改为正方向"])]),
    "la.dot_product": T(
        "向量内积与线性模型分数",
        ["逐项相乘并求和计算内积", "区分内积标量与逐分量乘积", "将内积、偏置和 Sigmoid 串成一次预测"],
        "需要向量分量与固定特征顺序；概率解释是本例的模型约定。",
        "特征 x=(2,1)，权重 w=(0.5,-1)，偏置 b=0.5，模型怎样得到一个预测概率？",
        ["内积将两个同维向量映射成一个标量。", "线性得分 z=wᵀx+b 可以是任意实数，不自动是概率。", "在二分类模型中，Sigmoid 将得分映射到 (0,1)，供指定正类的条件概率解释。"],
        [("w^Tx=\\sum_{j=1}^d w_jx_j", "w、x 形状 d×1，wᵀ 为 1×d，结果 1×1", "两向量同维且特征顺序一致"),
         ("p=1/(1+e^{-z}),\\quad z=w^Tx+b", "b 是标量偏置，p 是正类概率预测", "这里只演示固定模型的前向计算，不表示已校准")],
        "先乘后加得到一个标量；加偏置得到得分，经过链接函数后才得到概率预测。",
        [E("C_dot_sigmoid", "prediction.dot-bias-sigmoid", "例题 C：从向量内积到概率", "x=(2,1)，w=(0.5,-1)，b=0.5，计算 z 和 sigmoid(z)。", {"x":[2,1],"w":[0.5,-1],"b":0.5}, "线性得分与二分类概率",
           [("逐项相乘","wᵀx=w₁x₁+w₂x₂","0.5×2+(-1)×1","1-1=0","同一位置的权重乘对应特征。"),
            ("加上偏置","z=wᵀx+b","0+0.5","z=0.5","偏置在求和之后只加一次。"),
            ("计算非线性输出","σ(z)=1/(1+e⁻ᶻ)","1/(1+e⁻⁰·⁵)","p≈0.622459","指数函数将任意实数得分映射到正概率范围。"),
            ("解释模型输出","p=P(Y=1|x;w,b)","以 0.5 为分类阈值","本例预测正类","这是模型给定特征后的概率预测，不是样本真实标签的证明。")],
           "z=0.5，sigmoid(z)≈0.622459。", [("dot",[[2,1],[0.5,-1]],0),("linear",[1,0,0.5],0.5),("sigmoid",[0.5],0.6224593312018546)], ["遗漏负权重", "将 z=0.5 直接当作概率"]),
         E("orthogonal", "dot.orthogonality-calculation", "通过内积检查直角", "u=(1,2)，v=(2,-1)，用内积判断是否正交。", {"u":[1,2],"v":[2,-1]}, "内积及正交判断",
           [("检查形状","u,v∈R²","两个分量分别对应","可以计算内积","同维是内积定义的前提。"),
            ("求内积","uᵀv=1×2+2×(-1)","2-2","0","正负乘积在求和时相互抵消。"),
            ("应用正交条件","uᵀv=0","u、v 均非零","两向量夹角为 90°","欧氏内积下非零向量内积为零意味着正交。")],
           "uᵀv=0，两非零向量正交。", [("dot",[[1,2],[2,-1]],0)], ["把逐分量乘积 (2,-2) 当最终内积", "忽略欧氏内积和非零向量条件"])]),
    "math.functions": T(
        "函数与变量：从输入得到唯一输出",
        ["区分自变量、参数和输出", "代入一次函数完成预测", "根据运算限制确定定义域"],
        "使用实数算术；定义域、值域和单位在具体问题中明确。",
        "出租车费用模型 f(x)=3x+10，x 表示公里数；行驶 4 公里时如何计算费用？",
        ["函数把定义域中的每个输入映射到唯一输出，不要求不同输入有不同输出。", "x 是本次输入；3 与 10 是固定参数，换模型时参数才改变。", "分式的分母不能为零；实数平方根内部须非负；应用定义域还可能要求 x≥0。"],
        [("f(x)=ax+b", "x 为输入，a 为每单位变化量，b 为 x=0 时的输出", "a、b 固定，x 在约定定义域内"),
         ("(f\\circ g)(x)=f(g(x))", "先计算内层 g，再把结果作为 f 的输入", "g(x) 必须位于 f 的定义域")],
        "明确哪些量固定、哪些量变化；代入前先检查定义域，再检查输出的单位。",
        [E("fare", "function.affine-evaluation", "计算费用函数", "f(x)=3x+10 元，x≥0，求行驶 4 公里的费用。", {"a":3,"b":10,"x":4}, "费用 f(4)",
           [("确认输入","x=4 km","4≥0","输入在定义域内","实际里程不能为负。"),
            ("代入函数","f(4)=3×4+10","12+10","22 元","先乘法后加固定起步费。"),
            ("解释参数","f(0)=10","3 元/km 与 4 km 相乘","里程费 12 元，起步费 10 元","量纲合并后均为元。")],
           "f(4)=22 元。", [("linear",[3,4,10],22)], ["把起步费乘以里程", "把参数 a 当成输入 x"]),
         E("composition", "function.composition-evaluation", "顺序执行两个函数", "g(x)=x+1，f(t)=t²，求 f(g(2))。", {"x":2,"g":"x+1","f":"t²"}, "复合函数输出",
           [("先算内层","g(2)=2+1","2+1","3","括号表示 g 的结果先产生。"),
            ("再算外层","f(g(2))=f(3)","3²","9","把内层输出整体作为外层输入。"),
            ("对照逆序","g(f(2))=g(4)","4+1","5，与 9 不同","函数复合通常不满足交换律。")],
           "f(g(2))=9；逆序 g(f(2))=5。", [("power",[3,2],9),("linear",[1,4,1],5)], ["把 f(g(x)) 当成 f(x)g(x)", "交换函数执行顺序"])]),
}


from .machine_learning import authored as _machine_learning
from .calculus import authored as _calculus
from .probability import authored as _probability
from .algebra import authored as _algebra

for authored in (_machine_learning, _calculus, _probability, _algebra):
    TOPICS.update(authored(T, E))


def build_content() -> dict[str, list[dict]]:
    """Return fresh content objects; repeated calls have identical output."""
    lessons, examples = [], []
    for topic_id, spec in TOPICS.items():
        example_ids = [f"example.{topic_id}.{e['name']}" for e in spec["examples"]]
        lessons.append(dict(id="lesson."+topic_id, topic_id=topic_id, title=spec["title"],
            learning_objectives=deepcopy(spec["objectives"]), prerequisite_summary=spec["prerequisites"],
            motivating_problem=spec["problem"], key_concepts=deepcopy(spec["concepts"]),
            formulas=[{"expression":f,"symbols":s,"conditions":c} for f,s,c in spec["formulas"]],
            worked_example_ids=example_ids, practice_recommendations=[],
            summary=spec["summary"], source_refs=[], content_origin=ORIGIN,
            version=2, status="published"))
        for example_id, e in zip(example_ids, spec["examples"], strict=True):
            steps = [{"step_id":f"step-{i}","title":title,"formula":formula,
                      "substitution":substitution,"result":result,"explanation":explanation,
                      "justification":explanation}
                     for i,(title,formula,substitution,result,explanation) in enumerate(e["steps"],1)]
            examples.append(dict(id=example_id, topic_id=topic_id, title=e["title"], difficulty="medium",
                problem=e["problem"], givens=deepcopy(e["givens"]), target=e["target"],
                solution_outline=" → ".join(s["title"] for s in steps), steps=steps,
                final_answer=e["answer"], verification={"kind":"trusted_numeric_fixture",
                    "checks":[{"operation":k,"arguments":deepcopy(a),"expected":v} for k,a,v in e["checks"]]},
                common_mistakes=deepcopy(e["mistakes"]), followup_practice_ids=[],
                source_refs=[], content_origin=ORIGIN, version=2,
                status="published", family_id=e["family"]))
    return {"lessons":lessons,"examples":examples}


def _close(actual: Any, expected: Any) -> bool:
    if isinstance(expected, (list, tuple)):
        return isinstance(actual, (list,tuple)) and len(actual)==len(expected) and all(
            _close(x,y) for x,y in zip(actual,expected,strict=True))
    return isinstance(actual,(int,float)) and math.isfinite(actual) and math.isclose(actual,expected,rel_tol=1e-9,abs_tol=1e-9)


def verify_content(content: dict | None = None) -> list[str]:
    """Check worked examples against trusted calculations."""
    content = build_content() if content is None else content
    errors: list[str] = []
    all_ids = set()
    for group in content.values():
        for item in group:
            if item["id"] in all_ids:
                errors.append(item["id"]+": duplicate ID")
            all_ids.add(item["id"])
            if item["source_refs"] or item["content_origin"]!=ORIGIN:
                errors.append(item["id"]+": project-authored provenance mismatch")
    for e in content["examples"]:
        for check in e["verification"]["checks"]:
            if not _close(calculate(check["operation"],check["arguments"]),check["expected"]):
                errors.append(e["id"]+": worked calculation mismatch")
        if len(e["steps"])<3 or any(not all(s.values()) for s in e["steps"]):
            errors.append(e["id"]+": missing intermediate teaching steps")
    return errors
