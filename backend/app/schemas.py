from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=16000)

    @model_validator(mode="after")
    def content_limit(self):
        if not self.content.strip() or (self.role == "user" and len(self.content) > 8000):
            raise ValueError("Invalid content")
        return self


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    messages: list[Message] = Field(min_length=1, max_length=39)

    @model_validator(mode="after")
    def conversation(self):
        if len(self.messages) % 2 != 1 or any(
            m.role != ("user" if i % 2 == 0 else "assistant")
            for i, m in enumerate(self.messages)
        ) or sum(len(m.content) for m in self.messages) > 64000:
            raise ValueError("Invalid conversation")
        return self
