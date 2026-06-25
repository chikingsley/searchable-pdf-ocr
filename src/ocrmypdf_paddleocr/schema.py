from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BBox(BaseModel):
    model_config = ConfigDict(frozen=True)

    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return max(self.right - self.left, 0.0)

    @property
    def height(self) -> float:
        return max(self.bottom - self.top, 0.0)


class WordRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    bbox: BBox
    confidence: float | None = None
    corrected_text: str | None = None


class LineRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    bbox: BBox
    confidence: float | None = None
    words: list[WordRecord] = Field(default_factory=list)


class PageRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_image: str
    page_number: int
    width: int
    height: int
    dpi: float
    plain_text: str
    lines: list[LineRecord] = Field(default_factory=list)

    @property
    def words(self) -> list[WordRecord]:
        return [word for line in self.lines for word in line.words]


class OverlayBox(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    bbox: BBox
    label: str | None = None
    text: str | None = None
    confidence: float | None = None


class OverlayPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    page_number: int
    width: float
    height: float
    boxes: list[OverlayBox] = Field(default_factory=list)


class ReconcileCorrection(BaseModel):
    model_config = ConfigDict(frozen=True)

    word_id: str
    text: str
    reason: str | None = None


class ReconcileResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    page_number: int
    corrections: list[ReconcileCorrection] = Field(default_factory=list)
