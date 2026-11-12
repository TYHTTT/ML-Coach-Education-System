from enum import Enum
import re

from pydantic_core import core_schema


class Course(str, Enum):
    MACHINE_LEARNING = "machine_learning"
    ADVANCED_MATHEMATICS = "advanced_mathematics"
    LINEAR_ALGEBRA = "linear_algebra"
    PROBABILITY_STATISTICS = "probability_statistics"

    def __str__(self):
        return self.value

    @classmethod
    def _missing_(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", value):
            return None
        member = str.__new__(cls, value)
        member._name_ = value
        member._value_ = value
        return member

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        # Course IDs are database records; the four enum members remain seed constants.
        return core_schema.no_info_after_validator_function(
            cls, core_schema.str_schema(pattern=r"^[a-z][a-z0-9_]{1,63}$")
        )

    @property
    def display_name(self) -> str:
        return {
            self.MACHINE_LEARNING: "机器学习",
            self.ADVANCED_MATHEMATICS: "高等数学",
            self.LINEAR_ALGEBRA: "线性代数",
            self.PROBABILITY_STATISTICS: "概率论与统计基础",
        }.get(self, self.value)
