"""The one piece of geometry both formats agree on: a 2D affine transform.

1.x writes the six meaningful terms of a QTransform inline; 2.x writes all nine
as a serialized QVariant. Neither keeps the projective row, so this is what is
left when the two are reconciled.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import cos, radians, sin

@dataclass
class Transform:
    """A 2D affine transform, stored the way both formats store it."""

    m11: float = 1.0
    m12: float = 0.0
    m21: float = 0.0
    m22: float = 1.0
    dx: float = 0.0
    dy: float = 0.0

    @classmethod
    def translate(cls, dx: float, dy: float) -> Transform:
        return cls(dx=dx, dy=dy)

    @classmethod
    def scale(cls, x: float, y: float | None = None) -> Transform:
        return cls(m11=x, m22=x if y is None else y)

    @classmethod
    def rotate(cls, degrees: float) -> Transform:
        angle = radians(degrees)
        return cls(m11=cos(angle), m12=sin(angle), m21=-sin(angle), m22=cos(angle))

    @classmethod
    def compose(cls, *, x: float = 0.0, y: float = 0.0, scale_x: float = 1.0,
                scale_y: float = 1.0, rotation: float = 0.0) -> Transform:
        """Rotate, then scale, then translate: the order the app's gizmo uses."""
        angle = radians(rotation)
        cosine, sine = cos(angle), sin(angle)
        return cls(m11=scale_x * cosine, m12=scale_x * sine,
                   m21=-scale_y * sine, m22=scale_y * cosine, dx=x, dy=y)

    @classmethod
    def from_matrix9(cls, values) -> Transform:
        m11, m12, _, m21, m22, _, dx, dy, _ = values
        return cls(m11, m12, m21, m22, dx, dy)

    def to_matrix9(self) -> list[float]:
        return [self.m11, self.m12, 0.0, self.m21, self.m22, 0.0, self.dx, self.dy, 1.0]

    @property
    def is_identity(self) -> bool:
        return self.to_matrix9() == Transform().to_matrix9()

    def map(self, x: float, y: float) -> tuple[float, float]:
        return (self.m11 * x + self.m21 * y + self.dx,
                self.m12 * x + self.m22 * y + self.dy)

    def scaled(self, factor: float) -> Transform:
        return replace(self, m11=self.m11 * factor, m12=self.m12 * factor,
                       m21=self.m21 * factor, m22=self.m22 * factor)


def multiply(outer: Transform, inner: Transform) -> Transform:
    """`inner` first, then `outer`: how a parent transforms its children."""
    return Transform(
        m11=inner.m11 * outer.m11 + inner.m12 * outer.m21,
        m12=inner.m11 * outer.m12 + inner.m12 * outer.m22,
        m21=inner.m21 * outer.m11 + inner.m22 * outer.m21,
        m22=inner.m21 * outer.m12 + inner.m22 * outer.m22,
        dx=inner.dx * outer.m11 + inner.dy * outer.m21 + outer.dx,
        dy=inner.dx * outer.m12 + inner.dy * outer.m22 + outer.dy)
