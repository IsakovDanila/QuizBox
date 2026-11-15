from __future__ import annotations

from pydantic import BaseModel, Field


class QuizCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class QuizUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class QuestionOptionInput(BaseModel):
    label: str = Field(min_length=1, max_length=300)
    is_correct: bool = False


class QuestionInput(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    points: int = Field(default=1, ge=1, le=100000)
    options: list[QuestionOptionInput] = Field(min_length=2, max_length=10)
