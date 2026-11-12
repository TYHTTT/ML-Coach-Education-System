from enum import Enum


class Course(str, Enum):
    MACHINE_LEARNING = "machine_learning"
    ADVANCED_MATHEMATICS = "advanced_mathematics"
    LINEAR_ALGEBRA = "linear_algebra"
    PROBABILITY_STATISTICS = "probability_statistics"

    @property
    def display_name(self) -> str:
        return {
            self.MACHINE_LEARNING: "机器学习",
            self.ADVANCED_MATHEMATICS: "高等数学",
            self.LINEAR_ALGEBRA: "线性代数",
            self.PROBABILITY_STATISTICS: "概率论与统计基础",
        }[self]
